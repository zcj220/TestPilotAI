"""Webhook 通知模块测试（v4.0）。"""

import json
from unittest.mock import patch, MagicMock

import pytest

from src.notify.webhook import WebhookNotifier


SAMPLE_REPORT = {
    "test_name": "商城测试",
    "pass_rate": 0.9,
    "passed_steps": 9,
    "total_steps": 10,
    "bug_count": 1,
    "duration_seconds": 5.3,
}

SAMPLE_REPORT_PERFECT = {
    "test_name": "完美测试",
    "pass_rate": 1.0,
    "passed_steps": 5,
    "total_steps": 5,
    "bug_count": 0,
    "duration_seconds": 2.0,
}

SAMPLE_REPORT_BAD = {
    "test_name": "失败测试",
    "pass_rate": 0.3,
    "passed_steps": 3,
    "total_steps": 10,
    "bug_count": 5,
    "duration_seconds": 12.0,
}


class TestWebhookNotifier:
    def test_init(self):
        n = WebhookNotifier()
        assert n._timeout == 10

    def test_init_custom_timeout(self):
        n = WebhookNotifier(timeout=30)
        assert n._timeout == 30

    # ── 钉钉 ──

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_dingtalk_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        result = n.send_dingtalk("https://oapi.dingtalk.com/robot/send?token=xxx", SAMPLE_REPORT)
        assert result is True
        mock_urlopen.assert_called_once()

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_dingtalk_payload_format(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        n.send_dingtalk("https://example.com", SAMPLE_REPORT)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["msgtype"] == "markdown"
        assert "90%" in payload["markdown"]["text"]

    # ── 飞书 ──

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_feishu_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        result = n.send_feishu("https://open.feishu.cn/hook/xxx", SAMPLE_REPORT)
        assert result is True

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_feishu_payload(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        n.send_feishu("https://example.com", SAMPLE_REPORT_PERFECT)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["msg_type"] == "text"
        assert "100%" in payload["content"]["text"]
        assert "✅" in payload["content"]["text"]

    # ── Slack ──

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_slack_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        result = n.send_slack("https://hooks.slack.com/xxx", SAMPLE_REPORT)
        assert result is True

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_slack_payload(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        n.send_slack("https://example.com", SAMPLE_REPORT_BAD)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert "blocks" in payload
        assert payload["blocks"][0]["type"] == "header"

    # ── 通用 Webhook ──

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_generic(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        result = n.send_generic("https://my-server.com/hook", SAMPLE_REPORT)
        assert result is True
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["event"] == "test_completed"
        assert payload["report"] == SAMPLE_REPORT

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_generic_with_extra(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        n.send_generic("https://example.com", SAMPLE_REPORT, extra={"env": "prod"})
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert payload["env"] == "prod"

    # ── 错误处理 ──

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_url_error(self, mock_urlopen):
        import urllib.error
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        n = WebhookNotifier()
        result = n.send_dingtalk("https://bad-url.com", SAMPLE_REPORT)
        assert result is False

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_send_generic_exception(self, mock_urlopen):
        mock_urlopen.side_effect = RuntimeError("unexpected")
        n = WebhookNotifier()
        result = n.send_feishu("https://bad.com", SAMPLE_REPORT)
        assert result is False

    # ── 图标逻辑 ──

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_icon_perfect(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        n.send_dingtalk("https://example.com", SAMPLE_REPORT_PERFECT)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert "✅" in payload["markdown"]["text"]

    @patch("src.notify.webhook.urllib.request.urlopen")
    def test_icon_bad(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        n = WebhookNotifier()
        n.send_dingtalk("https://example.com", SAMPLE_REPORT_BAD)
        req = mock_urlopen.call_args[0][0]
        payload = json.loads(req.data)
        assert "❌" in payload["markdown"]["text"]
