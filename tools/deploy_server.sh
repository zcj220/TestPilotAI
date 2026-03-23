#!/bin/bash
# TestPilot 服务器部署脚本
# 在服务器上执行：bash /tmp/deploy_server.sh

set -e
cd /opt/testpilot/app

echo "=== 1. 加载环境变量 ==="
set -a
source .env
set +a
echo "DATABASE_URL 前60字符: ${DATABASE_URL:0:60}"

echo ""
echo "=== 2. 激活 venv ==="
source venv/bin/activate
python --version

echo ""
echo "=== 3. git pull 拉最新代码 ==="
git pull origin main 2>&1 || echo "警告: git pull 失败，继续..."

echo ""
echo "=== 4. 执行数据库迁移 ==="
alembic upgrade head 2>&1

echo ""
echo "=== 6. 重启后端服务 ==="
pkill -f "uvicorn src.app:app" 2>/dev/null || true
sleep 2
nohup python -m uvicorn src.app:app --host 0.0.0.0 --port 8900 --workers 1 > logs/app.log 2>&1 &
sleep 3
echo "后端 PID: $(pgrep -f 'uvicorn src.app:app' | head -1)"

echo ""
echo "=== 7. 验证后端 ==="
sleep 2
curl -s http://127.0.0.1:8900/api/v1/health && echo ""

echo ""
echo "=== 8. 构建并部署前端 ==="
echo "前端构建需要 Node.js，检查..."
node -v 2>/dev/null && npm -v 2>/dev/null || { echo "Node.js 未安装，跳过前端构建"; exit 0; }

# 构建 web 前端
cd /opt/testpilot/app/web
npm install -q 2>&1 | tail -3
npm run build 2>&1 | tail -5

# 部署到 /var/www/testpilot
echo "部署前端到 /var/www/testpilot ..."
sudo rm -rf /var/www/testpilot/*
sudo cp -r dist/* /var/www/testpilot/
sudo chown -R www-data:www-data /var/www/testpilot/

echo ""
echo "=== ✅ 部署完成 ==="
echo "访问: https://testpilot.xinzaoai.com"
