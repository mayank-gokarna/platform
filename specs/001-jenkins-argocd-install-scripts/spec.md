# Feature Specification: Jenkins & ArgoCD Installation Scripts with Sample Application

**Created**: 2026-06-16

**Status**: Completed

**Input**: User description: "create scripts to Install jenkins with required plugins and argocd targeted for this ubuntu OS. Also create a sample web based application which can be built via Jenkins and deployed through ArgoCD."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install Jenkins with Required Plugins (Priority: P1)

A platform engineer runs a single script on an Ubuntu machine and gets a fully functional Jenkins instance with all required CI plugins pre-installed and configured, ready to run pipelines.

**Why this priority**: Jenkins is the CI engine for the platform. Without it, no pipelines can run, blocking all downstream development and deployment workflows.

**Independent Test**: Can be fully tested by running the Jenkins install script on a fresh Ubuntu machine, accessing the Jenkins web UI, and confirming all specified plugins are active and Jenkins can execute a sample pipeline.

**Acceptance Scenarios**:

1. **Given** a fresh Ubuntu 22.04+ machine with internet access, **When** the engineer runs the Jenkins install script, **Then** Jenkins is installed, running as a systemd service, and accessible on its configured port.
2. **Given** Jenkins is installed, **When** the engineer checks the plugin list, **Then** all required plugins (Pipeline, Git, Docker Pipeline, Credentials, Blue Ocean, Job DSL, Kubernetes) are installed and active.
3. **Given** Jenkins is running with plugins, **When** the engineer creates a simple declarative pipeline job, **Then** the job executes successfully confirming the installation is functional.
4. **Given** any step of the script fails, **When** the engineer reviews the output, **Then** a clear error message indicates what failed and how to remediate.

---

### User Story 2 - Install ArgoCD (Priority: P1)

A platform engineer runs a single script on an Ubuntu machine and gets ArgoCD installed and accessible, ready to manage GitOps deployments.

**Why this priority**: ArgoCD is the CD engine for the platform. It is equally critical as Jenkins for enabling the full CI/CD workflow defined in the project constitution.

**Independent Test**: Can be fully tested by running the ArgoCD install script, verifying ArgoCD server is running, logging in via CLI or web UI, and confirming it can connect to a Git repository.

**Acceptance Scenarios**:

1. **Given** a fresh Ubuntu 22.04+ machine with a running Kubernetes cluster (or the script provisions one), **When** the engineer runs the ArgoCD install script, **Then** ArgoCD is deployed and its server is accessible.
2. **Given** ArgoCD is installed, **When** the engineer retrieves the initial admin credentials, **Then** they can log in to the ArgoCD UI and CLI successfully.
3. **Given** ArgoCD is running, **When** the engineer points it at a sample Git repository, **Then** ArgoCD can sync and display the application state.
4. **Given** any step of the script fails, **When** the engineer reviews the output, **Then** a clear error message indicates what failed and suggests remediation.

---

### User Story 3 - Prerequisites Validation and Idempotent Execution (Priority: P2)

Before installing any tool, the scripts validate that all prerequisites are met (OS version, dependencies, network access) and can be re-run safely without breaking an existing installation.

**Why this priority**: Idempotency and pre-checks prevent broken installations and reduce support burden. Important for reliability but secondary to core installation capability.

**Independent Test**: Can be tested by running the scripts twice in succession and verifying no errors occur on the second run, and by running on a machine missing prerequisites to confirm clear validation messages.

**Acceptance Scenarios**:

1. **Given** an Ubuntu machine missing Java, **When** the Jenkins install script runs prerequisite checks, **Then** it either installs Java automatically or clearly reports it as a missing dependency before proceeding.
2. **Given** Jenkins is already installed and running, **When** the script is run again, **Then** it completes without errors and does not duplicate configurations or break the existing installation.
3. **Given** ArgoCD is already deployed in the cluster, **When** the ArgoCD script is run again, **Then** it completes without errors and the existing ArgoCD state is preserved.

---

### User Story 4 - Sample Web Application with CI/CD Pipeline (Priority: P1)

A platform engineer deploys a sample web application that demonstrates the full CI/CD workflow: Jenkins builds and tests the application, pushes a container image, and ArgoCD automatically deploys it to the Kubernetes cluster. This validates the entire platform end-to-end.

**Why this priority**: The demo application is the integration test for the entire platform. Without it, there is no way to verify that Jenkins and ArgoCD work together correctly in the GitOps flow defined by the constitution.

