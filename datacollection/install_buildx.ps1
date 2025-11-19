# Check if Docker is installed
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker is not installed. Please install Docker Desktop and start it first."
    exit 1
}

# Enable Docker Buildx experimental feature
Write-Host "Enabling Docker Buildx..."
docker buildx version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Unable to enable Buildx. Please ensure Docker Desktop version supports Buildx."
    exit 1
}

# List available builders to verify Buildx is working
Write-Host "Listing available builders..."
docker buildx ls

Write-Host "Docker Buildx configuration completed! You can now use 'docker buildx build' to build multi-architecture images."