# TestPilot AI — 腾讯云服务器部署备忘录

> 最后更新：2026-03-17

---

## 一、服务器信息

| 项目 | 值 |
|------|---|
| 云厂商 | 腾讯云轻量服务器 |
| 公网 IP | `82.157.97.179` |
| 域名 | `testpilop.xinzao.com` |
| 操作系统 | Ubuntu 24.04 LTS |
| SSH 密钥 | `D:\Projects\TestPilotAI\key\TestPilotAi.pem` |
| 应用目录 | `/opt/testpilot/app` |
| 前端静态目录 | `/var/www/testpilot` |
| 引擎端口 | `8900`（仅内网，Nginx 代理） |
| 社区网页 | `http://testpilop.xinzao.com` | 

---

## 二、SSH 登录

```bash
# Windows PowerShell
ssh -i "D:\Projects\TestPilotAI\key\TestPilotAi.pem" ubuntu@82.157.97.179

# macOS / Linux
ssh -i ~/.ssh/TestPilotAi.pem ubuntu@82.157.97.179
```

> 首次连接时 pem 文件权限需设为只读：
> - Windows：右键 pem → 属性 → 安全 → 仅保留自己账户的读取权限
> - Linux/Mac：`chmod 600 TestPilotAi.pem`

---

## 三、首次部署（从零开始）

```bash
# 1. 登录服务器
ssh -i "D:\Projects\TestPilotAI\key\TestPilotAi.pem" ubuntu@82.157.97.179

# 2. 上传并运行初始化脚本
scp -i "D:\Projects\TestPilotAI\key\TestPilotAi.pem" \
    D:\Projects\TestPilotAI\deploy\setup-server.sh \
    ubuntu@82.157.97.179:/tmp/setup-server.sh

ssh -i "D:\Projects\TestPilotAI\key\TestPilotAi.pem" ubuntu@82.157.97.179 \
    "sudo bash /tmp/setup-server.sh"

# 3. 配置环境变量
sudo cp /opt/testpilot/app/.env.example /opt/testpilot/app/.env
sudo nano /opt/testpilot/app/.env
# 必填项见第四节
```

---

## 四、.env 必填配置项

```env
# 数据库（PostgreSQL，社区功能必须）
TP_DATABASE_URL=postgresql+psycopg2://testpilot:密码@localhost:5432/testpilot

# JWT 密钥（随机字符串，生产环境必须修改）
JWT_SECRET_KEY=换成随机字符串至少32位

# 豆包 AI API 密钥
TP_AI_API_KEY=你的方舟平台密钥
TP_AI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
TP_AI_MODEL=doubao-seed-1-8-251228

# 禁用热重载（服务器上必须为 false）
TP_SERVER_RELOAD=false

# 仅监听本地（Nginx 代理，不对外暴露）
TP_SERVER_HOST=127.0.0.1
TP_SERVER_PORT=8900
```

---

## 五、Nginx 配置

```bash
# 复制配置文件
sudo cp /opt/testpilot/app/deploy/nginx-testpilot.conf \
    /etc/nginx/sites-available/testpilot

# 启用站点
sudo ln -sf /etc/nginx/sites-available/testpilot \
    /etc/nginx/sites-enabled/testpilot

# 删除默认站点（避免冲突）
sudo rm -f /etc/nginx/sites-enabled/default

# 测试配置
sudo nginx -t

# 重载
sudo systemctl reload nginx
```

---

## 六、systemd 服务（引擎守护进程）

```bash
# 复制服务文件
sudo cp /opt/testpilot/app/deploy/testpilot-api.service \
    /etc/systemd/system/testpilot-api.service

# 启用并启动
sudo systemctl daemon-reload
sudo systemctl enable testpilot-api
sudo systemctl start testpilot-api

# 查看状态
sudo systemctl status testpilot-api

# 查看日志（实时）
sudo journalctl -u testpilot-api -f
```

---

## 七、日常更新部署

```bash
# 本地：推送代码到 GitHub
git add . && git commit -m "更新说明" && git push

# 服务器：拉取并重建
ssh -i "D:\Projects\TestPilotAI\key\TestPilotAi.pem" ubuntu@82.157.97.179 << 'EOF'
cd /opt/testpilot/app
git pull

# 更新 Python 依赖（如有新库）
source venv/bin/activate
poetry install --no-interaction --only main

# 重建前端
cd web && npm ci && npm run build
sudo rm -rf /var/www/testpilot
sudo cp -r dist /var/www/testpilot
sudo chown -R www-data:www-data /var/www/testpilot

# 重启后端
sudo systemctl restart testpilot-api
EOF
```

---

## 八、SSL 证书（HTTPS）

```bash
# 使用 Let's Encrypt 申请免费证书
sudo certbot --nginx -d testpilopai.xinzao.com

# 自动续期（certbot 安装后已自动配置 cron）
sudo certbot renew --dry-run
```

> ⚠️ 申请证书前确保：
> - 域名 `testpilopai.xinzao.com` 已在 DNS 解析到 `82.157.97.179`
> - 服务器 80 端口未被防火墙屏蔽

---

## 九、PostgreSQL 数据库安装

```bash
# 安装
sudo apt-get install -y postgresql

# 创建数据库和用户
sudo -u postgres psql << 'EOF'
CREATE USER testpilot WITH PASSWORD '设置一个强密码';
CREATE DATABASE testpilot OWNER testpilot;
GRANT ALL PRIVILEGES ON DATABASE testpilot TO testpilot;
EOF

# 运行数据库迁移
cd /opt/testpilot/app
source venv/bin/activate
alembic upgrade head
```

---

## 十、常用排查命令

```bash
# 引擎健康检查
curl http://127.0.0.1:8900/api/v1/health

# 查看引擎日志
sudo journalctl -u testpilot-api -n 100

# 查看 Nginx 错误日志
sudo tail -f /var/log/nginx/error.log

# 查看磁盘空间
df -h

# 查看内存
free -h

# 重启所有服务
sudo systemctl restart testpilot-api nginx postgresql
```

---

## 十一、防火墙端口

腾讯云控制台 → 防火墙规则，需开放：

| 端口 | 协议 | 说明 |
|------|------|------|
| 22 | TCP | SSH |
| 80 | TCP | HTTP（Nginx） |
| 443 | TCP | HTTPS（SSL） |

> 8900 端口**不需要**对外开放，Nginx 内部代理即可。
