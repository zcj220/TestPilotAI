#!/bin/bash
cd /opt/testpilot/app
source venv/bin/activate
python3 -c "
from src.auth.database import engine
from sqlalchemy import text
with engine.connect() as conn:
    r = conn.execute(text('SHOW TABLES'))
    tables = [row[0] for row in r]
    print('Tables:', tables)
    print('Count:', len(tables))
"
