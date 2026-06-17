#!/usr/bin/env bash
# install-observability.sh — Install Prometheus and Grafana into the Kubernetes cluster
# Usage: sudo ./scripts/install-observability.sh [--skip-prometheus] [--skip-grafana]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

require_root

# ============================================================================
# Defaults and argument parsing
# ============================================================================

SKIP_PROMETHEUS=false
SKIP_GRAFANA=false
NAMESPACE="monitoring"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-prometheus)
            SKIP_PROMETHEUS=true
            shift
            ;;
        --skip-grafana)
            SKIP_GRAFANA=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--skip-prometheus] [--skip-grafana]"
            exit 1
            ;;
    esac
done

# ============================================================================
# Prerequisite checks
# ============================================================================

if ! check_command kubectl; then
    log_error "kubectl not found. Run install-prerequisites.sh first."
    exit 2
fi

if ! check_command helm; then
    log_info "Helm not found — installing..."
    curl -kfsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | VERIFY_CHECKSUM=false bash
fi

if ! kubectl cluster-info &>/dev/null 2>&1; then
    log_error "No Kubernetes cluster reachable. Run install-argocd.sh first."
    exit 2
fi

# ============================================================================
# Create monitoring namespace
# ============================================================================

if kubectl get namespace "$NAMESPACE" &>/dev/null 2>&1; then
    log_info "Namespace '$NAMESPACE' already exists"
else
    log_info "Creating namespace '$NAMESPACE'..."
    kubectl create namespace "$NAMESPACE"
fi

# ============================================================================
# Install Prometheus
# ============================================================================

install_prometheus() {
    if [[ "$SKIP_PROMETHEUS" == "true" ]]; then
        log_info "Skipping Prometheus (--skip-prometheus)"
        return 0
    fi

    if helm list -n "$NAMESPACE" 2>/dev/null | grep -q "prometheus"; then
        log_info "Prometheus already installed"
        return 0
    fi

    log_info "Adding Prometheus Helm chart repo..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
    helm repo update

    log_info "Installing Prometheus..."
    helm install prometheus prometheus-community/prometheus \
        --namespace "$NAMESPACE" \
        --set server.persistentVolume.enabled=false \
        --set alertmanager.enabled=false \
        --set kube-state-metrics.enabled=false \
        --wait --timeout 300s

    log_info "Prometheus installed"
}

# ============================================================================
# Install Grafana
# ============================================================================

install_grafana() {
    if [[ "$SKIP_GRAFANA" == "true" ]]; then
        log_info "Skipping Grafana (--skip-grafana)"
        return 0
    fi

    if helm list -n "$NAMESPACE" 2>/dev/null | grep -q "grafana"; then
        log_info "Grafana already installed"
        return 0
    fi

    log_info "Adding Grafana Helm chart repo..."
    helm repo add grafana https://grafana.github.io/helm-charts 2>/dev/null || true
    helm repo update

    log_info "Installing Grafana..."
    helm install grafana grafana/grafana \
        --namespace "$NAMESPACE" \
        --set persistence.enabled=false \
        --set adminUser=admin \
        --set adminPassword=admin \
        --set "datasources.datasources\\.yaml.apiVersion=1" \
        --set "datasources.datasources\\.yaml.datasources[0].name=Prometheus" \
        --set "datasources.datasources\\.yaml.datasources[0].type=prometheus" \
        --set "datasources.datasources\\.yaml.datasources[0].url=http://prometheus-server.${NAMESPACE}.svc.cluster.local" \
        --set "datasources.datasources\\.yaml.datasources[0].access=proxy" \
        --set "datasources.datasources\\.yaml.datasources[0].isDefault=true" \
        --wait --timeout 300s

    log_info "Grafana installed (admin/admin)"
}

# ============================================================================
# Provision dashboard
# ============================================================================

provision_dashboard() {
    local dashboard_file="${SCRIPT_DIR}/../sample-app/grafana/dashboard.json"

    if [[ ! -f "$dashboard_file" ]]; then
        log_warn "Dashboard JSON not found at $dashboard_file — skipping provisioning"
        return 0
    fi

    log_info "Provisioning Grafana dashboard from dashboard.json..."

    # Create a ConfigMap with the dashboard
    kubectl create configmap sample-app-dashboard \
        --from-file=sample-app-dashboard.json="$dashboard_file" \
        --namespace "$NAMESPACE" \
        --dry-run=client -o yaml | kubectl apply -f -

    # Label it for the Grafana sidecar (if using Grafana Helm chart's sidecar)
    kubectl label configmap sample-app-dashboard \
        grafana_dashboard=1 \
        --namespace "$NAMESPACE" \
        --overwrite

    log_info "Dashboard provisioned as ConfigMap"
}

# ============================================================================
# Main execution
# ============================================================================

install_prometheus
install_grafana
provision_dashboard

log_info "Observability stack installed in namespace '$NAMESPACE'"
log_info "Access Prometheus: kubectl port-forward -n $NAMESPACE svc/prometheus-server 9090:80"
log_info "Access Grafana:    kubectl port-forward -n $NAMESPACE svc/grafana 3000:80"
log_info "Grafana credentials: admin / admin"
