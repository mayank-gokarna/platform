#!/usr/bin/env bash
# install-jenkins.sh — Install Jenkins LTS with required plugins on Ubuntu
# Usage: sudo ./scripts/install-jenkins.sh [--plugins-only] [--port PORT]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

require_root

# ============================================================================
# Defaults and argument parsing
# ============================================================================

PLUGINS_ONLY=false
JENKINS_PORT=8080

while [[ $# -gt 0 ]]; do
    case "$1" in
        --plugins-only)
            PLUGINS_ONLY=true
            shift
            ;;
        --port)
            JENKINS_PORT="$2"
            shift 2
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Usage: $0 [--plugins-only] [--port PORT]"
            exit 1
            ;;
    esac
done

PLUGINS_FILE="${SCRIPT_DIR}/lib/plugins.txt"

# ============================================================================
# Prerequisite checks
# ============================================================================

check_jenkins_prerequisites() {
    log_info "Checking Jenkins prerequisites..."

    # Check Java 21+ (required by Jenkins LTS 2.540+)
    if check_command java; then
        local java_version
        java_version=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+)\..*/\1/')
        if [[ "$java_version" -lt 21 ]]; then
            log_warn "Java $java_version found but Jenkins requires Java 21+"
            return 1
        fi
        log_info "Java OK: version $java_version"
    else
        log_warn "Java not found — will install OpenJDK 21"
        return 1
    fi
    return 0
}

# ============================================================================
# Install Java
# ============================================================================

install_java() {
    if check_command java; then
        local java_version
        java_version=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+)\..*/\1/')
        if [[ "$java_version" -ge 21 ]]; then
            log_info "Java 21+ already installed (version $java_version)"
            return 0
        fi
    fi

    log_info "Installing OpenJDK 21..."
    apt-get update -qq
    apt-get install -y -qq fontconfig openjdk-21-jre
    log_info "OpenJDK 21 installed"
}

# ============================================================================
# Install Jenkins
# ============================================================================

install_jenkins() {
    if check_command jenkins && systemctl is-enabled --quiet jenkins 2>/dev/null; then
        log_info "Jenkins is already installed"
        return 0
    fi

    log_info "Adding Jenkins apt repository..."
    # Remove any stale config from previous runs
    rm -f /usr/share/keyrings/jenkins-keyring.gpg
    rm -f /etc/apt/sources.list.d/jenkins.list

    # Try to import GPG key (may fail behind corporate proxies like Zscaler)
    local key_ok=false
    curl -fsSLk https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key \
        -o /tmp/jenkins.key 2>/dev/null || true

    if [[ -s /tmp/jenkins.key ]]; then
        gpg --batch --yes --dearmor -o /usr/share/keyrings/jenkins-keyring.gpg \
            /tmp/jenkins.key 2>/dev/null || true
        rm -f /tmp/jenkins.key

        if [[ -s /usr/share/keyrings/jenkins-keyring.gpg ]]; then
            echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.gpg] https://pkg.jenkins.io/debian-stable binary/" | \
                tee /etc/apt/sources.list.d/jenkins.list > /dev/null
            # Test if key actually works (disable pipefail for this check)
            local update_output
            update_output=$(apt-get update 2>&1 || true)
            if echo "$update_output" | grep -q "NO_PUBKEY"; then
                log_warn "GPG key corrupted by corporate proxy."
            else
                key_ok=true
            fi
        fi
    fi

    if [[ "$key_ok" != "true" ]]; then
        log_warn "Using trusted repo (GPG verification unavailable behind proxy)."
        echo "deb [trusted=yes] https://pkg.jenkins.io/debian-stable binary/" | \
            tee /etc/apt/sources.list.d/jenkins.list > /dev/null
    fi

    log_info "Installing Jenkins LTS..."
    apt-get update -qq || true
    apt-get install -y -qq jenkins

    # Configure port if non-default
    if [[ "$JENKINS_PORT" != "8080" ]]; then
        log_info "Configuring Jenkins to use port $JENKINS_PORT..."
        if [[ -f /etc/default/jenkins ]]; then
            sed -i "s/HTTP_PORT=.*/HTTP_PORT=$JENKINS_PORT/" /etc/default/jenkins
        fi
        mkdir -p /etc/systemd/system/jenkins.service.d
        cat > /etc/systemd/system/jenkins.service.d/override.conf <<EOF
[Service]
Environment="JENKINS_PORT=$JENKINS_PORT"
EOF
        systemctl daemon-reload
    fi

    log_info "Enabling and starting Jenkins..."
    systemctl enable jenkins
    systemctl start jenkins
    log_info "Jenkins installed and started"
}

# ============================================================================
# Wait for Jenkins to be ready
# ============================================================================

