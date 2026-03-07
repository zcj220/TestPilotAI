"""
应用配置模块

使用 pydantic-settings 管理所有配置项，支持环境变量和 .env 文件覆盖。
所有敏感信息（API密钥等）通过环境变量注入，绝不硬编码。
"""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录（pyproject.toml 所在目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class ServerConfig(BaseSettings):
    """FastAPI 服务配置。"""

    model_config = SettingsConfigDict(
        env_prefix="TP_SERVER_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(default="127.0.0.1", description="服务监听地址")
    port: int = Field(default=8900, description="服务监听端口")
    reload: bool = Field(default=False, description="是否启用热重载（仅开发环境）")
    log_level: str = Field(default="INFO", description="日志级别")


class SandboxConfig(BaseSettings):
    """Docker 沙箱配置。"""

    model_config = SettingsConfigDict(
        env_prefix="TP_SANDBOX_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    image: str = Field(
        default="ghcr.io/agent-infra/sandbox:latest",
        description="沙箱 Docker 镜像名称",
    )
    container_name_prefix: str = Field(
        default="testpilot",
        description="容器名称前缀",
    )
    workspace_mount_target: str = Field(
        default="/workspace",
        description="项目文件夹在沙箱内的挂载路径",
    )
    default_startup_command: str = Field(
        default="npm run dev",
        description="沙箱内默认的应用启动命令",
    )
    startup_timeout_seconds: int = Field(
        default=60,
        description="等待应用启动的超时时间（秒）",
    )
    vnc_port: int = Field(
        default=6080,
        description="VNC Web 端口（用于可视化观看）",
    )
    browser_port: int = Field(
        default=9222,
        description="浏览器远程调试端口",
    )
    app_port: int = Field(
        default=3000,
        description="被测应用的默认端口",
    )


class BrowserConfig(BaseSettings):
    """Playwright 浏览器自动化配置。"""

    model_config = SettingsConfigDict(
        env_prefix="TP_BROWSER_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    headless: bool = Field(
        default=True,
        description="是否使用无头模式",
    )
    default_timeout_ms: int = Field(
        default=30000,
        description="默认操作超时时间（毫秒）",
    )
    screenshot_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "screenshots",
        description="截图保存目录",
    )
    video_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "videos",
        description="录屏保存目录",
    )
    viewport_width: int = Field(default=1280, description="浏览器视口宽度")
    viewport_height: int = Field(default=720, description="浏览器视口高度")


class AIConfig(BaseSettings):
    """AI API 配置。

    使用 Doubao-Seed-1.8 作为统一模型，兼具文本生成和视觉理解能力，
    专为 Agent 场景优化。通过 OpenAI SDK 兼容接口调用方舟平台。
    """

    model_config = SettingsConfigDict(
        env_prefix="TP_AI_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: Optional[str] = Field(
        default=None,
        description="方舟平台 API 密钥（必须通过环境变量设置）",
    )
    api_base_url: str = Field(
        default="https://ark.cn-beijing.volces.com/api/v3",
        description="方舟平台 API 基础 URL（兼容 OpenAI 格式）",
    )
    model: str = Field(
        default="doubao-seed-1-8-251228",
        description="Doubao-Seed-1.8 统一模型（文本生成 + 视觉理解 + Agent）",
    )
    reasoning_effort: str = Field(
        default="medium",
        description="思考深度：minimal（不思考）/ low / medium / high",
    )
    max_completion_tokens: int = Field(
        default=65535,
        description="最大输出 Token 数",
    )
    max_retries: int = Field(default=3, description="API 调用最大重试次数")
    request_timeout_seconds: int = Field(default=60, description="API 请求超时（秒）")


class MobileConfig(BaseSettings):
    """移动端测试配置（v5.0）。"""

    model_config = SettingsConfigDict(
        env_prefix="TP_MOBILE_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    appium_url: str = Field(
        default="http://127.0.0.1:4723",
        description="Appium Server 地址",
    )
    platform_name: str = Field(
        default="Android",
        description="平台名称: Android / iOS",
    )
    device_name: str = Field(
        default="",
        description="设备名称（空=自动检测）",
    )
    app_package: str = Field(
        default="",
        description="Android 包名",
    )
    app_activity: str = Field(
        default="",
        description="Android 启动 Activity",
    )
    app_path: str = Field(
        default="",
        description="APK/IPA 文件路径（自动安装）",
    )
    automation_name: str = Field(
        default="UiAutomator2",
        description="自动化引擎: UiAutomator2 (Android) / XCUITest (iOS)",
    )
    no_reset: bool = Field(
        default=True,
        description="不重置应用状态",
    )
    screenshot_dir: Path = Field(
        default=PROJECT_ROOT / "screenshots" / "mobile",
        description="手机截图保存目录",
    )


class AppConfig(BaseSettings):
    """应用全局配置，聚合所有子配置。"""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server: ServerConfig = Field(default_factory=ServerConfig)
    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    mobile: MobileConfig = Field(default_factory=MobileConfig)

    debug: bool = Field(default=False, description="调试模式")


def get_config() -> AppConfig:
    """获取应用配置单例。

    Returns:
        AppConfig: 应用全局配置实例
    """
    return AppConfig()
