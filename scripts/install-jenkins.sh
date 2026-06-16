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

    # Check Java 17+
    if check_command java; then
        local java_version
        java_version=$(java -version 2>&1 | head -1 | sed -E 's/.*"([0-9]+)\..*/\1/')
        if [[ "$java_version" -lt 17 ]]; then
            log_warn "Java $java_version found but Jenkins requires Java 17+"
            return 1
        fi
        log_info "Java OK: version $java_version"
    else
        log_warn "Java not found — will install OpenJDK 17"
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
        if [[ "$java_version" -ge 17 ]]; then
            log_info "Java 17+ already installed (version $java_version)"
            return 0
        fi
    fi

    log_info "Installing OpenJDK 17..."
    apt-get update -qq
    apt-get install -y -qq fontconfig openjdk-17-jre
    log_info "OpenJDK 17 installed"
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
    curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io-2023.key | \
        gpg --dearmor -o /usr/share/keyrings/jenkins-keyring.gpg 2>/dev/null || true

    if [[ ! -f /etc/apt/sources.list.d/jenkins.list ]]; then
        echo "deb [signed-by=/usr/share/keyrings/jenkins-keyring.gpg] https://pkg.jenkins.io/debian-stable binary/" | \
            tee /etc/apt/sources.list.d/jenkins.list > /dev/null
    fi

    log_info "Installing Jenkins LTS..."
    apt-get update -qq
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

    local jenkins_cli="/usr/local/bin/jenkins-plugin-cli"
    if [[ ! -f "$jenkins_cli" ]]; then
        # Use the CLI bundled in the Jenkins WAR
        local jenkins_war
        jenkins_war=$(find /usr/share/jenkins -name "jenkins.war" 2>/dev/null | head -1)
        if [[ -z "$jenkins_war" ]]; then
            jenkins_war="/usr/share/java/jenkins.war"
        fi

        if [[ -f "$jenkins_war" ]]; then
            log_info "Using jenkins-plugin-cli from WAR file..."
            java -jar "$jenkins_war" --plugin-cli --plugin-file "$PLUGINS_FILE" \
                --jenkins-update-center "https://updates.jenkins.io" \
                -d /var/lib/jenkins/plugins/ 2>&1 || {
                    log_warn "WAR-based plugin install failed, trying alternative method..."
                    install_plugins_alternative
                    return $?
                }
        else
            log_warn "jenkins-plugin-cli not found, using alternative method..."
            install_plugins_alternative
            return $?
        fi
    else
        "$jenkins_cli" --plugin-file "$PLUGINS_FILE" -d /var/lib/jenkins/plugins/ 2>&1
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
    local cli_url="https://github.com/jenkinsci/plugin-installation-manager-tool/releases/latest/download/jenkins-plugin-manager.jar"
    local cli_jar="/tmp/jenkins-plugin-manager.jar"

    log_info "Downloading jenkins-plugin-manager..."
    curl -fsSL "$cli_url" -o "$cli_jar"

    java -jar "$cli_jar" \
        --plugin-file "$PLUGINS_FILE" \
        --plugin-download-directory /var/lib/jenkins/plugins/ \
        --jenkins-update-center "https://updates.jenkins.io" 2>&1

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
