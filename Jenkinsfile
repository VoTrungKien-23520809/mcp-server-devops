pipeline {
    agent any

    // Khai báo biến môi trường cho gọn gàng và chuyên nghiệp
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
                // Build image và gắn thẳng tên user của bạn vào
                sh "docker build -t ${IMAGE_TAG} ."
                echo '✅ Docker image built successfully!'
            }
        }

        stage('Push to Docker Hub') {
            steps {
                echo 'Pushing the image to Docker Hub...'
                // Gọi chìa khóa dockerhub-credentials ra để đăng nhập
                withCredentials([usernamePassword(credentialsId: 'dockerhub-credentials', passwordVariable: 'DOCKER_PASS', usernameVariable: 'DOCKER_USER')]) {
                    sh '''
                        # Đăng nhập Docker Hub một cách bảo mật
                        echo "$DOCKER_PASS" | docker login -u "$DOCKER_USER" --password-stdin
                        
                        # Đẩy image lên kho
                        docker push ''' + "${IMAGE_TAG}" + '''
                    '''
                }
                echo '✅ Image successfully pushed to Docker Hub Registry!'
            }
        }
    }
}
