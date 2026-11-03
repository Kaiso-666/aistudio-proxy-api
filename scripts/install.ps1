# AI Studio Proxy API 一键安装脚本 (Windows PowerShell)
# 使用 Poetry 进行依赖管理

# 设置错误处理
$ErrorActionPreference = "Stop"

# 颜色函数
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Log-Info {
    param([string]$Message)
    Write-ColorOutput "[INFO] $Message" "Blue"
}

function Log-Success {
    param([string]$Message)
    Write-ColorOutput "[SUCCESS] $Message" "Green"
}

function Log-Warning {
    param([string]$Message)
    Write-ColorOutput "[WARNING] $Message" "Yellow"
}

function Log-Error {
    param([string]$Message)
    Write-ColorOutput "[ERROR] $Message" "Red"
}

# 检查命令是否存在
function Test-Command {
    param([string]$Command)
    try {
        Get-Command $Command -ErrorAction Stop | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

# 检查 Python 版本
function Test-Python {
    Log-Info "检查 Python 版本..."
    
    $pythonCmd = $null
    if (Test-Command "python") {
        $pythonCmd = "python"
    }
    elseif (Test-Command "py") {
        $pythonCmd = "py"
    }
    else {
        Log-Error "未找到 Python。请先安装 Python 3.9+"
        exit 1
    }
    
    try {
        $pythonVersion = & $pythonCmd --version 2>&1
        $versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
        
        if ($versionMatch) {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            
            if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 9)) {
                Log-Error "Python 版本过低: $pythonVersion。需要 Python 3.9+"
                exit 1
            }
            
            Log-Success "Python 版本: $pythonVersion ✓"
            return $pythonCmd
        }
        else {
            Log-Error "无法解析 Python 版本"
            exit 1
        }
    }
    catch {
        Log-Error "Python 版本检查失败: $_"
        exit 1
    }
}

# 安装 Poetry
function Install-Poetry {
    if (Test-Command "poetry") {
        Log-Success "Poetry 已安装 ✓"
        return
    }
    
    Log-Info "安装 Poetry..."
    try {
        (Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -
        
        # 刷新环境变量
        $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH", "User")
        
        if (Test-Command "poetry") {
            Log-Success "Poetry 安装成功 ✓"
        }
        else {
            Log-Error "Poetry 安装失败。请手动安装 Poetry"
            exit 1
        }
    }
    catch {
        Log-Error "Poetry 安装失败: $_"
        exit 1
    }
}

# 克隆项目
function Clone-Project {
    Log-Info "克隆项目..."
    
    if (Test-Path "AIstudioProxyAPI") {
        Log-Warning "项目目录已存在，跳过克隆"
        Set-Location "AIstudioProxyAPI"
    }
    else {
        try {
            git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
            Set-Location "AIstudioProxyAPI"
            Log-Success "项目克隆成功 ✓"
        }
        catch {
            Log-Error "项目克隆失败: $_"
            exit 1
        }
    }
}

# 安装依赖
function Install-Dependencies {
    Log-Info "安装项目依赖..."
    try {
        poetry install
        Log-Success "依赖安装成功 ✓"
    }
    catch {
        Log-Error "依赖安装失败: $_"
        exit 1
    }
}

# 下载 Camoufox
function Download-Camoufox {
    Log-Info "下载 Camoufox 浏览器..."
    try {
        poetry run camoufox fetch
        Log-Success "Camoufox 下载成功 ✓"
    }
    catch {
        Log-Warning "Camoufox 下载失败，但不影响主要功能: $_"
    }
}

# 安装 Playwright 依赖
function Install-PlaywrightDeps {
    Log-Info "安装 Playwright 依赖..."
    try {
        poetry run playwright install-deps firefox
    }
    catch {
        Log-Warning "Playwright 依赖安装失败，但不影响主要功能"
    }
}

# 创建配置文件
function Create-Config {
    Log-Info "创建配置文件..."
    
    if (!(Test-Path ".env") -and (Test-Path ".env.example")) {
        Copy-Item ".env.example" ".env"
        Log-Success "配置文件创建成功 ✓"
        Log-Info "请编辑 .env 文件进行个性化配置"
    }
    else {
        Log-Warning "配置文件已存在或模板不存在"
    }
}

# 验证安装
function Test-Installation {
    Log-Info "验证安装..."
    
    try {
        # 检查 Poetry 环境
        poetry env info | Out-Null
        
        # 检查关键依赖
        poetry run python -c "import fastapi, playwright, camoufox"
        
        Log-Success "安装验证成功 ✓"
    }
    catch {
        Log-Error "安装验证失败: $_"
        exit 1
    }
}

# 显示后续步骤
function Show-NextSteps {
    Write-Host ""
    Log-Success "🎉 安装完成！"
    Write-Host ""
    Write-Host "后续步骤："
    Write-Host "1. 进入项目目录: cd AIstudioProxyAPI"
    Write-Host "2. 激活虚拟环境: poetry env activate"
    Write-Host "3. 配置环境变量: notepad .env"
    Write-Host "4. 首次认证设置: poetry run python launch_camoufox.py --debug"
    Write-Host "5. 日常运行: poetry run python launch_camoufox.py --headless"
    Write-Host ""
    Write-Host "详细文档："
    Write-Host "- 快速开始: docs/quick-start.md"
    Write-Host "- 配置参考: docs/configuration-reference.md"
    Write-Host "- 认证与轮转: docs/auth-rotation-cookie-refresh.md"
    Write-Host ""
}

# 主函数
function Main {
    Write-Host "🚀 AI Studio Proxy API 一键安装脚本"
    Write-Host "使用 Poetry 进行现代化依赖管理"
    Write-Host ""

    $pythonCmd = Test-Python
    Install-Poetry
    Clone-Project
    Install-Dependencies
    Download-Camoufox
    Install-PlaywrightDeps
    Create-Config
    Test-Installation
    Show-NextSteps
}

# 运行主函数
try {
    Main
}
catch {
    Log-Error "安装过程中发生错误: $_"
    exit 1
}
