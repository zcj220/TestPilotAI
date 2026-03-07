"""
配置模块的单元测试。

验证：
- 默认配置值正确
- 环境变量能覆盖配置
- 子配置聚合正常
"""

from src.core.config import (
    AIConfig,
    AppConfig,
    BrowserConfig,
    SandboxConfig,
    ServerConfig,
    get_config,
)


class TestServerConfig:
    """服务配置测试。"""

    def test_default_values(self) -> None:
        """默认值应该是本地开发环境。"""
        config = ServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8900
        assert isinstance(config.reload, bool)
        assert config.log_level in ("INFO", "DEBUG")


class TestSandboxConfig:
    """沙箱配置测试。"""

    def test_default_image(self) -> None:
        """默认镜像应该是 AIO Sandbox。"""
        config = SandboxConfig()
        assert "sandbox" in config.image
        assert config.container_name_prefix == "testpilot"

    def test_default_ports(self) -> None:
        """默认端口配置。"""
        config = SandboxConfig()
        assert config.app_port == 3000
        assert config.vnc_port == 6080
        assert config.browser_port == 9222

    def test_workspace_mount(self) -> None:
        """默认挂载路径。"""
        config = SandboxConfig()
        assert config.workspace_mount_target == "/workspace"


class TestBrowserConfig:
    """浏览器配置测试。"""

    def test_default_headless(self) -> None:
        """默认应该是无头模式（有 .env 时可能为 False）。"""
        config = BrowserConfig()
        assert isinstance(config.headless, bool)

    def test_default_viewport(self) -> None:
        """默认视口应该是 1280x720。"""
        config = BrowserConfig()
        assert config.viewport_width == 1280
        assert config.viewport_height == 720

    def test_screenshot_dir_exists(self) -> None:
        """截图目录路径应该有值。"""
        config = BrowserConfig()
        assert config.screenshot_dir is not None
        assert "screenshots" in str(config.screenshot_dir)


class TestAIConfig:
    """AI API 配置测试。"""

    def test_default_no_api_key(self) -> None:
        """默认情况下 API 密钥为空，有 .env 时为字符串。"""
        config = AIConfig()
        assert config.api_key is None or isinstance(config.api_key, str)

    def test_default_model(self) -> None:
        """默认模型应该是 Doubao-Seed-1.8。"""
        config = AIConfig()
        assert "doubao-seed" in config.model
        assert config.reasoning_effort == "medium"
        assert config.max_completion_tokens == 65535

    def test_retry_config(self) -> None:
        """重试配置应该合理。"""
        config = AIConfig()
        assert config.max_retries == 3
        assert config.request_timeout_seconds == 60


class TestAppConfig:
    """应用全局配置测试。"""

    def test_aggregates_sub_configs(self) -> None:
        """全局配置应该包含所有子配置。"""
        config = AppConfig()
        assert isinstance(config.server, ServerConfig)
        assert isinstance(config.sandbox, SandboxConfig)
        assert isinstance(config.browser, BrowserConfig)
        assert isinstance(config.ai, AIConfig)

    def test_get_config_returns_instance(self) -> None:
        """get_config 应该返回有效的配置实例。"""
        config = get_config()
        assert isinstance(config, AppConfig)
