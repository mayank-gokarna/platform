pipeline {
    agent any

    environment {
        REGISTRY       = 'localhost:5001'
        CLUSTER_REGISTRY = 'kind-registry:5000'
        IMAGE_NAME     = 'sample-app'
        IMAGE_TAG      = "${env.BUILD_NUMBER}"
        FULL_IMAGE     = "${REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
        CLUSTER_IMAGE  = "${CLUSTER_REGISTRY}/${IMAGE_NAME}:${IMAGE_TAG}"
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
                sh """
                    # Update the deployment manifest with the new image tag (use in-cluster registry name)
                    sed -i 's|image:.*|image: ${CLUSTER_IMAGE}|' k8s/deployment.yaml
                    kubectl apply -f k8s/deployment.yaml
                    kubectl apply -f k8s/service.yaml
                """
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
            echo "Build ${env.BUILD_NUMBER} succeeded \u2014 image: ${FULL_IMAGE}"
        }
        failure {
            echo "Build ${env.BUILD_NUMBER} failed"
        }
    }
}
