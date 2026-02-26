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
                echo '⏳ Docker build command will be added later...'
            }
        }
    }
}
