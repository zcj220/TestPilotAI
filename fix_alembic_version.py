import sqlite3
conn = sqlite3.connect('data/testpilot.db')
cur = conn.cursor()
cur.execute("UPDATE alembic_version SET version_num='f03fbc681fc5'")
conn.commit()
print("version_num updated to f03fbc681fc5, rows:", cur.rowcount)
conn.close()