**Independent Test**: Can be tested by pushing a code change to the sample app repository, observing Jenkins build it, and confirming ArgoCD deploys the new version to the cluster with the updated container image.

**Acceptance Scenarios**:

1. **Given** Jenkins and ArgoCD are installed, **When** the engineer sets up the sample application, **Then** a working web application is accessible in the browser showing a simple page.
2. **Given** the sample app is deployed, **When** the engineer pushes a code change to the app's Git repository, **Then** Jenkins automatically triggers a build pipeline (lint, test, build image, push image).
3. **Given** Jenkins has built and pushed a new image, **When** ArgoCD detects the manifest update in Git, **Then** it deploys the new version to the cluster and the updated application is accessible.
4. **Given** the sample app is running, **When** the engineer checks the application, **Then** it exposes a health endpoint returning its current version and status.

---

### User Story 5 - Sample Application Kubernetes Manifests (Priority: P2)

The sample application includes production-ready Kubernetes manifests (Deployment, Service, Ingress/port-forward) and a Jenkinsfile that ArgoCD can sync from Git, following the GitOps model.

**Why this priority**: Well-structured manifests and pipeline definition serve as a reference for all future applications on the platform. Important for usability but secondary to getting the app running.

**Independent Test**: Can be tested by applying the manifests directly with kubectl and verifying the app deploys correctly, independent of ArgoCD.

**Acceptance Scenarios**:

1. **Given** the Kubernetes manifests exist in the repo, **When** applied to a cluster, **Then** the sample app deploys and is accessible without modification.
2. **Given** the Jenkinsfile exists in the repo, **When** Jenkins runs the pipeline, **Then** all stages (lint, test, build, push) execute successfully.
3. **Given** the ArgoCD Application manifest points to the sample app's repo, **When** ArgoCD syncs, **Then** it deploys the app matching the desired state in Git.

---

### Edge Cases

- What happens when the machine has no internet access during installation?
- How does the script handle an incompatible Ubuntu version (e.g., Ubuntu 18.04 or earlier)?
- What happens if the Kubernetes cluster is not running when the ArgoCD script executes?
- How does the script handle insufficient disk space or memory?
- What happens if a required port (8080 for Jenkins, 443/80 for ArgoCD) is already in use?
- What happens if the Jenkins pipeline fails mid-build (e.g., tests fail)? Does ArgoCD remain on the last good deployment?
- What happens if the container registry is unreachable when Jenkins tries to push the image?
- How does the sample app behave if deployed without a database or external dependency?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a shell script that installs Jenkins LTS on Ubuntu 22.04+
- **FR-002**: System MUST install the following Jenkins plugins: Pipeline, Git, Docker Pipeline, Credentials Binding, Blue Ocean, Job DSL, Kubernetes
- **FR-003**: System MUST configure Jenkins to start automatically via systemd on boot
- **FR-004**: System MUST provide a shell script that provisions a kind Kubernetes cluster (if none exists) and installs ArgoCD into it, accessible from the Ubuntu host
- **FR-005**: System MUST expose the ArgoCD server so it is accessible via browser or CLI from the host machine
- **FR-006**: System MUST output the initial ArgoCD admin password or provide instructions to retrieve it
- **FR-007**: Scripts MUST validate prerequisites (OS version, required packages, network connectivity) before installation
- **FR-008**: Scripts MUST be idempotent — safe to run multiple times without side effects
- **FR-009**: Scripts MUST provide clear, actionable error messages on failure
- **FR-010**: Scripts MUST log all actions to stdout with timestamps for troubleshooting
- **FR-011**: System MUST include a sample web application with source code, a Dockerfile, and a health endpoint
- **FR-012**: Sample application MUST include a Jenkinsfile defining a CI pipeline (lint, test, build container image, push to registry)
- **FR-013**: Sample application MUST include Kubernetes manifests (Deployment, Service) for deployment
- **FR-014**: Sample application MUST include an ArgoCD Application manifest that points to the app's Kubernetes manifests in Git
- **FR-015**: The CI pipeline MUST push images to a local in-cluster registry and update the image tag in the Kubernetes manifests after a successful build so ArgoCD can detect and deploy the change
- **FR-016**: Sample application MUST display a simple web page showing app name and version to visually confirm deployment
- **FR-017**: Sample application MUST expose a `/health` endpoint returning JSON with version and status
- **FR-018**: Sample application MUST expose a `/metrics` endpoint in Prometheus exposition format (using prometheus_flask_instrumentator or similar)
- **FR-019**: Sample application MUST use structured JSON logging (timestamps, log level, request context) to stdout
- **FR-020**: Sample application MUST propagate trace context headers (W3C Trace Context / traceparent) for distributed tracing readiness
- **FR-021**: The CI pipeline MUST scan container images for known vulnerabilities (e.g., using trivy) before pushing to the registry, and fail the build if critical vulnerabilities are found
- **FR-022**: System MUST include a Grafana dashboard JSON file that visualizes the sample app's RED metrics (request rate, error rate, duration) from the /metrics endpoint
- **FR-023**: System MUST provide a script to deploy Prometheus and Grafana into the kind cluster, configured to scrape the sample app's /metrics endpoint and load the dashboard automatically

