"""
修复服务器配置：
1. 把 .env 的数据库名改回 testpilot_db
2. 用 zhuiyibian_1 账号尝试创建 testpilot_db 数据库
3. 执行 alembic 建表
4. 重启后端
"""
import os, sys, subprocess

# 加载 zhuiyibian_db 的连接信息（用于创建新数据库）
DB_USER = "zhuiyibian_1"
DB_PASS = "zcj220%40like"   # URL编码的 @
DB_PASS_PLAIN = "zcj220@like"
DB_HOST = "rm-bp1t95uj3l81oe1c8oo.mysql.rds.aliyuncs.com"
DB_PORT = 3306
NEW_DB = "testpilot_db"

APP_DIR = "/opt/testpilot/app"
ENV_FILE = f"{APP_DIR}/.env"

print("=== Step 1: 修改 .env 数据库名 ===")
with open(ENV_FILE, 'r') as f:
    content = f.read()

# 把 zhuiyibian_db 改回 testpilot_db
content = content.replace('zhuiyibian_db', 'testpilot_db')
with open(ENV_FILE, 'w') as f:
    f.write(content)

# 验证
with open(ENV_FILE) as f:
    for line in f:
        if 'DATABASE' in line:
            print("  DATABASE_URL:", line.strip()[:80])

print("\n=== Step 2: 尝试创建 testpilot_db 数据库 ===")
sys.path.insert(0, APP_DIR)

# 先用原来的 zhuiyibian 连接建新数据库
base_url = f"mysql+pymysql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/zhuiyibian_db?charset=utf8mb4"
from sqlalchemy import create_engine, text

try:
    engine = create_engine(base_url)
    with engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {NEW_DB} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
        conn.commit()
        dbs = conn.execute(text("SHOW DATABASES")).fetchall()
        print("  所有数据库:", [d[0] for d in dbs])
    print(f"  ✅ {NEW_DB} 创建成功（或已存在）")
except Exception as e:
    print(f"  ❌ 创建数据库失败: {e}")
    print("  需要在阿里云控制台手动创建 testpilot_db 数据库")

print("\n=== Step 3: 执行 alembic 迁移 ===")
os.chdir(APP_DIR)
with open(ENV_FILE) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

result = subprocess.run(
    [f"{APP_DIR}/venv/bin/alembic", "upgrade", "head"],
    capture_output=True, text=True, cwd=APP_DIR,
    env={**os.environ}
)
print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr[-1000:])
    print("  ❌ 迁移失败")
else:
    print("  ✅ 迁移成功")

print("\n=== Step 4: 重启后端 ===")
subprocess.run("pkill -f 'uvicorn src.app:app' 2>/dev/null || true", shell=True)
import time; time.sleep(1)

proc = subprocess.Popen(
    f"cd {APP_DIR} && source venv/bin/activate && nohup python -m uvicorn src.app:app --host 0.0.0.0 --port 8900 > logs/app.log 2>&1 &",
    shell=True, executable="/bin/bash"
)
time.sleep(4)

import urllib.request
try:
    resp = urllib.request.urlopen("http://127.0.0.1:8900/api/v1/health", timeout=5)
    print("  ✅ 后端健康:", resp.read().decode()[:100])
except Exception as e:
    print("  ⚠️ 后端检查:", e)

print("\n=== 完成 ===")
