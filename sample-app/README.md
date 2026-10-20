# Sample Web Application

A lightweight, trusted Python HTTP service designed for CloudDeploy Lite deployment and verification.

## Features
- Listens on internal port `8080`.
- Provides `GET /health` returning `{"status": "ok", "app": "sample-app"}`.
- Provides `GET /` returning welcome JSON.
- Runs as non-root user `appuser` (UID 1000).

## Building and Running Locally

### Direct Python execution
```bash
python app.py
# Verify:
curl http://localhost:8080/health
```

### Docker build and run
```bash
# Build image
docker build -t clouddeploy-sample-app:latest .

# Run container with port forwarding to host port 8080
docker run -d --name sample-app-test -p 8080:8080 clouddeploy-sample-app:latest

# Check health
curl http://localhost:8080/health

# Stop and clean up
docker stop sample-app-test
docker rm sample-app-test
```

### Packaging for CloudDeploy Lite Upload
To package this app into a ZIP file for upload:
```bash
# In the sample-app/ directory:
zip -r sample-app.zip Dockerfile app.py
```
Ensure `Dockerfile` is placed directly at the root of the ZIP archive.
