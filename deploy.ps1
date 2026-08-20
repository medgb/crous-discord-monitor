# ===================================================================
# CROUS Monitor - 1-Click Cloud Deployment Script
# ===================================================================

# Configure via environment variables or update the defaults below
$SSH_KEY = if ($env:CROUS_SSH_KEY) { $env:CROUS_SSH_KEY } else { "path/to/your/ssh_key.key" }
$VPS_IP = if ($env:CROUS_VPS_IP) { $env:CROUS_VPS_IP } else { "YOUR_VPS_IP_HERE" }
$VPS_USER = if ($env:CROUS_VPS_USER) { $env:CROUS_VPS_USER } else { "ubuntu" }
$REMOTE_DIR = if ($env:CROUS_REMOTE_DIR) { $env:CROUS_REMOTE_DIR } else { "/home/$VPS_USER/crous-monitor" }

if ($VPS_IP -eq "YOUR_VPS_IP_HERE") {
    Write-Host "Error: Please set the CROUS_VPS_IP environment variable or configure `$VPS_IP in deploy.ps1" -ForegroundColor Red
    exit 1
}

Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "Deploying CROUS Monitor to Cloud VPS ($VPS_IP)..." -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan

# 1. Upload updated files to VPS
Write-Host "`n[1/3] Uploading local files to VPS..." -ForegroundColor Yellow
scp -i $SSH_KEY -o BatchMode=yes -r src tests Dockerfile docker-compose.yml requirements.txt .env pytest.ini README.md "${VPS_USER}@${VPS_IP}:${REMOTE_DIR}/"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to upload files to VPS. Check network connection or SSH key." -ForegroundColor Red
    exit 1
}

# 2. Rebuild and restart the Docker container on the VPS
Write-Host "`n[2/3] Rebuilding and Restarting Docker container on VPS..." -ForegroundColor Yellow
ssh -i $SSH_KEY -o BatchMode=yes "${VPS_USER}@${VPS_IP}" "cd ${REMOTE_DIR}; sudo docker compose up -d --build"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Failed to reload Docker container on VPS." -ForegroundColor Red
    exit 1
}

# 3. Fetch latest live logs from the cloud
Write-Host "`n[3/3] Verifying live status on VPS..." -ForegroundColor Yellow
ssh -i $SSH_KEY -o BatchMode=yes "${VPS_USER}@${VPS_IP}" "cd ${REMOTE_DIR}; sudo docker compose logs --tail=10"

Write-Host "`n=======================================================" -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE! Cloud monitor is up to date!" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
