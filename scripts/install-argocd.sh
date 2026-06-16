#!/usr/bin/env bash
# install-argocd.sh — Install ArgoCD into a local kind Kubernetes cluster
# Usage: sudo ./scripts/install-argocd.sh [--cluster-name NAME] [--skip-cluster]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

require_root

# ============================================================================
# Defaults and argument parsing
# ============================================================================

CLUSTER_NAME="platform"
SKIP_CLUSTER=false
REGISTRY_NAME="kind-registry"
REGISTRY_PORT=5001

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cluster-name)
            CLUSTER_NAME="$2"
            shift 2
            ;;
        --skip-cluster)
            SKIP_CLUSTER=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--cluster-name NAME] [--skip-cluster]"
            exit 1
            ;;
    esac
done

# ============================================================================
# Prerequisite checks
# ============================================================================

log_info "Checking ArgoCD prerequisites..."

if ! check_command kubectl; then
    log_error "Prerequisite check failed: kubectl is not installed"
    log_info "Remediation: Run ./scripts/install-prerequisites.sh first"
    exit 2
fi

if ! check_command kind; then
    log_error "Prerequisite check failed: kind is not installed"
    log_info "Remediation: Run ./scripts/install-prerequisites.sh first"
    exit 2
fi

if ! check_docker_running; then
    log_error "Prerequisite check failed: Docker is not running"
    log_info "Remediation: Start Docker with 'systemctl start docker'"
    exit 2
fi

# ============================================================================
# Create kind cluster with local registry
# ============================================================================

create_local_registry() {
    if docker inspect "$REGISTRY_NAME" &>/dev/null 2>&1; then
        log_info "Local registry '$REGISTRY_NAME' already running"
        return 0
    fi

    log_info "Creating local container registry on port $REGISTRY_PORT..."
    docker run -d --restart=always \
        -p "127.0.0.1:${REGISTRY_PORT}:5000" \
        --network bridge \
        --name "$REGISTRY_NAME" \
        registry:2
    log_info "Local registry created: localhost:${REGISTRY_PORT}"
}

create_kind_cluster() {
    if [[ "$SKIP_CLUSTER" == "true" ]]; then
        log_info "Skipping cluster creation (--skip-cluster)"
        return 0
    fi

    if kind get clusters 2>/dev/null | grep -q "^${CLUSTER_NAME}$"; then
        log_info "Kind cluster '$CLUSTER_NAME' already exists"
        # Ensure kubeconfig is set
        kind export kubeconfig --name "$CLUSTER_NAME" 2>/dev/null || true
        return 0
    fi

    # Create the registry first
    create_local_registry

    log_info "Creating kind cluster '$CLUSTER_NAME' with local registry..."

    # Kind cluster config with registry mirror
    cat <<EOF | kind create cluster --name "$CLUSTER_NAME" --config=-
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
containerdConfigPatches:
- |-
  [plugins."io.containerd.grpc.v1.cri".registry.mirrors."localhost:${REGISTRY_PORT}"]
    endpoint = ["http://${REGISTRY_NAME}:5000"]
EOF

    # Connect the registry to the kind network
    if ! docker network inspect kind | grep -q "$REGISTRY_NAME" 2>/dev/null; then
        docker network connect kind "$REGISTRY_NAME" 2>/dev/null || true
    fi

    # Document the registry for kind
    kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "localhost:${REGISTRY_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF

    log_info "Kind cluster '$CLUSTER_NAME' created with local registry"
}

# ============================================================================
# Install ArgoCD
# ============================================================================

install_argocd() {
    local argocd_ns="argocd"

    # Create namespace if not exists
    if kubectl get namespace "$argocd_ns" &>/dev/null 2>&1; then
        log_info "Namespace '$argocd_ns' already exists"
    else
        log_info "Creating namespace '$argocd_ns'..."
        kubectl create namespace "$argocd_ns"
    fi

    # Apply ArgoCD install manifest
    log_info "Applying ArgoCD installation manifest..."
    kubectl apply -n "$argocd_ns" \
        -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

    # Wait for ArgoCD server to be ready
    log_info "Waiting for ArgoCD server to become ready..."
    kubectl wait --for=condition=available deployment/argocd-server \
        -n "$argocd_ns" --timeout=300s

    log_info "ArgoCD deployed successfully"
}

# ============================================================================
# Install ArgoCD CLI
# ============================================================================

install_argocd_cli() {
    if check_command argocd; then
        log_info "ArgoCD CLI already installed: $(argocd version --client --short 2>/dev/null || echo 'installed')"
        return 0
    fi

    log_info "Installing ArgoCD CLI..."
    local argocd_version
    argocd_version=$(curl -fsSL https://api.github.com/repos/argoproj/argo-cd/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')

    curl -fsSL "https://github.com/argoproj/argo-cd/releases/download/${argocd_version}/argocd-linux-amd64" \
        -o /usr/local/bin/argocd
    chmod +x /usr/local/bin/argocd
    log_info "ArgoCD CLI installed: $argocd_version"
}

# ============================================================================
# Extract admin password and print instructions
# ============================================================================

print_access_info() {
    log_info "Extracting initial admin password..."
    local password
    password=$(kubectl -n argocd get secret argocd-initial-admin-secret \
        -o jsonpath="{.data.password}" 2>/dev/null | base64 -d 2>/dev/null || echo "")

    if [[ -n "$password" ]]; then
        log_info "Initial admin password: $password"
    else
        log_warn "Could not extract initial admin password"
        log_info "Retrieve manually: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d"
    fi

    log_info "ArgoCD installed in cluster '$CLUSTER_NAME'"
    log_info "Access ArgoCD: kubectl port-forward svc/argocd-server -n argocd 8443:443"
    log_info "Then open: https://localhost:8443"
}

# ============================================================================
# Main execution
# ============================================================================

create_kind_cluster
install_argocd
install_argocd_cli
print_access_info
