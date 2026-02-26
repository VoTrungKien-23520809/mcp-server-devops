pipeline {
    agent any

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
                echo 'Building the Python Docker image for MCP Server...'
                // Lệnh đóng gói image với tag là latest
                sh 'docker build -t mcp-server-app:latest .'
                echo '✅ Docker image built successfully!'
            }
        }
    }
}
