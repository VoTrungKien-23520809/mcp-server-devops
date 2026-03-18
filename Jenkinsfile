pipeline {
    agent any

    options {
        timestamps() // Thêm thời gian vào log để dễ soi lỗi
        disableConcurrentBuilds() // Không cho phép chạy 2 build cùng lúc để tránh xung đột
    }

    environment {
        DOCKER_HUB_USER = "kienvo2110"
        APP_NAME = "mcp-server-app"
        IMAGE_REPO = "${DOCKER_HUB_USER}/${APP_NAME}"
        K8S_NAMESPACE = "staging"
        K8S_DEPLOYMENT = "mcp-server-deployment"
    }

    stages {
        stage('Checkout & Metadata') {
            steps {
                echo 'Fetching the latest code from GitHub...'
                checkout scm
                script {
                    // Tạo mã định danh duy nhất dựa trên Build Number và mã commit Git
                    env.GIT_SHA = sh(returnStdout: true, script: 'git rev-parse --short=8 HEAD').trim()
                    env.IMAGE_TAG = "${env.BUILD_NUMBER}-${env.GIT_SHA}"
                    env.IMAGE_REF = "${env.IMAGE_REPO}:${env.IMAGE_TAG}"
                }
                echo "📦 Phiên bản build: ${env.IMAGE_REF}"
            }
        }

        stage('Unit Test') {
            steps {
                echo 'Running Python Unit Tests...'
                sh '''
                #!/usr/bin/env bash
                set -e
                rm -rf venv
                python3 -m venv venv
                ./venv/bin/pip install --upgrade pip
                ./venv/bin/pip install -r requirements.txt
                ./venv/bin/python -m pytest test_main.py 
                '''
                echo '✅ Unit Test thành công!'
            }
        }

        stage('Security Analysis') {
            parallel {
                stage('SonarQube') {
                    steps {
                        script {
                            def scannerHome = tool 'sonar-scanner'
                            withSonarQubeEnv('sonar-server') {
                                sh "${scannerHome}/bin/sonar-scanner -Dsonar.projectKey=mcp-server-devops -Dsonar.sources=. -Dsonar.python.version=3"
                            }
                        }
                    }
                }
                stage('Checkov Scan') {
                    steps {
                        sh 'checkov -d . --soft-fail'
                    }
                }
            }
        }

        stage('Build & Push Docker') {
            steps {
                echo "Building & Pushing image: ${env.IMAGE_REF}..."
                sh "docker build -t ${env.IMAGE_REF} -t ${env.IMAGE_REPO}:latest ."
                withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials', passwordVariable: 'DOCKER_PASS', usernameVariable: 'DOCKER_USER')]) {
                    sh "echo \$DOCKER_PASS | docker login -u \$DOCKER_USER --password-stdin"
                    sh "docker push ${env.IMAGE_REF}"
                    sh "docker push ${env.IMAGE_REPO}:latest"
                }
            }
        }

        stage('Deploy to K3s (Staging)') {
            steps {
                echo 'Deploying to K3s...'
                sh '''
                #!/usr/bin/env bash
                set -e
                export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
                
                # Áp dụng cấu hình và ép K3s dùng đúng phiên bản vừa build
                kubectl apply -f k8s/staging-deployment.yaml
                kubectl -n ${K8S_NAMESPACE} set image deployment/${K8S_DEPLOYMENT} mcp-server=${DOCKER_HUB_USER}/${APP_NAME}:latest
                
                # Đợi hệ thống ổn định trong 120s, nếu không xong là báo lỗi
                kubectl rollout status deployment/${K8S_DEPLOYMENT} -n ${K8S_NAMESPACE} --timeout=120s
                '''
                echo '✅ Deployment thành công!'
            }
        }
    }

    post {
        failure {
            echo '❌ Build thất bại! Đang tự động Rollback về phiên bản ổn định gần nhất...'
            sh '''
            export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
            kubectl rollout undo deployment/${K8S_DEPLOYMENT} -n ${K8S_NAMESPACE}
            '''
        }
        always {
            echo '🧹 Dọn dẹp tài nguyên thừa...'
            sh 'docker image prune -f || true'
        }
    }
}