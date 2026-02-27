pipeline {
    agent any

    environment {
        DOCKER_HUB_USER = "kienvo2110"
        APP_NAME = "mcp-server-app"
        IMAGE_TAG = "${DOCKER_HUB_USER}/${APP_NAME}:latest"
    }

    stages {
        stage('Checkout Code') {
            steps {
                echo 'Fetching the latest code from GitHub...'
                checkout scm
                echo '✅ Code checkout successful!'
            }
        }

        stage('Unit Test') {
            steps {
                echo 'Running Python Unit Tests...'
                sh '''
                # Tạo môi trường ảo và cài thư viện
                python3 -m venv venv
                . venv/bin/activate
                pip install -r requirements.txt
                
                # Chạy test
                pytest test_main.py
                '''
                echo '✅ All tests passed successfully!'
            }
        }
  
        stage('Soi Code (SonarQube Analysis)') {
            steps {
                // Gọi cái máy soi đã cài ở bước 1 ra xài
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
                // Quét thư mục hiện tại. Bỏ qua lỗi nhẹ (--soft-fail) để tránh sập Pipeline.
                sh 'checkov -d . --soft-fail'
                echo '✅ IaC scan completed!'
            }
        }
        
        stage('Build Docker Image') {
            steps {
                echo "Building the Python Docker image: ${IMAGE_TAG}..."
                sh "docker build -t ${IMAGE_TAG} ."
                echo '✅ Docker image built successfully!'
            }
        }

        stage('Security Scan (Trivy)') {
            steps {
                echo 'Quét lỗi bảo mật nghiêm trọng trong Docker image...'
                
                // Thêm cờ --exit-code 1: Có lỗi là báo đỏ Pipeline ngay lập tức
                sh "trivy image --db-repository ghcr.io/aquasecurity/trivy-db:2 --severity CRITICAL --exit-code 1 ${IMAGE_TAG}"
                
                echo '✅ Đã quét xong, không phát hiện lỗi CRITICAL!'
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo 'Pushing the image to Docker Hub...'
                withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials', passwordVariable: 'DOCKER_PASS', usernameVariable: 'DOCKER_USER')]) {
                    sh '''
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        docker push ''' + "${IMAGE_TAG}" + '''
                    '''
                }
                echo '✅ Image successfully pushed to Docker Hub Registry!'
            }
        }
    }
}
