#!/usr/bin/env bash
# common.sh — Shared logging, error handling, and validation functions
# Sourced by all installation scripts

set -euo pipefail

# ============================================================================
# Logging
# ============================================================================

log_info() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [INFO] $*"
}

log_warn() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [WARN] $*" >&2
}

log_error() {
    echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] [ERROR] $*" >&2
}

# ============================================================================
# Validation helpers
# ============================================================================

check_command() {
    local cmd="$1"
    if command -v "$cmd" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

check_ubuntu_version() {
    local min_version="${1:-22.04}"
    if [[ ! -f /etc/os-release ]]; then
        log_error "Cannot determine OS: /etc/os-release not found"
        return 1
    fi
    # shellcheck source=/dev/null
    source /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        log_error "Unsupported OS: $ID. This script requires Ubuntu."
        return 1
    fi
    if ! printf '%s\n%s\n' "$min_version" "$VERSION_ID" | sort -V -C; then
        log_error "Ubuntu $VERSION_ID is below minimum required version $min_version"
        return 1
    fi
    return 0
}

check_docker_running() {
    if ! systemctl is-active --quiet docker 2>/dev/null; then
        log_error "Docker is not running"
        return 1
    fi
    return 0
}

check_port_available() {
    local port="$1"
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        log_error "Port $port is already in use"
        return 1
    fi
    return 0
}

# ============================================================================
# Privilege check
# ============================================================================

require_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# ============================================================================
# Cleanup trap
# ============================================================================

cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        log_error "Script failed with exit code $exit_code"
    fi
    return 0
}

trap cleanup EXIT
