"""
异常体系的单元测试。

验证：
- 异常继承关系正确
- 异常消息格式正确
- 详情信息能正确附加
"""

from src.core.exceptions import (
    AIAuthenticationError,
    AIError,
    BrowserActionError,
    BrowserError,
    BrowserLaunchError,
    SandboxError,
    SandboxNotFoundError,
    SandboxStartError,
    TestPilotError,
)


class TestExceptionHierarchy:
    """异常继承关系测试。"""

    def test_base_exception(self) -> None:
        """所有异常都应继承自 TestPilotError。"""
        err = TestPilotError("测试错误")
        assert isinstance(err, Exception)
        assert err.message == "测试错误"
        assert err.detail == ""

    def test_exception_with_detail(self) -> None:
        """异常应该能附带详细信息。"""
        err = TestPilotError("主错误", detail="详细原因")
        assert "主错误" in str(err)
        assert "详细原因" in str(err)

    def test_sandbox_exceptions_inherit(self) -> None:
        """沙箱异常应继承自 SandboxError → TestPilotError。"""
        err = SandboxStartError("启动失败")
        assert isinstance(err, SandboxError)
        assert isinstance(err, TestPilotError)

    def test_sandbox_not_found(self) -> None:
        """沙箱不存在异常。"""
        err = SandboxNotFoundError("沙箱不存在", detail="ID=test-123")
        assert isinstance(err, SandboxError)
        assert "test-123" in str(err)

    def test_browser_exceptions_inherit(self) -> None:
        """浏览器异常应继承自 BrowserError → TestPilotError。"""
        err = BrowserLaunchError("启动失败")
        assert isinstance(err, BrowserError)
        assert isinstance(err, TestPilotError)

    def test_browser_action_error(self) -> None:
        """浏览器操作异常。"""
        err = BrowserActionError("点击失败", detail="元素不存在")
        assert "点击失败" in str(err)

    def test_ai_exceptions_inherit(self) -> None:
        """AI API 异常应继承自 AIError → TestPilotError。"""
        err = AIAuthenticationError("认证失败")
        assert isinstance(err, AIError)
        assert isinstance(err, TestPilotError)
