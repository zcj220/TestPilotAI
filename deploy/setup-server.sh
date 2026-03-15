#!/bin/bash
# ═══════════════════════════════════════════════════════
# TestPilot AI — 服务器初始化脚本
# 适用于：Ubuntu 24.04 LTS（腾讯云轻量服务器）
# 使用方式：bash setup-server.sh
# ═══════════════════════════════════════════════════════

set -e

echo "=== TestPilot AI 服务器初始化 ==="

# 1. 系统更新
echo "[1/7] 更新系统..."
apt-get update && apt-get upgrade -y

# 2. 安装基础工具
echo "[2/7] 安装基础工具..."
apt-get install -y \
    git curl wget unzip \
    python3 python3-pip python3-venv \
    nginx certbot python3-certbot-nginx \
    supervisor

# 3. 安装 Node.js 20 LTS（构建前端用）
echo "[3/7] 安装 Node.js 20..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi
echo "Node.js $(node -v) / npm $(npm -v)"

# 4. 创建应用目录和用户
echo "[4/7] 创建应用目录..."
mkdir -p /opt/testpilot
mkdir -p /opt/testpilot/logs

if ! id "testpilot" &>/dev/null; then
    useradd -r -s /bin/false -d /opt/testpilot testpilot
fi

# 5. 克隆项目
echo "[5/7] 拉取项目代码..."
if [ -d "/opt/testpilot/app" ]; then
    cd /opt/testpilot/app && git pull
else
    git clone https://github.com/zcj220/TestPilotAI.git /opt/testpilot/app
fi

# 6. 安装 Python 依赖
echo "[6/7] 安装 Python 依赖..."
cd /opt/testpilot/app
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install poetry
poetry config virtualenvs.create false
poetry install --no-interaction --only main

# 7. 构建前端
echo "[7/7] 构建前端..."
cd /opt/testpilot/app/web
npm ci --production=false
npm run build

# 复制前端到 Nginx 目录
rm -rf /var/www/testpilot
cp -r dist /var/www/testpilot

# 设置权限
chown -R testpilot:testpilot /opt/testpilot
chown -R www-data:www-data /var/www/testpilot

echo ""
echo "=== 初始化完成！==="
echo "接下来需要："
echo "  1. 编辑 /opt/testpilot/app/.env（填入数据库和密钥信息）"
echo "  2. 复制 Nginx 配置：cp deploy/nginx-testpilot.conf /etc/nginx/sites-available/testpilot"
echo "  3. 启用站点：ln -s /etc/nginx/sites-available/testpilot /etc/nginx/sites-enabled/"
echo "  4. 复制 systemd 服务：cp deploy/testpilot-api.service /etc/systemd/system/"
echo "  5. 启动服务：systemctl enable --now testpilot-api && systemctl restart nginx"
