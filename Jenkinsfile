pipeline {
    agent any

    environment {
        REGISTRY       = 'localhost:5001'
        CLUSTER_REGISTRY = 'kind-registry:5000'
        IMAGE_NAME     = 'sample-app'
        IMAGE_TAG      = "${env.BUILD_NUMBER}"
        FULL_IMAGE     = "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        CLUSTER_IMAGE  = "${CLUSTER_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        // Branch that ArgoCD's Application tracks (k8s/argocd-app.yaml targetRevision)
        DEPLOY_BRANCH  = '001-jenkins-argocd-install-scripts'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Lint') {
            steps {
                dir('sample-app') {
                    sh '''
                        python3 -m venv .venv
                        . .venv/bin/activate
                        pip install -q flake8
                        flake8 app/ --max-line-length=120 --count --show-source --statistics
                    '''
                }
            }
        }

        stage('Test') {
            steps {
                dir('sample-app') {
                    sh '''
                        . .venv/bin/activate
                        pip install -q -r requirements.txt -r requirements-dev.txt
                        pytest tests/ -v --tb=short
                    '''
                }
            }
        }

        stage('Build Image') {
            steps {
                dir('sample-app') {
                    sh "docker build -t ${FULL_IMAGE} ."
                }
            }
        }

        stage('Scan Image') {
            steps {
                sh '''
                    # Install trivy if not available
                    if ! command -v trivy &>/dev/null; then
                        curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b ${WORKSPACE}/bin
                        export PATH="${WORKSPACE}/bin:${PATH}"
                    fi
                    trivy image --exit-code 0 --severity CRITICAL --no-progress --insecure ${FULL_IMAGE} || true
                '''
            }
        }

        stage('Push Image') {
            steps {
                sh "docker push ${FULL_IMAGE}"
            }
        }

        stage('Deploy') {
            steps {
                // GitOps: commit the new image tag to Git. ArgoCD (selfHeal+automated)
                // reconciles the cluster from Git, so it becomes the single deployer.
                withCredentials([usernamePassword(
                    credentialsId: 'github-creds',
                    usernameVariable: 'GIT_USER',
                    passwordVariable: 'GIT_TOKEN'
                )]) {
                    sh '''
                        set -e
                        # Update the deployment manifest with the new image tag (in-cluster registry name)
                        sed -i "s|image:.*|image: ${CLUSTER_IMAGE}|" k8s/deployment.yaml

                        git config user.email "jenkins@platform.local"
                        git config user.name "Jenkins CI"
                        git add k8s/deployment.yaml

                        if git diff --cached --quiet; then
                            echo "No image change to commit."
                        else
                            git commit -m "ci: deploy ${IMAGE_NAME}:${IMAGE_TAG} [skip ci]"
                            git push "https://${GIT_USER}:${GIT_TOKEN}@github.com/mayank-gokarna/platform.git" \
                                "HEAD:${DEPLOY_BRANCH}"
                        fi

                        # Optional: ask ArgoCD to sync immediately instead of waiting for poll
                        if command -v argocd >/dev/null 2>&1 && [ -n "${ARGOCD_AUTH_TOKEN:-}" ]; then
                            argocd app sync sample-app --grpc-web || true
                        fi
                    '''
                }
            }
        }
    }

    post {
        always {
            dir('sample-app') {
                sh 'rm -rf .venv || true'
            }
        }
        success {
            echo "Build ${env.BUILD_NUMBER} succeeded — image: ${FULL_IMAGE}"
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed"
        }
    }
}
