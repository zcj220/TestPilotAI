#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/opt/testpilot/app')
os.chdir('/opt/testpilot/app')
from src.auth.database import engine
from sqlalchemy import text, inspect

with engine.connect() as conn:
    r = conn.execute(text('SHOW TABLES'))
    tables = sorted([row[0] for row in r])
    print('=== 数据库中的表 (%d个) ===' % len(tables))
    for t in tables:
        print(' ', t)

print()
print('=== 检查关键表是否存在 ===')
required = ['users','api_keys','credit_transactions','shared_experiences',
            'experience_votes','user_badges','user_profiles','teams','team_members',
            'projects','debug_snapshots','usage_records',
            'login_attempts','refresh_tokens','email_verifications']
insp = inspect(engine)
existing = insp.get_table_names()
for t in required:
    status = '✅' if t in existing else '❌ 缺失!'
    print(f'  {status} {t}')
