"""
TestPilot AI CLI 命令行工具（v10.0）

CI/CD 和命令行用户的入口，支持无头模式执行测试。

使用方式：
    # 一键启动引擎（自动检查环境）
    python cli.py serve
    python cli.py serve --open          # 启动后自动打开浏览器
    python cli.py serve --force         # 端口占用时强制启动

    # 蓝本模式测试
    python cli.py run --blueprint testpilot.json
    python cli.py run --blueprint testpilot.json --base-url http://localhost:3000

    # 探索模式测试
    python cli.py explore --url http://localhost:3000 --description "电商网站"

    # 生成蓝本模板
    python cli.py init --name "我的应用" --url http://localhost:3000

    # 健康检查
    python cli.py health

    # MCP 闭环测试（在 Cascade 聊天中）
    # 说 "帮我修复" 即可自动 测试→发现Bug→修复代码→重测

退出码：
    0 = 测试全部通过
    1 = 存在失败的测试或Bug
    2 = 运行错误（引擎未启动、文件不存在等）
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path 中
root = Path(__file__).parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))


def cmd_serve(args: argparse.Namespace) -> int:
    """一键启动 TestPilot AI 引擎服务（v10.0 增强版）。

    自动检查：端口占用、Playwright浏览器、AI密钥配置
    自动动作：打开浏览器访问仪表盘（可选）
    """
    import uvicorn
    import socket
    import subprocess
    import os
    from src.core.config import get_config

    config = get_config()
    host = args.host or config.server.host
    port = args.port or config.server.port

    print("=" * 55)
    print("  🤖 TestPilot AI 一键启动")
    print("=" * 55)
    print()

    # ── 环境检查 ──────────────────────────────────

    all_ok = True

    # 1. 检查端口占用
    print("  [1/4] 检查端口...", end=" ")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        if result == 0:
            print(f"⚠️  端口 {port} 已被占用")
            print(f"         可能引擎已在运行，或请换一个端口: --port {port + 1}")
            if not args.force:
                print(f"         使用 --force 强制启动")
                return 2
            print(f"         --force 模式，继续启动...")
        else:
            print(f"✅ 端口 {port} 可用")
    finally:
        sock.close()

    # 2. 检查 Playwright 浏览器
    print("  [2/4] 检查浏览器...", end=" ")
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        try:
            browser = pw.chromium.launch(headless=True)
            browser.close()
            print("✅ Playwright Chromium 就绪")
        except Exception:
            print("⚠️  Playwright 浏览器未安装")
            print("         正在自动安装...")
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
            )
            print("         ✅ 浏览器安装完成")
        finally:
            pw.stop()
    except ImportError:
        print("❌ playwright 未安装")
        print("         请执行: pip install playwright && python -m playwright install chromium")
        all_ok = False

    # 3. 检查 AI 密钥
    print("  [3/4] 检查AI配置...", end=" ")
    if config.ai.api_key:
        key_preview = config.ai.api_key[:8] + "..." + config.ai.api_key[-4:]
        print(f"✅ API Key 已配置 ({key_preview})")
    else:
        print("⚠️  TP_AI_API_KEY 未配置（测试功能不可用）")
        print("         请在 .env 文件中设置: TP_AI_API_KEY=你的密钥")

    # 4. 检查仪表盘
    print("  [4/4] 检查仪表盘...", end=" ")
    dashboard_dist = Path(__file__).parent / "desktop" / "dist"
    if dashboard_dist.is_dir():
        print("✅ Web仪表盘已构建")
    else:
        print("⚠️  Web仪表盘未构建（仅API可用）")

    print()

    if not all_ok:
        print("❌ 环境检查未通过，请修复上述问题后重试")
        return 2

    # ── 启动引擎 ──────────────────────────────────

    base_url = f"http://{host}:{port}"
    print("─" * 55)
    print(f"  🚀 引擎启动中...")
    print(f"     地址:     {base_url}")
    print(f"     API文档:  {base_url}/docs")
    print(f"     健康检查: {base_url}/api/v1/health")
    print(f"     WebSocket: ws://{host}:{port}/ws")
    print()
    print("  💡 在 Windsurf/VSCode 中使用:")
    print("     • 命令面板搜索 'TestPilot AI' 查看所有命令")
    print("     • 或在Cascade聊天中说: '帮我测试 http://localhost:3000'")
    print()
    print("  🔄 MCP 闭环测试:")
    print("     在 Cascade 聊天中说 '帮我修复' 即可自动测试→修复→重测")
    print("─" * 55)
    print()

    # 自动打开浏览器（可选）
    if args.open_browser:
        import threading
        import webbrowser

        def _open_after_delay():
            """等引擎启动后再打开浏览器。"""
            import time
            time.sleep(2)
            webbrowser.open(base_url)

        threading.Thread(target=_open_after_delay, daemon=True).start()

    uvicorn.run(
        "src.app:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """检查引擎健康状态。"""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{args.port}/api/v1/health"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            print(f"✅ 引擎状态: {data.get('status', 'unknown')}")
            print(f"   版本: {data.get('version', '?')}")
            print(f"   浏览器: {'就绪' if data.get('browser_ready') else '未启动'}")
            print(f"   沙箱数: {data.get('sandbox_count', 0)}")
            return 0
    except urllib.error.URLError:
        print(f"❌ 无法连接引擎 ({url})")
        print(f"   请先运行: python cli.py serve")
        return 2
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")
        return 2


def cmd_run(args: argparse.Namespace) -> int:
    """执行蓝本模式测试。"""
    blueprint_path = Path(args.blueprint)
    if not blueprint_path.exists():
        print(f"❌ 蓝本文件不存在: {blueprint_path}")
        return 2

    # 通过HTTP API调用引擎执行测试
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{args.port}/api/v1/test/blueprint"
    payload = {
        "blueprint_path": str(blueprint_path.resolve()),
    }
    if args.base_url:
        payload["base_url"] = args.base_url

    print(f"🧪 蓝本测试开始...")
    print(f"   蓝本: {blueprint_path}")
    if args.base_url:
        print(f"   URL:  {args.base_url}")
    print()

    start_time = time.time()

    try:
        req_data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            report = json.loads(resp.read().decode())
    except urllib.error.URLError:
        print(f"❌ 无法连接引擎 (http://127.0.0.1:{args.port})")
        print(f"   请先运行: python cli.py serve")
        return 2
    except Exception as e:
        print(f"❌ 测试执行失败: {e}")
        return 2

    duration = time.time() - start_time

    # 输出结果
    _print_report(report, duration)

    # 保存报告文件
    if args.output:
        _save_report(report, args.output, args.format)

    # 退出码：有Bug则返回1
    if report.get("bug_count", 0) > 0 or report.get("pass_rate", 1) < 1.0:
        return 1
    return 0


def cmd_explore(args: argparse.Namespace) -> int:
    """执行探索模式测试。"""
    import urllib.request
    import urllib.error

    url = f"http://127.0.0.1:{args.port}/api/v1/test/explore"
    payload = {
        "url": args.url,
        "description": args.description or "",
        "focus": args.focus or "核心功能",
    }

    print(f"🔍 探索测试开始...")
    print(f"   URL:  {args.url}")
    if args.description:
        print(f"   描述: {args.description}")
    print(f"   重点: {args.focus or '核心功能'}")
    print()

    start_time = time.time()

    try:
        req_data = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=600) as resp:
            report = json.loads(resp.read().decode())
    except urllib.error.URLError:
        print(f"❌ 无法连接引擎 (http://127.0.0.1:{args.port})")
        print(f"   请先运行: python cli.py serve")
        return 2
    except Exception as e:
        print(f"❌ 测试执行失败: {e}")
        return 2

    duration = time.time() - start_time
    _print_report(report, duration)

    if args.output:
        _save_report(report, args.output, args.format)

    if report.get("bug_count", 0) > 0 or report.get("pass_rate", 1) < 1.0:
        return 1
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """生成蓝本模板文件。"""
    template = {
        "app_name": args.name or "我的应用",
        "base_url": args.url or "http://localhost:3000",
        "pages": [
            {
                "name": "首页",
                "path": "/",
                "scenarios": [
                    {
                        "name": "页面加载",
                        "steps": [
                            {
                                "action": "navigate",
                                "target": args.url or "http://localhost:3000",
                                "description": "打开首页",
                            },
                            {
                                "action": "screenshot",
                                "description": "截图验证首页加载",
                                "expected": "页面正常显示",
                            },
                        ],
                    }
                ],
            }
        ],
    }

    output_path = Path(args.output or "testpilot.json")
    if output_path.exists() and not args.force:
        print(f"❌ 文件已存在: {output_path}")
        print(f"   使用 --force 强制覆盖")
        return 2

    output_path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 蓝本模板已生成: {output_path}")
    print(f"   请编辑此文件，添加你的测试步骤和选择器。")
    return 0


def cmd_mobile(args: argparse.Namespace) -> int:
    """手机测试相关命令。"""
    import urllib.request
    import urllib.error

    base = f"http://127.0.0.1:{args.port}/api/v1"
    sub = getattr(args, "mobile_command", None)

    if not sub:
        print("请指定子命令: devices | appium | connect | screenshot | sessions")
        print("  python cli.py mobile devices     列出已连接设备")
        print("  python cli.py mobile appium      检查Appium状态")
        print("  python cli.py mobile connect      连接设备")
        print("  python cli.py mobile sessions     列出活跃会话")
        return 0

    if sub == "devices":
        try:
            req = urllib.request.Request(f"{base}/mobile/devices")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                devices = data.get("devices", [])
                if not devices:
                    print("📱 未检测到已连接的Android设备")
                    if data.get("error"):
                        print(f"   ⚠️ {data['error']}")
                    print("   请确保: USB调试已开启 + 设备已连接 + adb已安装")
                else:
                    print(f"📱 检测到 {len(devices)} 台设备:")
                    for d in devices:
                        model = d.get("model", "未知型号")
                        print(f"   • {d['serial']} ({model})")
                return 0
        except urllib.error.URLError:
            print(f"❌ 无法连接引擎，请先运行: python cli.py serve")
            return 2

    elif sub == "appium":
        try:
            req = urllib.request.Request(f"{base}/mobile/appium/status")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                if data.get("running"):
                    print("✅ Appium Server 运行中")
                else:
                    print("❌ Appium Server 未运行")
                    print("   请执行: npm install -g appium && appium")
                return 0
        except urllib.error.URLError:
            print(f"❌ 无法连接引擎，请先运行: python cli.py serve")
            return 2

    elif sub == "connect":
        payload = {
            "device_name": args.device,
            "app_package": args.package,
            "app_activity": args.activity,
            "app_path": args.apk,
        }
        try:
            req_data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{base}/mobile/session/create",
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
                print(f"✅ {data.get('message', '连接成功')}")
                print(f"   会话ID: {data.get('session_id')}")
                device = data.get("device", {})
                print(f"   设备: {device.get('name', '未知')}")
                return 0
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else ""
            print(f"❌ 连接失败: {body}")
            return 1
        except urllib.error.URLError:
            print(f"❌ 无法连接引擎，请先运行: python cli.py serve")
            return 2

    elif sub == "screenshot":
        session_id = args.session
        try:
            req = urllib.request.Request(f"{base}/mobile/session/{session_id}/screenshot")
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode())
                print(f"📸 截图已保存: {data.get('path', '未知')}")
                return 0
        except urllib.error.HTTPError as e:
            print(f"❌ 截图失败: {e.read().decode() if e.fp else e}")
            return 1
        except urllib.error.URLError:
            print(f"❌ 无法连接引擎")
            return 2

    elif sub == "sessions":
        try:
            req = urllib.request.Request(f"{base}/mobile/sessions")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                sessions = data.get("sessions", [])
                if not sessions:
                    print("📱 没有活跃的手机测试会话")
                else:
                    print(f"📱 {len(sessions)} 个活跃会话:")
                    for s in sessions:
                        device = s.get("device", {})
                        print(f"   • {s['session_id']} → {device.get('name', '未知')}")
                return 0
        except urllib.error.URLError:
            print(f"❌ 无法连接引擎")
            return 2

    return 0


def _print_report(report: dict, duration: float) -> None:
    """在终端打印测试报告。"""
    pass_rate = report.get("pass_rate", 0)
    total = report.get("total_steps", 0)
    passed = report.get("passed_steps", 0)
    failed = report.get("failed_steps", 0)
    bugs = report.get("bug_count", 0)

    # 状态图标
    icon = "✅" if pass_rate >= 1.0 else "⚠️" if pass_rate >= 0.8 else "❌"

    print("─" * 50)
    print(f"{icon} 测试完成")
    print(f"─" * 50)
    print(f"  测试名称: {report.get('test_name', '未知')}")
    print(f"  通过率:   {pass_rate * 100:.0f}% ({passed}/{total})")
    print(f"  失败步骤: {failed}")
    print(f"  发现Bug:  {bugs}")
    print(f"  耗时:     {duration:.1f}s")

    if report.get("fixed_bug_count"):
        print(f"  自动修复: {report['fixed_bug_count']}个")

    print(f"─" * 50)

    # 显示Bug列表
    if bugs > 0 and report.get("report_markdown"):
        lines = report["report_markdown"].split("\n")
        in_bug_section = False
        for line in lines:
            if "Bug" in line and "#" in line:
                in_bug_section = True
            elif in_bug_section and line.startswith("#"):
                break
            elif in_bug_section and line.strip():
                print(f"  {line.strip()}")

    print()


def _save_report(report: dict, output_path: str, fmt: str) -> None:
    """保存报告到文件。"""
    path = Path(output_path)

    if fmt == "json":
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "markdown" or fmt == "md":
        md = report.get("report_markdown", "")
        if not md:
            md = _report_to_markdown(report)
        path.write_text(md, encoding="utf-8")
    elif fmt == "junit":
        xml = _report_to_junit_xml(report)
        path.write_text(xml, encoding="utf-8")
    elif fmt == "html":
        html = _report_to_html(report)
        path.write_text(html, encoding="utf-8")
    else:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"📄 报告已保存: {path} ({fmt})")


def _report_to_markdown(report: dict) -> str:
    """将报告转为Markdown格式。"""
    lines = [
        f"# TestPilot AI 测试报告",
        f"",
        f"- **测试名称**: {report.get('test_name', '未知')}",
        f"- **URL**: {report.get('url', '')}",
        f"- **通过率**: {report.get('pass_rate', 0) * 100:.0f}%",
        f"- **步骤**: {report.get('passed_steps', 0)}/{report.get('total_steps', 0)} 通过",
        f"- **Bug数量**: {report.get('bug_count', 0)}",
        f"- **耗时**: {report.get('duration_seconds', 0):.1f}s",
        f"",
    ]
    return "\n".join(lines)


def _report_to_junit_xml(report: dict) -> str:
    """将报告转为JUnit XML格式（CI/CD系统标准格式）。"""
    total = report.get("total_steps", 0)
    failures = report.get("failed_steps", 0)
    bugs = report.get("bug_count", 0)
    duration = report.get("duration_seconds", 0)
    name = report.get("test_name", "TestPilot AI Test")

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<testsuites tests="{total}" failures="{failures}" errors="0" time="{duration:.1f}">',
        f'  <testsuite name="{name}" tests="{total}" failures="{failures}" errors="0" time="{duration:.1f}">',
    ]

    # 每个步骤作为一个testcase
    for i in range(total):
        step_name = f"Step {i + 1}"
        if i < total - failures:
            lines.append(f'    <testcase name="{step_name}" time="0">')
            lines.append(f'    </testcase>')
        else:
            lines.append(f'    <testcase name="{step_name}" time="0">')
            lines.append(f'      <failure message="测试步骤失败">Bug detected by TestPilot AI</failure>')
            lines.append(f'    </testcase>')

    lines.append(f'  </testsuite>')
    lines.append(f'</testsuites>')
    return "\n".join(lines)


def _report_to_html(report: dict) -> str:
    """将报告转为HTML格式。"""
    pass_rate = report.get("pass_rate", 0)
    color = "#22c55e" if pass_rate >= 1.0 else "#eab308" if pass_rate >= 0.8 else "#ef4444"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>TestPilot AI 测试报告</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; background: #0f172a; color: #e2e8f0; }}
  h1 {{ color: #818cf8; }}
  .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
  .stat {{ background: #1e293b; border-radius: 12px; padding: 16px; text-align: center; }}
  .stat-value {{ font-size: 28px; font-weight: bold; color: {color}; }}
  .stat-label {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
  .report {{ background: #1e293b; border-radius: 12px; padding: 20px; white-space: pre-wrap; font-family: monospace; font-size: 13px; }}
</style>
</head>
<body>
<h1>TestPilot AI 测试报告</h1>
<div class="stats">
  <div class="stat"><div class="stat-value">{pass_rate * 100:.0f}%</div><div class="stat-label">通过率</div></div>
  <div class="stat"><div class="stat-value">{report.get('passed_steps', 0)}/{report.get('total_steps', 0)}</div><div class="stat-label">步骤</div></div>
  <div class="stat"><div class="stat-value">{report.get('bug_count', 0)}</div><div class="stat-label">Bug</div></div>
  <div class="stat"><div class="stat-value">{report.get('duration_seconds', 0):.1f}s</div><div class="stat-label">耗时</div></div>
</div>
<div class="report">{report.get('report_markdown', '无详细报告')}</div>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="testpilot",
        description="TestPilot AI - AI驱动的自动化测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python cli.py serve                              启动引擎
  python cli.py run --blueprint testpilot.json      蓝本测试
  python cli.py run -b test.json -o report.xml -f junit   导出JUnit报告
  python cli.py explore --url http://localhost:3000  探索测试
  python cli.py init --name "我的应用"               生成蓝本模板
  python cli.py health                              健康检查
        """,
    )
    parser.add_argument("--port", type=int, default=8900, help="引擎端口 (默认: 8900)")

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # serve（一键启动）
    p_serve = subparsers.add_parser("serve", help="一键启动 TestPilot AI 引擎（自动检查环境）")
    p_serve.add_argument("--host", default=None, help="监听地址")
    p_serve.add_argument("--reload", action="store_true", help="开发模式热重载")
    p_serve.add_argument("--log-level", default="info", help="日志级别")
    p_serve.add_argument("--force", action="store_true", help="端口占用时强制启动")
    p_serve.add_argument("--open", dest="open_browser", action="store_true", help="启动后自动打开浏览器")

    # run (蓝本测试)
    p_run = subparsers.add_parser("run", help="执行蓝本模式测试")
    p_run.add_argument("-b", "--blueprint", required=True, help="蓝本文件路径 (testpilot.json)")
    p_run.add_argument("--base-url", default=None, help="覆盖蓝本中的base_url")
    p_run.add_argument("-o", "--output", default=None, help="报告输出路径")
    p_run.add_argument("-f", "--format", default="json", choices=["json", "markdown", "md", "junit", "html"], help="报告格式 (默认: json)")

    # explore (探索测试)
    p_explore = subparsers.add_parser("explore", help="执行探索模式测试")
    p_explore.add_argument("--url", required=True, help="被测应用URL")
    p_explore.add_argument("--description", default="", help="应用描述")
    p_explore.add_argument("--focus", default="核心功能", help="测试重点")
    p_explore.add_argument("-o", "--output", default=None, help="报告输出路径")
    p_explore.add_argument("-f", "--format", default="json", choices=["json", "markdown", "md", "junit", "html"], help="报告格式")

    # init (生成模板)
    p_init = subparsers.add_parser("init", help="生成蓝本模板文件")
    p_init.add_argument("--name", default="我的应用", help="应用名称")
    p_init.add_argument("--url", default="http://localhost:3000", help="应用URL")
    p_init.add_argument("-o", "--output", default="testpilot.json", help="输出路径")
    p_init.add_argument("--force", action="store_true", help="强制覆盖已存在的文件")

    # health
    subparsers.add_parser("health", help="检查引擎健康状态")

    # mobile (手机测试 v5.0)
    p_mobile = subparsers.add_parser("mobile", help="手机测试相关命令")
    mobile_sub = p_mobile.add_subparsers(dest="mobile_command", help="手机测试子命令")

    mobile_sub.add_parser("devices", help="列出已连接的手机设备")
    mobile_sub.add_parser("appium", help="检查 Appium Server 状态")

    p_mobile_connect = mobile_sub.add_parser("connect", help="连接手机设备并创建测试会话")
    p_mobile_connect.add_argument("--device", default="", help="设备名称")
    p_mobile_connect.add_argument("--package", default="", help="Android 包名")
    p_mobile_connect.add_argument("--activity", default="", help="启动 Activity")
    p_mobile_connect.add_argument("--apk", default="", help="APK 文件路径")

    p_mobile_screenshot = mobile_sub.add_parser("screenshot", help="截取手机屏幕")
    p_mobile_screenshot.add_argument("--session", required=True, help="会话ID")

    mobile_sub.add_parser("sessions", help="列出活跃的手机测试会话")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "serve": cmd_serve,
        "run": cmd_run,
        "explore": cmd_explore,
        "init": cmd_init,
        "health": cmd_health,
        "mobile": cmd_mobile,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
