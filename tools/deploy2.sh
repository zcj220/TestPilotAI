#!/bin/bash
set -e
cd /opt/testpilot/app
set -a; source .env; set +a
source venv/bin/activate
echo "DB: ${DATABASE_URL:0:70}"
echo "--- alembic upgrade ---"
alembic upgrade head
echo "--- restart backend ---"
pkill -f "uvicorn src.app:app" 2>/dev/null || true
sleep 1
nohup python -m uvicorn src.app:app --host 0.0.0.0 --port 8900 > logs/app.log 2>&1 &
sleep 4
curl -s http://127.0.0.1:8900/api/v1/health
echo ""
echo "--- build frontend ---"
cd /opt/testpilot/app/web
[ -d node_modules ] || npm install 2>&1 | tail -3
npm run build 2>&1 | tail -6
sudo rm -rf /var/www/testpilot/*
sudo cp -r dist/* /var/www/testpilot/
sudo chown -R www-data:www-data /var/www/testpilot/
ls /var/www/testpilot/
echo "=== DONE ==="
