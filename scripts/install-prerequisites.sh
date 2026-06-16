#!/usr/bin/env bash
# install-prerequisites.sh — Validate and install shared prerequisites
# Usage: sudo ./scripts/install-prerequisites.sh [--check-only]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

require_root

# ============================================================================
# Parse arguments
# ============================================================================

CHECK_ONLY=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--check-only]"
            exit 1
            ;;
    esac
done

# ============================================================================
# OS Validation
# ============================================================================

log_info "Checking Ubuntu version..."
if ! check_ubuntu_version "22.04"; then
    log_error "Prerequisite check failed: Ubuntu 22.04+ is required"
    log_info "Remediation: Upgrade to Ubuntu 22.04 LTS or newer"
    exit 2
fi
log_info "Ubuntu version OK"

# ============================================================================
# Prerequisites check/install functions
# ============================================================================

install_apt_packages() {
    local packages=("curl" "wget" "apt-transport-https" "ca-certificates" "gnupg" "lsb-release")
    local missing=()

    for pkg in "${packages[@]}"; do
        if ! dpkg -l "$pkg" 2>/dev/null | grep -q "^ii"; then
            missing+=("$pkg")
        fi
    done

    if [[ ${#missing[@]} -eq 0 ]]; then
        log_info "All base apt packages already installed"
        return 0
    fi

    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_error "Prerequisite check failed: Missing packages: ${missing[*]}"
        log_info "Remediation: Run this script without --check-only to install them"
        return 1
    fi

    log_info "Installing missing packages: ${missing[*]}"
    apt-get update -qq
    apt-get install -y -qq "${missing[@]}"
    log_info "Base packages installed"
}

install_docker() {
    if check_command docker; then
        log_info "Docker already installed: $(docker --version)"
        if ! check_docker_running; then
            if [[ "$CHECK_ONLY" == "true" ]]; then
                log_error "Docker is installed but not running"
                return 1
            fi
            log_info "Starting Docker service..."
            systemctl start docker
            systemctl enable docker
        fi
        return 0
    fi

    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_error "Prerequisite check failed: Docker is not installed"
        log_info "Remediation: Run this script without --check-only to install Docker"
        return 1
    fi

    log_info "Installing Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
        $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
        tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin

    systemctl start docker
    systemctl enable docker
    log_info "Docker installed: $(docker --version)"
}

install_kubectl() {
    if check_command kubectl; then
        log_info "kubectl already installed: $(kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null | head -1)"
        return 0
    fi

    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_error "Prerequisite check failed: kubectl is not installed"
        log_info "Remediation: Run this script without --check-only to install kubectl"
        return 1
    fi

    log_info "Installing kubectl..."
    local kubectl_version
    kubectl_version=$(curl -fsSL https://dl.k8s.io/release/stable.txt)
    curl -fsSL "https://dl.k8s.io/release/${kubectl_version}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl
    chmod +x /usr/local/bin/kubectl
    log_info "kubectl installed: $(kubectl version --client --short 2>/dev/null || echo "$kubectl_version")"
}

install_kind() {
    if check_command kind; then
        log_info "kind already installed: $(kind --version)"
        return 0
    fi

    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_error "Prerequisite check failed: kind is not installed"
        log_info "Remediation: Run this script without --check-only to install kind"
        return 1
    fi

    log_info "Installing kind..."
    local kind_version
    kind_version=$(curl -fsSL https://api.github.com/repos/kubernetes-sigs/kind/releases/latest | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/')
    curl -fsSL "https://kind.sigs.k8s.io/dl/${kind_version}/kind-linux-amd64" -o /usr/local/bin/kind
    chmod +x /usr/local/bin/kind
    log_info "kind installed: $(kind --version)"
}

# ============================================================================
# Execute
# ============================================================================

FAILED=false

install_apt_packages || FAILED=true
install_docker || FAILED=true
install_kubectl || FAILED=true
install_kind || FAILED=true

if [[ "$FAILED" == "true" ]]; then
    if [[ "$CHECK_ONLY" == "true" ]]; then
        log_error "Some prerequisites are not met. See above for details."
        exit 2
    else
        log_error "Some prerequisites failed to install. See above for details."
        exit 1
    fi
fi

log_info "All prerequisites satisfied"
exit 0
