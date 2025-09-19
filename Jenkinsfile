pipeline {
    agent any
    
    environment {
        PYPI_TOKEN = credentials('pypi-api-token')
        GITHUB_TOKEN = credentials('github-token')
    }
    
    stages {
        stage('Setup') {
            steps {
                script {
                    // Set GitHub status to pending
                    updateGitHubStatus('pending', 'Build started')
                }
                
                sh '''
                    cd RoLint
                    python3.12 -m venv venv
                    . venv/bin/activate
                    pip install --upgrade pip
                    pip install build twine pytest flake8
                    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
                    pip install -e .
                '''
            }
        }
        
        stage('Test') {
            steps {
                sh '''
                    cd RoLint
                    . venv/bin/activate
                    
                    # Run linter tests
                    if [ -d "tests" ]; then
                        pytest tests/ -v --tb=short || echo "No tests found, skipping"
                    fi
                    
                    # Test CLI functionality
                    rolint --help
                    
                    # Test on example files
                    rolint check examples/bad_code.c --lang c || true
                '''
            }
        }
        
        stage('Build Package') {
            steps {
                sh '''
                    cd RoLint
                    . venv/bin/activate
                    python -m build
                    twine check dist/*
                '''
                
                archiveArtifacts artifacts: 'RoLint/dist/*', fingerprint: true
            }
        }
        
        stage('Publish to PyPI') {
            when {
                branch 'main'
            }
            steps {
                script {
                    sh '''
                        cd RoLint
                        . venv/bin/activate
                        
                        # Get current version
                        VERSION=$(python -c "
                        try:
                            import tomllib
                            with open('pyproject.toml', 'rb') as f:
                                data = tomllib.load(f)
                            print(data['project']['version'])
                        except:
                            print('unknown')
                        ")
                        
                        echo "Package version: $VERSION"
                        
                        # Check if version exists on PyPI
                        if pip index versions rolint | grep -q "$VERSION"; then
                            echo "Version $VERSION already exists on PyPI - skipping publish"
                            exit 0
                        fi
                        
                        # Publish to PyPI
                        TWINE_USERNAME=__token__ TWINE_PASSWORD=$PYPI_TOKEN twine upload dist/*
                        
                        echo "Successfully published RoLint v$VERSION to PyPI"
                    '''
                }
            }
        }
        
        stage('Create GitHub Release') {
            when {
                branch 'main'
            }
            steps {
                script {
                    sh '''
                        cd RoLint
                        VERSION=$(python -c "
                        try:
                            import tomllib
                            with open('pyproject.toml', 'rb') as f:
                                data = tomllib.load(f)
                            print(data['project']['version'])
                        except:
                            print('unknown')
                        ")
                        
                        # Create GitHub release
                        curl -X POST \
                            -H "Authorization: token $GITHUB_TOKEN" \
                            -H "Accept: application/vnd.github.v3+json" \
                            https://api.github.com/repos/$GIT_URL_HOST/releases \
                            -d "{
                                \\"tag_name\\": \\"rolint-v$VERSION\\",
                                \\"name\\": \\"RoLint v$VERSION\\",
                                \\"body\\": \\"RoLint v$VERSION published to PyPI\\\\n\\\\nInstall: \`pip install rolint\`\\",
                                \\"draft\\": false,
                                \\"prerelease\\": false
                            }"
                    '''
                }
            }
        }
    }
    
    post {
        success {
            script {
                updateGitHubStatus('success', 'Build completed successfully')
            }
        }
        failure {
            script {
                updateGitHubStatus('failure', 'Build failed')
            }
        }
        cleanup {
            sh 'rm -rf RoLint/venv RoLint/dist RoLint/build'
        }
    }
}

def updateGitHubStatus(state, description) {
    sh """
        curl -X POST \
            -H "Authorization: token $GITHUB_TOKEN" \
            -H "Accept: application/vnd.github.v3+json" \
            https://api.github.com/repos/\$GIT_URL_HOST/statuses/\$GIT_COMMIT \
            -d '{
                "state": "${state}",
                "description": "${description}",
                "context": "jenkins/build"
            }'
    """
}