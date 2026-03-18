pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()
    }

    environment {
        DOCKER_HUB_USER = "kienvo2110"
        APP_NAME = "mcp-server-app"
        IMAGE_REPO = "${DOCKER_HUB_USER}/${APP_NAME}"
        K8S_NAMESPACE = "staging"
        K8S_DEPLOYMENT = "mcp-server-deployment"
    }

    stages {
        stage('Checkout Code') {
            steps {
                echo 'Fetching the latest code from GitHub...'
                checkout scm
                echo '✅ Code checkout successful!'
            }
        }

        stage('Prepare Build Metadata') {
            steps {
                script {
                    env.GIT_SHA = sh(returnStdout: true, script: 'git rev-parse --short=8 HEAD').trim()
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_SHA}"
                    env.IMAGE_REF = "${env.IMAGE_REPO}:${env.IMAGE_TAG}"
                }
                echo "Image to build: ${env.IMAGE_REF}"
            }
        }

        stage('Unit Test') {
            steps {
                echo 'Running Python Unit Tests...'
                sh '''
                #!/usr/bin/env bash
                set -e
                python3 -m venv venv
                . venv/bin/activate
                pip install --upgrade pip
                pip install -r requirements.txt

                pytest test_main.py
                '''
                echo '✅ All tests passed successfully!'
            }
        }
  
        stage('Soi Code (SonarQube Analysis)') {
            steps {
                // Gọi cái máy soi đã cài ở bước 1
                script {
                    def scannerHome = tool 'sonar-scanner'
                    withSonarQubeEnv('sonar-server') {
                        sh "${scannerHome}/bin/sonar-scanner \
                        -Dsonar.projectKey=mcp-server-devops \
                        -Dsonar.sources=. \
                        -Dsonar.exclusions=venv/**,**/*.pyc \
                        -Dsonar.python.version=3"
                    }
                }
            }
        }

        stage('IaC Security Scan (Checkov)') {
            steps {
                echo 'Scanning Terraform files with Checkov...'
                sh 'checkov -d terraform-jenkins --framework terraform --quiet'
                echo '✅ IaC scan completed!'
            }
        }
        
        stage('Build Docker Image') {
            steps {
                echo "Building the Python Docker image: ${env.IMAGE_REF}..."
                sh "docker build -t ${env.IMAGE_REF} ."
                echo '✅ Docker image built successfully!'
            }
        }

        stage('Security Scan (Trivy)') {
            steps {
                echo 'Scanning the Docker image for high and critical vulnerabilities...'
                sh "trivy image --db-repository ghcr.io/aquasecurity/trivy-db:2 --severity HIGH,CRITICAL --exit-code 1 ${env.IMAGE_REF}"
                echo '✅ Scan completed. No HIGH/CRITICAL issues detected!'
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo 'Pushing the image to Docker Hub...'
                withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials', passwordVariable: 'DOCKER_PASS', usernameVariable: 'DOCKER_USER')]) {
                    sh '''
                        #!/usr/bin/env bash
                        set -e
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker push ''' + "${IMAGE_REF}" + '''
                    '''
                }
                echo '✅ Image successfully pushed to Docker Hub Registry!'
            }
        }

        stage('Deploy to K3s (Staging)') {
            steps {
                echo 'Deploying application to K3s Staging environment...'
                sh '''
                #!/usr/bin/env bash
                set -e
                export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

                kubectl apply -f k8s/staging-deployment.yaml
                kubectl -n ${K8S_NAMESPACE} set image deployment/${K8S_DEPLOYMENT} mcp-server=${IMAGE_REF}
                kubectl rollout status deployment/${K8S_DEPLOYMENT} -n ${K8S_NAMESPACE} --timeout=120s
                '''
                echo '✅ Deployment to Staging successful!'
            }
        }
    }

    post {
        failure {
            echo 'Pipeline failed. Attempting automatic rollback...'
            sh '''
            #!/usr/bin/env bash
            set +e
            export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
            kubectl rollout undo deployment/${K8S_DEPLOYMENT} -n ${K8S_NAMESPACE}
            '''
        }
        always {
            sh 'docker image prune -f || true'
        }
    }
}
