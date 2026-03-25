import re

with open('/etc/nginx/sites-enabled/testpilot', 'r') as f:
    content = f.read()

auth_block = '''    # Auth 直接代理（插件直连，路径映射到 /api/v1/auth/）
    location /auth/ {
        proxy_pass http://127.0.0.1:8900/api/v1/auth/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    '''

if 'location /auth/' not in content:
    content = content.replace('    # API 代理', auth_block + '    # API 代理')
    with open('/etc/nginx/sites-enabled/testpilot', 'w') as f:
        f.write(content)
    print("OK: /auth/ block added")
else:
    print("SKIP: already exists")
