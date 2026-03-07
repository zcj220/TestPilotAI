"""
自定义异常体系

所有 TestPilot AI 的异常都继承自 TestPilotError，
便于上层统一捕获和处理。每个模块有自己的异常基类。
"""


class TestPilotError(Exception):
    """TestPilot AI 所有异常的基类。"""

    def __init__(self, message: str, detail: str = "") -> None:
        self.message = message
        self.detail = detail
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.detail:
            return f"{self.message} | 详情: {self.detail}"
        return self.message


# ── 沙箱相关异常 ──────────────────────────────────────────────


class SandboxError(TestPilotError):
    """沙箱操作异常的基类。"""


class SandboxStartError(SandboxError):
    """沙箱启动失败。"""


class SandboxStopError(SandboxError):
    """沙箱停止失败。"""


class SandboxNotFoundError(SandboxError):
    """指定的沙箱容器不存在。"""


class SandboxTimeoutError(SandboxError):
    """沙箱操作超时。"""


# ── 浏览器自动化相关异常 ──────────────────────────────────────


class BrowserError(TestPilotError):
    """浏览器操作异常的基类。"""


class BrowserLaunchError(BrowserError):
    """浏览器启动失败。"""


class BrowserNavigationError(BrowserError):
    """页面导航失败。"""


class BrowserScreenshotError(BrowserError):
    """截图失败。"""


class BrowserActionError(BrowserError):
    """用户交互操作（点击、输入等）失败。"""


# ── AI API 相关异常 ──────────────────────────────────────────


class AIError(TestPilotError):
    """AI API 调用异常的基类。"""


class AIAuthenticationError(AIError):
    """API 认证失败（密钥无效或过期）。"""


class AIRateLimitError(AIError):
    """API 调用频率超限。"""


class AIResponseError(AIError):
    """AI 返回了无法解析的响应。"""


# ── 测试执行相关异常 ──────────────────────────────────────────


class TestExecutionError(TestPilotError):
    """测试执行过程中的异常基类。"""


class TestScriptParseError(TestExecutionError):
    """测试脚本解析失败。"""


class TestStepFailedError(TestExecutionError):
    """单个测试步骤执行失败（非Bug，是执行层面的错误）。"""


# ── 自动修复相关异常 ──────────────────────────────────────────


class RepairError(TestPilotError):
    """自动修复过程中的异常基类。"""


class RepairAnalysisError(RepairError):
    """AI 分析Bug/生成修复方案失败。"""


class PatchApplyError(RepairError):
    """补丁应用失败（文件不存在、行号不匹配等）。"""


class PatchRollbackError(RepairError):
    """补丁回滚失败。"""


class RepairLoopError(RepairError):
    """修复闭环流程异常（超过重试次数等）。"""
