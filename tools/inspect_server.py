"""
用密码连进腾讯云服务器，检查现状 + 添加 PEM 公钥到 authorized_keys
"""
import paramiko
import subprocess
import sys

HOST = "82.157.97.179"
USER = "root"
PASSWORD = "zcj220@like"
PEM_PATH = r"D:\Projects\TestPilotAI\key\TestPilotAi.pem"

def get_pubkey_from_pem(pem_path):
    """从 PEM 私钥提取公钥"""
    result = subprocess.run(
        ["ssh-keygen", "-y", "-f", pem_path],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print("无法提取公钥:", result.stderr)
        return None
    return result.stdout.strip()

def run(client, cmd, label=""):
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace").strip()
    err = stderr.read().decode("utf-8", errors="replace").strip()
    if label:
        print(f"\n=== {label} ===")
    if out:
        print(out)
    if err and "warning" not in err.lower():
        print("[stderr]", err)
    return out

def main():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    print(f"连接 {USER}@{HOST} ...")
    try:
        client.connect(HOST, username=USER, password=PASSWORD, timeout=15)
        print("✅ 连接成功！\n")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        sys.exit(1)

    # 1. 系统基本信息
    run(client, "uname -a && uptime", "系统信息")

    # 2. 磁盘和内存
    run(client, "df -h / && free -h", "磁盘/内存")

    # 3. 检查 /var/www 目录（当前部署的网站）
    run(client, "ls -la /var/www/ 2>/dev/null || echo '无 /var/www 目录'", "/var/www 目录")

    # 4. 检查 /opt 目录
    run(client, "ls /opt/ 2>/dev/null", "/opt 目录")

    # 5. Nginx 状态
    run(client, "systemctl is-active nginx; nginx -v 2>&1; ls /etc/nginx/sites-enabled/ 2>/dev/null", "Nginx 状态")

    # 6. 当前监听端口
    run(client, "ss -tlnp | grep -E 'LISTEN'", "监听端口")

    # 7. Python/Python3 版本
    run(client, "python3 --version 2>/dev/null; which python3", "Python")

    # 8. 正在运行的服务（testpilot 相关）
    run(client, "ps aux | grep -E 'python|uvicorn|gunicorn|node' | grep -v grep", "运行中的进程")

    # 9. systemd 服务
    run(client, "systemctl list-units --type=service --state=active | grep -v systemd | head -20", "活跃服务")

    # 10. 检查 /etc/nginx/sites-enabled 里的配置内容
    run(client, "cat /etc/nginx/sites-enabled/* 2>/dev/null || cat /etc/nginx/nginx.conf | head -60", "Nginx 配置")

    # 11. 添加 PEM 公钥到 authorized_keys
    print("\n=== 添加 PEM 公钥到 authorized_keys ===")
    pubkey = get_pubkey_from_pem(PEM_PATH)
    if pubkey:
        print(f"公钥提取成功: {pubkey[:60]}...")
        # 添加到 authorized_keys（去重）
        add_cmd = f"""
mkdir -p ~/.ssh
chmod 700 ~/.ssh
if ! grep -qF '{pubkey}' ~/.ssh/authorized_keys 2>/dev/null; then
    echo '{pubkey}' >> ~/.ssh/authorized_keys
    chmod 600 ~/.ssh/authorized_keys
    echo "✅ 公钥已添加"
else
    echo "✅ 公钥已存在，无需重复添加"
fi
"""
        run(client, add_cmd, "添加公钥")
    else:
        print("⚠️ 跳过添加公钥（提取失败）")

    client.close()
    print("\n=== 检查完成 ===")

if __name__ == "__main__":
    main()
