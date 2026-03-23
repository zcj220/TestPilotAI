"""检查 testpilot_db 里已有哪些表"""
import pymysql

conn = pymysql.connect(
    host='rm-bp1t95uj3l81oe1c8oo.mysql.rds.aliyuncs.com',
    port=3306,
    user='zhuiyibian_1',
    password='zcj220@like',
    database='testpilot_db',
    charset='utf8mb4'
)
cur = conn.cursor()
cur.execute('SHOW TABLES')
tables = [row[0] for row in cur.fetchall()]
print('testpilot_db 现有表:', tables)

# 查 alembic_version
if 'alembic_version' in tables:
    cur.execute('SELECT * FROM alembic_version')
    rows = cur.fetchall()
    print('alembic_version:', rows)
else:
    print('alembic_version: 表不存在')

conn.close()
