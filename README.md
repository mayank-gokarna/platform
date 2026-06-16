# Platform — Jenkins + ArgoCD DevOps Setup

Automated installation scripts for Jenkins, ArgoCD, and a sample Flask web application with full CI/CD pipeline on Ubuntu.

## Prerequisites

- Ubuntu 22.04 LTS or newer
- Root/sudo access
- Internet connectivity

## Quick Start

```bash
# 1. Install prerequisites (Docker, kubectl, kind)
sudo ./scripts/install-prerequisites.sh

# 2. Install Jenkins with plugins
sudo ./scripts/install-jenkins.sh

# 3. Install ArgoCD on a local kind cluster
sudo ./scripts/install-argocd.sh

# 4. Install observability stack (Prometheus + Grafana)
sudo ./scripts/install-observability.sh
```

## Project Structure

```
scripts/
  lib/common.sh          # Shared logging and validation
  lib/plugins.txt        # Jenkins plugin manifest
  install-prerequisites.sh   # Docker, kubectl, kind
  install-jenkins.sh         # Jenkins LTS + plugins
  install-argocd.sh          # kind cluster + ArgoCD
  install-observability.sh   # Prometheus + Grafana

sample-app/
  app/                   # Flask application
  tests/                 # pytest test suite
  grafana/dashboard.json # Grafana dashboard as code
  Dockerfile             # Container build
  requirements.txt       # Python dependencies

k8s/
  deployment.yaml        # Kubernetes deployment
  service.yaml           # Kubernetes service
  argocd-app.yaml        # ArgoCD Application manifest

Jenkinsfile              # CI/CD pipeline
```

## Scripts

| Script | Purpose | Options |
|--------|---------|--------|
| `install-prerequisites.sh` | Install Docker, kubectl, kind | `--check-only` |
| `install-jenkins.sh` | Install Jenkins LTS + plugins | `--plugins-only`, `--port PORT` |
| `install-argocd.sh` | Create kind cluster, install ArgoCD | `--cluster-name NAME`, `--skip-cluster` |
| `install-observability.sh` | Install Prometheus + Grafana | `--skip-prometheus`, `--skip-grafana` |

## Sample Application

A Flask web app with:
- `GET /` — Landing page
- `GET /health` — Health check (JSON)
- `GET /metrics` — Prometheus metrics
- Structured JSON logging
- W3C trace context propagation

## CI/CD Pipeline

The Jenkinsfile defines: Checkout → Lint → Test → Build → Scan (trivy) → Push → Deploy

## Access

- **Jenkins**: http://localhost:8080
- **ArgoCD**: `kubectl port-forward svc/argocd-server -n argocd 8443:443` → https://localhost:8443
- **Grafana**: `kubectl port-forward -n monitoring svc/grafana 3000:80` → http://localhost:3000
- **Prometheus**: `kubectl port-forward -n monitoring svc/prometheus-server 9090:80` → http://localhost:9090
