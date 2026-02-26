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

        stage('Security Scan (Trivy)') {
            steps {
                echo 'Quét lỗi bảo mật nghiêm trọng trong Docker image...'
                // Ép Trivy tải database từ ghcr.io thay vì gcr.io bị lỗi 404
                sh "trivy image --db-repository ghcr.io/aquasecurity/trivy-db:2 --severity CRITICAL ${IMAGE_TAG}"
                echo '✅ Đã quét xong!'
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
