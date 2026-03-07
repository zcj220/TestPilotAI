"""
TestPilot AI MCP Server

让编程AI（Cursor/Windsurf等）通过MCP协议调用TestPilot的测试能力。
实现双向闭环：编程AI写代码 → TestPilot测试 → 报Bug → 编程AI修复 → 再测。

工具列表：
- run_blueprint_test: 按蓝本执行Web测试，返回Bug列表
- run_mobile_blueprint_test: 在Android手机浏览器上按蓝本测试
- run_miniprogram_test: 在微信小程序上按蓝本测试
- run_desktop_test: 在Windows桌面应用上按蓝本测试
- run_quick_test: 无蓝本快速测试（盲测模式）
- get_test_report: 获取最近的测试报告
- check_engine_health: 检查TestPilot引擎是否运行中
- generate_blueprint: AI自动生成蓝本（给URL全自动，兜底用）
- generate_blueprint_template: 生成蓝本模板框架（需手动补选择器）

启动方式：
    poetry run python -m src.mcp_server
"""

import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def _http_get(url: str, timeout: int = 10) -> tuple[int, str]:
    """标准库 HTTP GET。"""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except urllib.error.URLError as e:
        raise ConnectionError(str(e.reason))


def _http_post_json(url: str, data: dict, timeout: int = 600) -> tuple[int, str]:
    """标准库 HTTP POST JSON。"""
    try:
        body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode('utf-8')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except urllib.error.URLError as e:
        raise ConnectionError(str(e.reason))

# 创建 MCP Server
mcp = FastMCP("TestPilot AI")

# TestPilot 引擎地址
ENGINE_URL = "http://127.0.0.1:8900"

# 存储最近一次测试报告
_last_report: dict | None = None


@mcp.tool()
def run_blueprint_test(
    blueprint_path: str,
    base_url: str = "",
) -> str:
    """按蓝本（testpilot.json）执行精确测试，返回测试结果和Bug列表。

    编程AI写完代码后，应该先生成 testpilot.json 蓝本文件，
    然后调用此工具让 TestPilot 按蓝本精确测试。

    ⚠️ 蓝本管理规则（必须遵守）：
    - 每个被测应用目录下只允许一个 testpilot.json
    - 若已存在 testpilot.json，直接覆盖更新，禁止创建 _v2/_new/_backup 等变体
    - 蓝本文件必须放在被测应用根目录，固定命名 testpilot.json

    Args:
        blueprint_path: testpilot.json 蓝本文件的绝对路径
        base_url: 被测应用的URL（可选，覆盖蓝本中的base_url）

    Returns:
        测试报告（包含通过率、Bug列表、改进建议）
    """
    global _last_report

    # 验证文件存在
    if not Path(blueprint_path).exists():
        return f"❌ 蓝本文件不存在: {blueprint_path}\n请先生成 testpilot.json 文件。"

    try:
        status, text = _http_post_json(
            f"{ENGINE_URL}/api/v1/test/blueprint",
            {"blueprint_path": blueprint_path, "base_url": base_url},
        )

        if status != 200:
            return f"❌ 测试执行失败: {text}"

        data = json.loads(text)
        _last_report = data

        return _format_report(data)

    except ConnectionError:
        return (
            "❌ 无法连接 TestPilot 引擎。\n"
            "请确保引擎已启动：poetry run python main.py\n"
            f"引擎地址：{ENGINE_URL}"
        )
    except Exception as e:
        return f"❌ 测试异常: {str(e)}"


