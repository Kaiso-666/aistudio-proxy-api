#!/bin/bash

# AI Studio Proxy API 一键安装脚本 (macOS/Linux)
# 使用 Poetry 进行依赖管理

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 检查 Python 版本
check_python() {
    log_info "检查 Python 版本..."
    
    if command_exists python3; then
        PYTHON_CMD="python3"
    elif command_exists python; then
        PYTHON_CMD="python"
    else
        log_error "未找到 Python。请先安装 Python 3.9+"
        exit 1
    fi
    
    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d'.' -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d'.' -f2)
    
    if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]); then
        log_error "Python 版本过低: $PYTHON_VERSION。需要 Python 3.9+"
        exit 1
    fi
    
    log_success "Python 版本: $PYTHON_VERSION ✓"
}

# 安装 Poetry
install_poetry() {
    if command_exists poetry; then
        log_success "Poetry 已安装 ✓"
        return
    fi
    
    log_info "安装 Poetry..."
    curl -sSL https://install.python-poetry.org | $PYTHON_CMD -
    
    # 添加 Poetry 到 PATH
    export PATH="$HOME/.local/bin:$PATH"
    
    if command_exists poetry; then
        log_success "Poetry 安装成功 ✓"
    else
        log_error "Poetry 安装失败。请手动安装 Poetry"
        exit 1
    fi
}

# 克隆项目
clone_project() {
    log_info "克隆项目..."
    
    if [ -d "AIstudioProxyAPI" ]; then
        log_warning "项目目录已存在，跳过克隆"
        cd AIstudioProxyAPI
    else
        git clone https://github.com/CJackHwang/AIstudioProxyAPI.git
        cd AIstudioProxyAPI
        log_success "项目克隆成功 ✓"
    fi
}

# 安装依赖
install_dependencies() {
    log_info "安装项目依赖..."
    poetry install
    log_success "依赖安装成功 ✓"
}

# 下载 Camoufox
download_camoufox() {
    log_info "下载 Camoufox 浏览器..."
    poetry run camoufox fetch
    log_success "Camoufox 下载成功 ✓"
}

# 安装 Playwright 依赖
install_playwright_deps() {
    log_info "安装 Playwright 依赖..."
    poetry run playwright install-deps firefox || {
        log_warning "Playwright 依赖安装失败，但不影响主要功能"
    }
}

# 创建配置文件
create_config() {
    log_info "创建配置文件..."
    
    if [ ! -f ".env" ] && [ -f ".env.example" ]; then
        cp .env.example .env
        log_success "配置文件创建成功 ✓"
        log_info "请编辑 .env 文件进行个性化配置"
    else
        log_warning "配置文件已存在或模板不存在"
    fi
}

# 验证安装
verify_installation() {
    log_info "验证安装..."
    
    # 检查 Poetry 环境
    poetry env info >/dev/null 2>&1 || {
        log_error "Poetry 环境验证失败"
        exit 1
    }
    
    # 检查关键依赖
    poetry run python -c "import fastapi, playwright, camoufox" || {
        log_error "关键依赖验证失败"
        exit 1
    }
    
    log_success "安装验证成功 ✓"
}

# 显示后续步骤
show_next_steps() {
    echo
    log_success "🎉 安装完成！"
    echo
    echo "后续步骤："
    echo "1. 进入项目目录: cd AIstudioProxyAPI"
    echo "2. 激活虚拟环境: poetry env activate"
    echo "3. 配置环境变量: nano .env"
    echo "4. 首次认证设置: python launch_camoufox.py --debug"
    echo "5. 日常运行: python launch_camoufox.py --headless"
    echo
    echo "详细文档："
    echo "- 快速开始: docs/quick-start.md"
    echo "- 配置参考: docs/configuration-reference.md"
    echo "- 认证与轮转: docs/auth-rotation-cookie-refresh.md"
    echo
}

# 主函数
main() {
    echo "🚀 AI Studio Proxy API 一键安装脚本"
    echo "使用 Poetry 进行现代化依赖管理"
    echo

    check_python
    install_poetry
    clone_project
    install_dependencies
    download_camoufox
    install_playwright_deps
    create_config
    verify_installation
    show_next_steps
}

# 运行主函数
main "$@"
