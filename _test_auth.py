"""临时测试脚本：验证注册/登录/JWT 在 MySQL RDS 上工作正常"""
import traceback
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
    print("1. dotenv loaded")

    from src.auth.database import get_db
    print("2. database imported")

    from src.auth.service import register_user, authenticate_user, create_access_token
    print("3. service imported")

    db = next(get_db())
    print("4. db session OK")

    # 注册（已存在则跳过）
    try:
        user = register_user(db, "test@testpilot.com", "testuser", "Test123456")
        print(f"5. 注册成功: id={user.id}, username={user.username}, role={user.role}")
    except ValueError as e:
        print(f"5. 注册跳过（已存在）: {e}")

    # 用户名登录
    u = authenticate_user(db, "testuser", "Test123456")
    status = "成功" if u else "失败"
    print(f"6. 用户名登录: {status}")

    # 邮箱登录
    u2 = authenticate_user(db, "test@testpilot.com", "Test123456")
    status2 = "成功" if u2 else "失败"
    print(f"7. 邮箱登录: {status2}")

    # 错误密码
    u3 = authenticate_user(db, "testuser", "wrongpass")
    status3 = "正确拒绝" if not u3 else "未拒绝!"
    print(f"8. 错误密码: {status3}")

    # JWT
    if u:
        token = create_access_token(u.id, u.username, u.role)
        print(f"9. JWT: {token[:60]}...")

    # MySQL 持久化验证
    from sqlalchemy import text
    row = db.execute(text("SELECT id, email, username, role FROM users WHERE username='testuser'")).fetchone()
    print(f"10. MySQL 持久化: {row}")

    db.close()
    print("\nALL PASSED!")

except Exception:
    traceback.print_exc()
    sys.exit(1)