@mcp.tool()
def run_mobile_blueprint_test(
    blueprint_path: str,
    mobile_session_id: str = "",
    device_serial: str = "",
    base_url: str = "",
) -> str:
    """在真实 Android 手机上按蓝本执行测试（fix-test-fix 闭环）。

    与 run_blueprint_test 行为一致，但在手机浏览器上运行。
    如果 mobile_session_id 为空，会自动用第一台已连接设备创建 session。

    Args:
        blueprint_path: testpilot.json 蓝本文件的绝对路径
        mobile_session_id: 已有的 Session ID（空则自动创建）
        device_serial: Android 设备序列号（自动创建时使用）
        base_url: 覆盖蓝本中的 base_url（手机浏览器访问的地址）

    Returns:
        测试报告
    """
    global _last_report

    if not Path(blueprint_path).exists():
        return f"❌ 蓝本文件不存在: {blueprint_path}"

    # 如果没有提供 session_id，自动创建
    session_id = mobile_session_id
    if not session_id:
        try:
            create_body: dict = {}
            if device_serial:
                create_body["device_serial"] = device_serial
            status, text = _http_post_json(
                f"{ENGINE_URL}/api/v1/mobile/session/create",
                create_body,
                timeout=60,
            )
            if status != 200:
                return f"❌ 创建手机 Session 失败: {text}"
            data = json.loads(text)
            session_id = data.get("session_id", "")
            if not session_id:
                return f"❌ 创建手机 Session 失败：响应中无 session_id\n{text}"
        except ConnectionError:
            return (
                "❌ 无法连接 TestPilot 引擎。\n"
                "请确保引擎已启动：poetry run python main.py"
            )
        except Exception as e:
            return f"❌ 创建手机 Session 异常: {e}"

    try:
        status, text = _http_post_json(
            f"{ENGINE_URL}/api/v1/test/mobile-blueprint",
            {
                "blueprint_path": blueprint_path,
                "mobile_session_id": session_id,
                "base_url": base_url,
            },
            timeout=600,
        )

        if status != 200:
            return f"❌ 手机测试执行失败: {text}"

        data = json.loads(text)
        _last_report = data
        device_hint = f"\n- **Session**: {session_id}"
        return _format_report(data).replace(
            "# TestPilot 测试报告",
            f"# TestPilot 手机测试报告{device_hint}",
            1,
        )

    except ConnectionError:
        return (
            "❌ 无法连接 TestPilot 引擎。\n"
            "请确保引擎已启动：poetry run python main.py\n"
            f"引擎地址：{ENGINE_URL}"
        )
    except Exception as e:
        return f"❌ 手机测试异常: {str(e)}"


@mcp.tool()
def run_quick_test(
    url: str,
    description: str = "",
    focus: str = "核心功能",
) -> str:
    """无蓝本快速测试（AI自由探索模式）。

    适用于没有蓝本时的快速测试，AI会自行分析页面并生成测试步骤。
    注意：此模式准确率低于蓝本模式，建议优先使用蓝本模式。

    Args:
        url: 被测应用的URL
        description: 应用描述
        focus: 测试重点

    Returns:
        测试报告
    """
    global _last_report

    try:
        status, text = _http_post_json(
            f"{ENGINE_URL}/api/v1/test/run",
            {"url": url, "description": description, "focus": focus},
        )

        if status != 200:
            return f"❌ 测试执行失败: {text}"

        data = json.loads(text)
        _last_report = data
        return _format_report(data)

    except ConnectionError:
        return (
            "❌ 无法连接 TestPilot 引擎。\n"
            "请确保引擎已启动：poetry run python main.py\n"
            f"引擎地址：{ENGINE_URL}"
        )
    except Exception as e:
        return f"❌ 测试异常: {str(e)}"


@mcp.tool()
def get_test_report() -> str:
    """获取最近一次测试的完整报告。

    Returns:
        Markdown格式的测试报告
    """
    if _last_report is None:
        return "暂无测试报告。请先运行 run_blueprint_test 或 run_quick_test。"

    return _last_report.get("report_markdown", "报告内容为空")


@mcp.tool()
def check_engine_health() -> str:
    """检查 TestPilot AI 引擎是否正常运行。

    Returns:
        引擎状态信息
    """
    try:
        status, text = _http_get(f"{ENGINE_URL}/api/v1/health")
        if status == 200:
            data = json.loads(text)
            return (
                f"✅ TestPilot AI 引擎运行正常\n"
                f"- 版本: {data.get('version')}\n"
                f"- 浏览器: {'已就绪' if data.get('browser_ready') else '未启动（首次测试时自动启动）'}\n"
                f"- 沙箱数: {data.get('sandbox_count')}"
            )
        return f"⚠️ 引擎响应异常: {status}"
    except ConnectionError:
        return (
            "❌ TestPilot AI 引擎未运行。\n"
            "请在项目目录执行：poetry run python main.py"
        )
    except Exception as e:
        return f"❌ 检查失败: {str(e)}"


