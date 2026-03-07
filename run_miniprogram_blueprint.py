"""
小程序蓝本测试执行器
每个场景独立启动桥接服务器，确保状态完全隔离。

用法：echo 60427 | poetry run python run_miniprogram_blueprint.py
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.controller.miniprogram import MiniProgramController, MiniProgramConfig


async def run_scenario(name, desc, port, test_fn):
    """独立运行一个场景：启动连接 → 执行测试 → 关闭连接。"""
    print(f"\n{'─' * 50}")
    print(f"场景: {name}")
    print(f"描述: {desc}")
    print(f"{'─' * 50}")

    config = MiniProgramConfig(
        project_path=r"D:\projects\TestPilotAI\miniprogram-demo",
        screenshot_dir="screenshots/miniprogram_blueprint",
        automation_port=port,
        timeout_ms=30000,
    )
    ctrl = MiniProgramController(config)

    try:
        await ctrl.launch()
        # 确保在首页
        page = await ctrl.get_current_page()
        if page.get("path", "") != "pages/index/index":
            # 回到首页
            await ctrl._call_bridge("navigateBack", {})
            await asyncio.sleep(0.5)
            # 清空购物车
            await ctrl._call_bridge("evaluate", {"code": "getApp().globalData.cart = []"})
            await asyncio.sleep(0.2)
            await ctrl._call_bridge("setPageData", {
                "data": {"cartCount": 0, "cartTotal": "0", "message": "", "msgClass": ""}
            })
            await asyncio.sleep(0.2)
        else:
            # 在首页也清空购物车
            await ctrl._call_bridge("evaluate", {"code": "getApp().globalData.cart = []"})
            await asyncio.sleep(0.2)
            await ctrl._call_bridge("setPageData", {
                "data": {"cartCount": 0, "cartTotal": "0", "message": "", "msgClass": ""}
            })
            await asyncio.sleep(0.2)
        print("  [准备] 已回到首页，购物车已清空")
        result = await test_fn(ctrl)
        return result
    except Exception as e:
        print(f"  ❌ 执行异常: {e}")
        return {"name": name, "status": "error", "message": str(e)}
    finally:
        await ctrl.close()


async def bug1_test(ctrl):
    """Bug1: 机械键盘页面显示199，加入购物车后变599。"""
    # 读取页面显示价格
    price = await ctrl.get_text("#price-2")
    print(f"  [1] 机械键盘页面显示价格: {price}")

    # 点击机械键盘的"加入购物车"
    await ctrl.tap(".product:nth-child(3) .btn-primary")
    await asyncio.sleep(0.5)
    print(f"  [2] 点击机械键盘'加入购物车'")

    # 读取购物车总计
    total = await ctrl.get_text("#cartTotal")
    print(f"  [3] 购物车总计: {total}")

    # 验证：页面显示199，但购物车应该也是199
    if "199" in price and "599" in total:
        msg = f"页面显示{price}，购物车却变成{total}，价格不一致！"
        print(f"\n  🐛 发现Bug: {msg}")
        return {"name": "Bug1-机械键盘价格不一致", "status": "bug_found", "message": msg}
    else:
        msg = f"页面={price}，购物车={total}"
        print(f"\n  ✅ 通过: {msg}")
        return {"name": "Bug1-机械键盘价格不一致", "status": "passed", "message": msg}


async def bug2_test(ctrl):
    """Bug2: 耳机(299)+扩展坞(159)总价应为458.00，但有浮点误差。"""
    # 点击无线耳机
    await ctrl.tap(".product:nth-child(2) .btn-primary")
    await asyncio.sleep(0.3)
    print(f"  [1] 点击无线耳机'加入购物车'")

    # 点击扩展坞
    await ctrl.tap(".product:nth-child(4) .btn-primary")
    await asyncio.sleep(0.3)
    print(f"  [2] 点击扩展坞'加入购物车'")

    # 读取购物车总计
    total = await ctrl.get_text("#cartTotal")
    print(f"  [3] 购物车总计: {total}")

    # 验证：299+159=458，总计应为"总计: 458.00"
    if "458.00" not in total:
        msg = f"总计={total}，期望'总计: 458.00'，出现浮点误差！"
        print(f"\n  🐛 发现Bug: {msg}")
        return {"name": "Bug2-浮点精度", "status": "bug_found", "message": msg}
    else:
        msg = f"总计={total}，正常"
        print(f"\n  ✅ 通过: {msg}")
        return {"name": "Bug2-浮点精度", "status": "passed", "message": msg}


async def bug3_test(ctrl):
    """Bug3: 空购物车点'查看购物车'应提示，不应直接跳转。"""
    # 确认在首页
    page = await ctrl.get_current_page()
    print(f"  [1] 当前页面: {page.get('path', '')}")

    # 点击"查看购物车"按钮
    await ctrl.tap("#cartTotal ~ .btn-primary")
    await asyncio.sleep(1.0)
    print(f"  [2] 点击'查看购物车'")

    # 获取跳转后的页面
    page = await ctrl.get_current_page()
    current = page.get("path", "")
    print(f"  [3] 跳转后页面: {current}")

    # 验证：空购物车应提示，不应跳转到cart页面
    if "cart/cart" in current:
        msg = f"空购物车直接跳转到{current}，应该提示'购物车为空'而非跳转！"
        print(f"\n  🐛 发现Bug: {msg}")
        return {"name": "Bug3-空购物车跳转", "status": "bug_found", "message": msg}
    else:
        msg = f"当前页面={current}，未跳转"
        print(f"\n  ✅ 通过: {msg}")
        return {"name": "Bug3-空购物车跳转", "status": "passed", "message": msg}


async def bug4_test(ctrl):
    """Bug4: 添加全部商品(总价>500)后到购物车结算，应成功但报500错误。"""
    # 添加3个商品
    await ctrl.tap(".product:nth-child(2) .btn-primary")
    await asyncio.sleep(0.3)
    print(f"  [1] 加入无线耳机(299)")

    await ctrl.tap(".product:nth-child(3) .btn-primary")
    await asyncio.sleep(0.3)
    print(f"  [2] 加入机械键盘(199→实际599)")

    await ctrl.tap(".product:nth-child(4) .btn-primary")
    await asyncio.sleep(0.3)
    print(f"  [3] 加入扩展坞(159)")

    total = await ctrl.get_text("#cartTotal")
    print(f"  [4] 购物车总计: {total}")

    # 跳转到购物车页面
    await ctrl.tap("#cartTotal ~ .btn-primary")
    await asyncio.sleep(1.0)
    print(f"  [5] 跳转到购物车页面")

    # 读取购物车页面总价
    cart_total = await ctrl.get_text("#totalPrice")
    print(f"  [6] 购物车页面总价: {cart_total}")

    # 点击结算按钮
    await ctrl.tap(".btn-primary")
    await asyncio.sleep(0.5)
    print(f"  [7] 点击'结算'")

    # 读取结算消息
    message = await ctrl.get_text("#cartMessage")
    print(f"  [8] 结算消息: {message}")

    # 验证：总价>500应该结算成功，但Bug导致报500错误
    if "错误" in message or "Error" in message or "500" in message:
        msg = f"总计={total}，结算消息='{message}'，大金额结算报错！"
        print(f"\n  🐛 发现Bug: {msg}")
        return {"name": "Bug4-大金额结算报错", "status": "bug_found", "message": msg}
    elif "成功" in message:
        msg = f"总计={total}，结算消息='{message}'，正常"
        print(f"\n  ✅ 通过: {msg}")
        return {"name": "Bug4-大金额结算报错", "status": "passed", "message": msg}
    else:
        msg = f"总计={total}，结算消息='{message}'（意外结果）"
        print(f"\n  ⚠️ 意外: {msg}")
        return {"name": "Bug4-大金额结算报错", "status": "error", "message": msg}


async def main():
    print("=" * 60)
    print("  BuggyMini 小程序蓝本测试")
    print("  预埋4个Bug，验证自动化测试能否发现")
    print("=" * 60)

    port_str = input("\n请输入WebSocket端口号（如 60427）: ").strip()
    if not port_str.isdigit():
        print("端口号必须是数字！")
        return
    port = int(port_str)

    start_time = time.time()
    results = []

    scenarios = [
        ("Bug1-机械键盘价格不一致", "页面显示199但加入购物车变599", bug1_test),
        ("Bug2-浮点精度", "耳机+扩展坞总价应为458整数", bug2_test),
        ("Bug3-空购物车跳转", "空购物车点查看应提示而非跳转", bug3_test),
        ("Bug4-大金额结算报错", "总价>500结算应成功但报500错误", bug4_test),
    ]

    for name, desc, test_fn in scenarios:
        result = await run_scenario(name, desc, port, test_fn)
        results.append(result)

    # 汇总报告
    print("\n" + "=" * 60)
    print("  测试报告")
    print("=" * 60)

    bugs = sum(1 for r in results if r["status"] == "bug_found")
    passed = sum(1 for r in results if r["status"] == "passed")
    errors = sum(1 for r in results if r["status"] == "error")

    for r in results:
        icon = {"bug_found": "🐛", "passed": "✅", "error": "⚠️"}.get(r["status"], "?")
        print(f"  {icon} {r['name']}: {r['message'][:70]}")

    elapsed = time.time() - start_time
    print(f"\n  总计: {len(results)} 场景 | 🐛 Bug: {bugs} | ✅ 通过: {passed} | ⚠️ 异常: {errors} | 耗时: {elapsed:.1f}秒")
    print("=" * 60)

    if bugs == 4:
        print("\n🎉 完美！成功发现所有4个预埋Bug！")
    elif bugs > 0:
        print(f"\n⚠️ 发现 {bugs}/4 个Bug，还有 {4 - bugs} 个未检测到。")
    else:
        print("\n❌ 未发现任何Bug。")


if __name__ == "__main__":
    asyncio.run(main())