wait_for_jenkins() {
    local url="http://localhost:${JENKINS_PORT}/login"
    local max_wait=120
    local waited=0

    log_info "Waiting for Jenkins to become ready on port $JENKINS_PORT..."
    while [[ $waited -lt $max_wait ]]; do
        if curl -sf -o /dev/null "$url" 2>/dev/null; then
            log_info "Jenkins is ready"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done

    log_error "Jenkins did not become ready within ${max_wait}s"
    log_info "Remediation: Check logs with 'journalctl -u jenkins -f'"
    return 1
}

# ============================================================================
# Install plugins
# ============================================================================

install_plugins() {
    if [[ ! -f "$PLUGINS_FILE" ]]; then
        log_error "Plugin manifest not found: $PLUGINS_FILE"
        exit 1
    fi

    log_info "Installing Jenkins plugins from $PLUGINS_FILE..."

    # Get the Jenkins admin password for CLI access
    local admin_pass=""
    if [[ -f /var/lib/jenkins/secrets/initialAdminPassword ]]; then
        admin_pass=$(cat /var/lib/jenkins/secrets/initialAdminPassword)
    fi

    # Use Jenkins CLI to install plugins via the running instance
    local jenkins_cli_jar="/tmp/jenkins-cli.jar"
    if [[ -n "$admin_pass" ]]; then
        # Download Jenkins CLI from the running instance
        curl -sfk "http://localhost:${JENKINS_PORT}/jnlpJars/jenkins-cli.jar" \
            -o "$jenkins_cli_jar" 2>/dev/null || true

        if [[ -s "$jenkins_cli_jar" ]]; then
            log_info "Installing plugins via Jenkins CLI..."
            while IFS= read -r plugin || [[ -n "$plugin" ]]; do
                plugin=$(echo "$plugin" | tr -d '[:space:]')
                [[ -z "$plugin" || "$plugin" == \#* ]] && continue
                log_info "  Installing plugin: $plugin"
                java -jar "$jenkins_cli_jar" -s "http://localhost:${JENKINS_PORT}/" \
                    -auth "admin:${admin_pass}" install-plugin "$plugin" 2>&1 || \
                    log_warn "  Failed to install plugin: $plugin"
            done < "$PLUGINS_FILE"
            rm -f "$jenkins_cli_jar"
        else
            log_warn "Could not download Jenkins CLI, using plugin manager tool..."
            install_plugins_alternative
            return $?
        fi
    else
        log_warn "No admin password found, using plugin manager tool..."
        install_plugins_alternative
        return $?
    fi

    # Fix plugin ownership
    chown -R jenkins:jenkins /var/lib/jenkins/plugins/ 2>/dev/null || true

    log_info "Restarting Jenkins to activate plugins..."
    systemctl restart jenkins
    wait_for_jenkins
    log_info "Plugins installed and activated"
}

install_plugins_alternative() {
    # Download jenkins-plugin-manager standalone tool
    local pim_version
    pim_version=$(curl -fsSLk https://api.github.com/repos/jenkinsci/plugin-installation-manager-tool/releases/latest 2>/dev/null \
        | grep '"tag_name"' | sed -E 's/.*"([^"]+)".*/\1/' || echo "2.14.0")
    local cli_url="https://github.com/jenkinsci/plugin-installation-manager-tool/releases/download/${pim_version}/jenkins-plugin-manager-${pim_version}.jar"
    local cli_jar="/tmp/jenkins-plugin-manager.jar"

    log_info "Downloading jenkins-plugin-manager ${pim_version}..."
    curl -fsSLk "$cli_url" -o "$cli_jar" || {
        log_error "Failed to download plugin manager"
        return 1
    }

    local jenkins_war
    jenkins_war=$(find /usr/share/java /usr/share/jenkins -name "jenkins.war" 2>/dev/null | head -1)

    java -jar "$cli_jar" \
        --war "$jenkins_war" \
        --plugin-file "$PLUGINS_FILE" \
        --plugin-download-directory /var/lib/jenkins/plugins/ 2>&1 || true

    chown -R jenkins:jenkins /var/lib/jenkins/plugins/ 2>/dev/null || true
    rm -f "$cli_jar"
}

# ============================================================================
# Main execution
# ============================================================================

if [[ "$PLUGINS_ONLY" == "true" ]]; then
    log_info "Running in plugins-only mode..."
    wait_for_jenkins
    install_plugins
else
    install_java
    install_jenkins

    # Ensure Jenkins is running before installing plugins
    if ! systemctl is-active --quiet jenkins; then
        systemctl start jenkins
    fi
    wait_for_jenkins
    install_plugins
fi

log_info "Jenkins is running on port $JENKINS_PORT"
log_info "Initial admin password: /var/lib/jenkins/secrets/initialAdminPassword"
log_info "Access Jenkins at: http://localhost:${JENKINS_PORT}"