@mcp.tool()
def generate_blueprint(
    url: str,
    app_name: str = "",
    description: str = "",
    output_path: str = "",
) -> str:
    """⚠️ 兜底工具：仅在无编程AI生成的蓝本时使用。

    优先让编程AI（Cursor/Windsurf）生成蓝本——因为它最了解代码结构、元素ID和业务逻辑，
    生成的蓝本更准确、覆盖更全面。

    此工具通过爬取页面自动生成蓝本，适用于：遗留项目、编程AI未生成蓝本时的兜底补救。
    注意：通过爬取生成的蓝本可能遗漏未渲染的UI状态和内部业务逻辑。
    生成后建议人工审核，补充边界场景和精确断言。生成后可直接用 run_blueprint_test 执行。

    Args:
        url: 被测应用的URL（如 http://localhost:3000）
        app_name: 应用名称（空则从页面标题自动推断）
        description: 应用功能描述（帮助AI更准确生成测试用例）
        output_path: 保存路径（如 shop-demo/testpilot.json，空则不保存文件）

    Returns:
        生成的蓝本摘要和JSON内容
    """
    try:
        payload = {"url": url}
        if app_name:
            payload["app_name"] = app_name
        if description:
            payload["description"] = description
        if output_path:
            payload["output_path"] = output_path

        status, text = _http_post_json(
            f"{ENGINE_URL}/api/v1/blueprint/generate",
            payload,
            timeout=120,
        )

        if status != 200:
            return f"❌ 蓝本生成失败: {text}"

        data = json.loads(text)
        bp_json = json.dumps(
            data.get("blueprint_json", {}),
            ensure_ascii=False, indent=2,
        )

        return (
            f"✅ 蓝本自动生成成功！\n\n"
            f"- **应用**: {data.get('app_name', '')}\n"
            f"- **URL**: {data.get('base_url', '')}\n"
            f"- **场景数**: {data.get('total_scenarios', 0)}\n"
            f"- **步骤数**: {data.get('total_steps', 0)}\n"
            f"- **保存路径**: {data.get('saved_path', '未保存')}\n\n"
            f"```json\n{bp_json}\n```\n\n"
            f"**下一步**: 调用 run_blueprint_test 执行测试。"
        )
    except ConnectionError:
        return (
            "❌ 无法连接 TestPilot 引擎。\n"
            "请确保引擎已启动：poetry run python main.py"
        )
    except Exception as e:
        return f"❌ 蓝本生成异常: {str(e)}"


@mcp.tool()
def generate_blueprint_template(
    app_name: str,
    base_url: str,
    pages_description: str,
) -> str:
    """生成 testpilot.json 蓝本模板。

    根据应用描述生成一个蓝本模板框架，编程AI需要根据实际代码补充精确的选择器和预期。

    Args:
        app_name: 应用名称
        base_url: 应用URL
        pages_description: 页面和功能的描述

    Returns:
        testpilot.json 模板内容
    """
    template = {
        "app_name": app_name,
        "base_url": base_url,
        "version": "1.0",
        "pages": [
            {
                "url": "/",
                "title": f"{app_name} - 首页",
                "elements": {
                    "// 请补充实际的元素映射": "// 格式：'元素名称': 'CSS选择器'",
                },
                "scenarios": [
                    {
                        "name": "页面加载",
                        "description": "验证首页正常加载",
                        "steps": [
                            {
                                "action": "navigate",
                                "value": base_url,
                                "expected": f"{app_name}首页正常加载，显示主要内容",
                                "description": "打开应用首页",
                            },
                            {
                                "action": "screenshot",
                                "expected": "页面正常显示，无报错",
                                "description": "截图记录首页状态",
                            },
                        ],
                    },
                    {
                        "name": "// 请根据以下功能描述补充测试场景",
                        "description": pages_description,
                        "steps": [
                            {
                                "action": "// 补充具体步骤",
                                "target": "// CSS选择器",
                                "expected": "// 预期结果",
                                "description": "// 步骤说明",
                            }
                        ],
                    },
                ],
            }
        ],
    }

    result = json.dumps(template, ensure_ascii=False, indent=2)
    return (
        f"以下是 testpilot.json 蓝本模板，请根据实际代码补充完善：\n\n"
        f"```json\n{result}\n```\n\n"
        f"**补充要点：**\n"
        f"1. elements 中填写实际的CSS选择器（#id, .class等）\n"
        f"2. 每个 scenario 代表一个测试场景（如添加、删除、编辑）\n"
        f"3. expected 写清楚操作后应该看到什么\n"
        f"4. 支持的 action: navigate, click, fill, select, wait, screenshot, assert_text, assert_visible\n"
        f"5. 保存为 testpilot.json 后调用 run_blueprint_test 执行测试"
    )


