param(
    [Parameter(Mandatory = $false)]
    [string]$RepositoryUrl
)

# 检查Docker是否已安装
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker未安装，请先安装Docker Desktop并启动"
    exit 1
}

# 检查Buildx是否配置
Write-Host "检查Docker Buildx配置..."
# Check if buildx is working
docker buildx version 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Buildx配置未完成，正在运行配置脚本..."
    & "$PSScriptRoot\install_buildx.ps1"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Buildx配置失败"
        exit 1
    }
}

# 获取仓库URL
if ([string]::IsNullOrEmpty($RepositoryUrl)) {
    $RepositoryUrl = Read-Host "请输入镜像仓库URL (例如: docker.io/yourusername/freeark-data-collector)"
    if ([string]::IsNullOrEmpty($RepositoryUrl)) {
        Write-Error "仓库URL不能为空"
        exit 1
    }
}

# 检查是否已登录Docker仓库
Write-Host "检查Docker仓库登录状态..."
docker system info | Select-String -Pattern "Registry Mirrors" | Out-Null
# 简单检查，实际可能需要更准确的登录状态检查

# 构建并推送多架构镜像
Write-Host "开始构建多架构镜像..."
# Use the active desktop-linux builder which has running status
$BuildCommand = "docker buildx build --builder desktop-linux --platform linux/amd64,linux/arm64 -t ${RepositoryUrl}:latest -t ${RepositoryUrl}:$(Get-Date -Format 'yyyyMMddHHmmss') -f $($PSScriptRoot)\Dockerfile --push .."
Write-Host "执行命令: $BuildCommand"
Invoke-Expression $BuildCommand

if ($LASTEXITCODE -eq 0) {
    Write-Host "多架构镜像构建并推送成功！"
    Write-Host "镜像已推送到: ${RepositoryUrl}:latest"
} else {
    Write-Error "Image build or push failed"
    exit 1
}