"""步骤2：创建 testpilot_db 数据库"""
import pymysql

try:
    conn = pymysql.connect(
        host='rm-bp1t95uj3l81oe1c8oo.mysql.rds.aliyuncs.com',
        port=3306,
        user='zhuiyibian_1',
        password='zcj220@like'
    )
    cur = conn.cursor()
    cur.execute('CREATE DATABASE IF NOT EXISTS testpilot_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
    conn.commit()
    cur.execute('SHOW DATABASES')
    dbs = [row[0] for row in cur.fetchall()]
    print('所有数据库:', dbs)
    if 'testpilot_db' in dbs:
        print('✅ testpilot_db 已存在')
    else:
        print('❌ 创建失败')
    conn.close()
except Exception as e:
    print('❌ 错误:', e)
