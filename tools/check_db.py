import os, sys
sys.path.insert(0, '/opt/testpilot/app')

# 加载 .env
with open('/opt/testpilot/app/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip()

from sqlalchemy import create_engine, text
engine = create_engine(os.environ['DATABASE_URL'])

with engine.connect() as conn:
    tables = conn.execute(text('SHOW TABLES')).fetchall()
    print('=== 现有表 ===')
    for t in tables: print(' ', t[0])
    
    # 检查 alembic_version
    if any('alembic_version' in str(t) for t in tables):
        ver = conn.execute(text('SELECT * FROM alembic_version')).fetchall()
        print('=== alembic 已执行版本 ===')
        for v in ver: print(' ', v[0])
    
    # 检查 users 表结构
    if any('users' in str(t) for t in tables):
        cols = conn.execute(text('DESCRIBE users')).fetchall()
        print('=== users 表结构 ===')
        for c in cols: print(f'  {c[0]:20} {c[1]}')

print('=== 检查完成 ===')
