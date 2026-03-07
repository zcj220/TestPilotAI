"""
Webhook 通知模块（v4.0）

测试完成后发送通知到外部系统：
- 钉钉机器人
- 飞书机器人
- Slack
- 通用Webhook（自定义URL）

使用方式：
    notifier = WebhookNotifier()
    notifier.send_dingtalk("https://oapi.dingtalk.com/robot/send?access_token=xxx", report)
    notifier.send_feishu("https://open.feishu.cn/open-apis/bot/v2/hook/xxx", report)
    notifier.send_slack("https://hooks.slack.com/services/xxx", report)
    notifier.send_generic("https://my-server.com/webhook", report)
"""

import json
import urllib.request
import urllib.error
from typing import Optional

from loguru import logger


class WebhookNotifier:
    """Webhook 通知发送器。"""

    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def send_dingtalk(self, webhook_url: str, report: dict) -> bool:
        """发送钉钉机器人通知。"""
        pass_rate = report.get("pass_rate", 0)
        icon = "✅" if pass_rate >= 1.0 else "⚠️" if pass_rate >= 0.8 else "❌"

        text = (
            f"### {icon} TestPilot AI 测试报告\n\n"
            f"- **测试名称**: {report.get('test_name', '未知')}\n"
            f"- **通过率**: {pass_rate * 100:.0f}%\n"
            f"- **步骤**: {report.get('passed_steps', 0)}/{report.get('total_steps', 0)}\n"
            f"- **Bug数量**: {report.get('bug_count', 0)}\n"
            f"- **耗时**: {report.get('duration_seconds', 0):.1f}s\n"
        )

        payload = {
            "msgtype": "markdown",
            "markdown": {
                "title": f"{icon} TestPilot 测试结果",
                "text": text,
            },
        }
        return self._post(webhook_url, payload)

    def send_feishu(self, webhook_url: str, report: dict) -> bool:
        """发送飞书机器人通知。"""
        pass_rate = report.get("pass_rate", 0)
        icon = "✅" if pass_rate >= 1.0 else "⚠️" if pass_rate >= 0.8 else "❌"

        content = (
            f"{icon} TestPilot AI 测试报告\n"
            f"测试名称: {report.get('test_name', '未知')}\n"
            f"通过率: {pass_rate * 100:.0f}%\n"
            f"步骤: {report.get('passed_steps', 0)}/{report.get('total_steps', 0)}\n"
            f"Bug数量: {report.get('bug_count', 0)}\n"
            f"耗时: {report.get('duration_seconds', 0):.1f}s"
        )

        payload = {
            "msg_type": "text",
            "content": {"text": content},
        }
        return self._post(webhook_url, payload)

    def send_slack(self, webhook_url: str, report: dict) -> bool:
        """发送Slack通知。"""
        pass_rate = report.get("pass_rate", 0)
        icon = "✅" if pass_rate >= 1.0 else "⚠️" if pass_rate >= 0.8 else "❌"

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{icon} TestPilot AI 测试报告",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*测试名称*\n{report.get('test_name', '未知')}"},
                    {"type": "mrkdwn", "text": f"*通过率*\n{pass_rate * 100:.0f}%"},
                    {"type": "mrkdwn", "text": f"*步骤*\n{report.get('passed_steps', 0)}/{report.get('total_steps', 0)}"},
                    {"type": "mrkdwn", "text": f"*Bug*\n{report.get('bug_count', 0)}"},
                ],
            },
        ]

        payload = {"blocks": blocks}
        return self._post(webhook_url, payload)

    def send_generic(self, webhook_url: str, report: dict, extra: Optional[dict] = None) -> bool:
        """发送通用Webhook（直接POST报告JSON）。"""
        payload = {
            "event": "test_completed",
            "report": report,
        }
        if extra:
            payload.update(extra)
        return self._post(webhook_url, payload)

    def _post(self, url: str, payload: dict) -> bool:
        """发送POST请求。"""
        try:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status < 300:
                    logger.info("Webhook通知发送成功: {}", url[:50])
                    return True
                else:
                    logger.warning("Webhook通知返回非200: {} {}", resp.status, url[:50])
                    return False
        except urllib.error.URLError as e:
            logger.warning("Webhook通知发送失败: {} | {}", url[:50], e)
            return False
        except Exception as e:
            logger.warning("Webhook通知异常: {} | {}", url[:50], e)
            return False