### Key Entities

- **Jenkins Instance**: The CI server with its plugin ecosystem, running as a system service on the Ubuntu host
- **ArgoCD Deployment**: The GitOps CD controller running inside a Kubernetes cluster, managing application state from Git repositories
- **Installation Script**: A self-contained bash script with prerequisite checks, installation logic, post-install validation, and error handling
- **Plugin Manifest**: The list of required Jenkins plugins that the script ensures are installed and active
- **Sample Web Application**: A minimal Python Flask app with observability instrumentation (metrics, structured logs, trace headers), serving as the end-to-end demo of the CI/CD pipeline
- **Jenkinsfile**: Declarative pipeline definition in the sample app repo that Jenkins executes for CI
- **Kubernetes Manifests**: Deployment and Service YAML files defining how the sample app runs in the cluster
- **ArgoCD Application**: A manifest that tells ArgoCD to watch the sample app's Git repo and sync its Kubernetes resources
- **Grafana Dashboard**: A JSON dashboard definition that visualizes the sample app's RED metrics, provisioned automatically into Grafana
- **Observability Stack**: Prometheus (metrics scraping) and Grafana (visualization) deployed in the kind cluster via a script

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A platform engineer can go from a fresh Ubuntu machine to a running Jenkins instance with all plugins in under 10 minutes of script execution time
- **SC-002**: A platform engineer can go from a Kubernetes-ready Ubuntu machine to a running ArgoCD instance in under 5 minutes of script execution time
- **SC-003**: Scripts succeed on first run without manual intervention on a standard Ubuntu 22.04+ machine with internet access
- **SC-004**: Scripts can be re-run on an already-configured machine without producing errors or altering existing state
- **SC-005**: Any failure during installation produces a human-readable error message that identifies the problem and suggests a fix
- **SC-006**: A code change pushed to the sample app triggers a full CI/CD cycle (build → push → deploy) completing in under 5 minutes
- **SC-007**: The sample application is accessible in a browser and displays its version within 30 seconds of ArgoCD completing sync
- **SC-008**: The sample app's health endpoint responds with correct version information matching the deployed image tag

## Clarifications

### Session 2026-06-16

- Q: Which container registry should the CI/CD pipeline use? → A: Local registry deployed in-cluster alongside kind
- Q: What language/framework should the sample web application use? → A: Python with Flask
- Q: Should the script provision the Kubernetes cluster or assume one exists? → A: Script provisions a kind cluster if none exists (fully self-contained)
- Q: Should the sample app include observability instrumentation? → A: Yes — Prometheus metrics endpoint, structured JSON logging, and basic trace headers
- Q: How should Jenkins authenticate to the kind cluster and local registry? → A: Host kubeconfig + localhost registry access (no extra credentials needed)

## Assumptions

- Target OS is Ubuntu 22.04 or newer (LTS preferred)
- The machine has internet access to download packages and container images
- For ArgoCD, the script provisions a kind cluster with a local registry if no Kubernetes cluster is detected; no pre-existing cluster is required
- Jenkins will run directly on the Ubuntu host (not containerized) for simplicity
- Jenkins accesses the kind cluster via the host's kubeconfig (~/.kube/config) and pushes images to the local registry via localhost; no additional credentials or service accounts are required
- The engineer running the scripts has sudo/root privileges
- Default ports are used unless already occupied (Jenkins: 8080, ArgoCD: port-forward or NodePort)
- Scripts are written in bash, compatible with the project's `"script": "sh"` convention from init-options.json
- The sample application is intentionally simple (single service, no database) to focus on demonstrating the CI/CD pipeline
- The sample app uses Python with Flask — minimal dependencies, fast container builds, trivial to lint/test
- A local container registry (e.g., registry:2) runs inside the kind cluster; no external registry accounts are needed