@mcp.tool()
def run_miniprogram_test(
    blueprint_path: str,
    project_path: str = "",
    base_url: str = "",
) -> str:
    """在微信小程序上按蓝本执行测试。

    需要：微信开发者工具已安装并开启服务端口。
    蓝本中 platform 应为 "miniprogram"。

    Args:
        blueprint_path: testpilot.json 蓝本文件的绝对路径
        project_path: 小程序项目目录路径（空则从蓝本 base_url 推断）
        base_url: 覆盖蓝本中的 base_url（可选）

    Returns:
        测试报告
    """
    global _last_report

    if not Path(blueprint_path).exists():
        return f"❌ 蓝本文件不存在: {blueprint_path}"

    try:
        payload: dict = {"blueprint_path": blueprint_path}
        if project_path:
            payload["project_path"] = project_path
        if base_url:
            payload["base_url"] = base_url

        status, text = _http_post_json(
            f"{ENGINE_URL}/api/v1/test/miniprogram-blueprint",
            payload,
            timeout=600,
        )

        if status != 200:
            return f"❌ 小程序测试执行失败: {text}"

        data = json.loads(text)
        _last_report = data
        return _format_report(data).replace(
            "# TestPilot 测试报告",
            "# TestPilot 小程序测试报告",
            1,
        )

    except ConnectionError:
        return (
            "❌ 无法连接 TestPilot 引擎。\n"
            "请确保引擎已启动：poetry run python main.py"
        )
    except Exception as e:
        return f"❌ 小程序测试异常: {str(e)}"


@mcp.tool()
def run_desktop_test(
    blueprint_path: str,
    window_title: str = "",
    base_url: str = "",
) -> str:
    """在 Windows 桌面应用上按蓝本执行测试。

    通过 DesktopController（pywinauto）操控桌面应用窗口。
    蓝本中 platform 应为 "desktop"。

    Args:
        blueprint_path: testpilot.json 蓝本文件的绝对路径
        window_title: 桌面应用窗口标题（用于定位窗口）
        base_url: 覆盖蓝本中的 base_url（可选）

    Returns:
        测试报告
    """
    global _last_report

    if not Path(blueprint_path).exists():
        return f"❌ 蓝本文件不存在: {blueprint_path}"

    try:
        payload: dict = {"blueprint_path": blueprint_path}
        if window_title:
            payload["window_title"] = window_title
        if base_url:
            payload["base_url"] = base_url

        status, text = _http_post_json(
            f"{ENGINE_URL}/api/v1/test/desktop-blueprint",
            payload,
            timeout=600,
        )

        if status != 200:
            return f"❌ 桌面测试执行失败: {text}"

        data = json.loads(text)
        _last_report = data
        return _format_report(data).replace(
            "# TestPilot 测试报告",
            "# TestPilot 桌面应用测试报告",
            1,
        )

    except ConnectionError:
        return (
            "❌ 无法连接 TestPilot 引擎。\n"
            "请确保引擎已启动：poetry run python main.py"
        )
    except Exception as e:
        return f"❌ 桌面测试异常: {str(e)}"


def _format_report(data: dict) -> str:
    """格式化测试报告给编程AI阅读。"""
    total = data.get("total_steps", 0)
    passed = data.get("passed_steps", 0)
    failed = data.get("failed_steps", 0)
    bug_count = data.get("bug_count", 0)
    pass_rate = data.get("pass_rate", 0)

    lines = [
        f"# TestPilot 测试报告",
        f"",
        f"- **测试名称**: {data.get('test_name', '未知')}",
        f"- **目标URL**: {data.get('url', '')}",
        f"- **通过率**: {pass_rate:.0f}%（{passed}/{total}步骤通过）",
        f"- **失败步骤**: {failed}",
        f"- **发现Bug数**: {bug_count}",
        f"- **耗时**: {data.get('duration_seconds', 0):.1f}秒",
        f"",
    ]

    if bug_count > 0:
        lines.extend([
            f"## ⚠️ 发现 {bug_count} 个Bug，请修复：",
            f"",
        ])

    # 附上完整Markdown报告
    report_md = data.get("report_markdown", "")
    if report_md:
        lines.extend([
            f"## 详细报告",
            f"",
            report_md,
        ])

    if bug_count > 0:
        lines.extend([
            f"",
            f"---",
            f"**下一步：请修复以上Bug，更新 testpilot.json（如需），然后再次调用 run_blueprint_test 重新测试。**",
        ])
    else:
        lines.extend([
            f"",
            f"---",
            f"✅ **所有测试通过，代码质量良好！**",
        ])

    return "\n".join(lines)


# ── 入口 ──

if __name__ == "__main__":
    mcp.run(transport="stdio")
