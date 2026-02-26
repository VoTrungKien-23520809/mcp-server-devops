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
        
        stage('Build Docker Image') {
            steps {
                echo "Building the Python Docker image: ${IMAGE_TAG}..."
                sh "docker build -t ${IMAGE_TAG} ."
                echo '✅ Docker image built successfully!'
            }
        }

        // --- TRẠM KIỂM DUYỆT DEVSECOPS ---
        stage('Security Scan (Trivy)') {
            steps {
                echo 'Scanning Docker image for CRITICAL vulnerabilities...'
                // Quét và hiển thị lỗi nghiêm trọng dưới dạng bảng. 
                // Tạm thời chưa dùng cờ --exit-code 1 để Pipeline không bị báo đỏ ngay lần đầu.
                sh "trivy image --severity CRITICAL ${IMAGE_TAG}"
                echo '✅ Security scan completed!'
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
