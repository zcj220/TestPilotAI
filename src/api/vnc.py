"""
VNC 实时观看模块（v0.7）

提供浏览器操作的实时可视化能力：
- 获取 VNC/noVNC 连接信息
- 截图流（降级方案：当 VNC 不可用时，通过定时截图模拟实时画面）
"""

import asyncio
import base64
import time
from pathlib import Path
from typing import Optional

from loguru import logger
from pydantic import BaseModel, Field


class VncInfo(BaseModel):
    """VNC 连接信息。"""
    available: bool = Field(default=False, description="VNC 是否可用")
    novnc_url: Optional[str] = Field(default=None, description="noVNC Web 地址")
    vnc_host: str = Field(default="127.0.0.1", description="VNC 主机")
    vnc_port: int = Field(default=5900, description="VNC 端口")
    password: str = Field(default="", description="VNC 密码")
    message: str = Field(default="", description="状态说明")


class ScreenshotFrame(BaseModel):
    """截图帧（降级方案）。"""
    timestamp: float = Field(description="时间戳")
    image_base64: str = Field(description="Base64 编码的 PNG 截图")
    width: int = Field(default=0)
    height: int = Field(default=0)


class LiveViewManager:
    """实时观看管理器。

    优先使用 VNC，不可用时降级为截图流模式。
    截图流模式：定时对浏览器截图，通过 WebSocket 推送给前端。
    """

    def __init__(self) -> None:
        self._vnc_info: Optional[VncInfo] = None
        self._screenshot_task: Optional[asyncio.Task] = None
        self._running = False

    def get_vnc_info(self) -> VncInfo:
        """获取当前 VNC 连接信息。

        VNC 需要 Docker 沙箱配置 VNC 服务（后续版本完善）。
        当前版本返回不可用状态，前端使用截图流降级方案。
        """
        if self._vnc_info:
            return self._vnc_info

        return VncInfo(
            available=False,
            message="VNC 尚未配置，使用截图流降级模式。后续版本将在 Docker 沙箱中集成 VNC 服务。",
        )

    def set_vnc_info(self, info: VncInfo) -> None:
        """设置 VNC 连接信息（由沙箱管理器调用）。"""
        self._vnc_info = info

    async def capture_screenshot(self, browser_page: object) -> Optional[ScreenshotFrame]:
        """从浏览器页面捕获一帧截图。

        Args:
            browser_page: Playwright Page 对象

        Returns:
            ScreenshotFrame 或 None（如果捕获失败）
        """
        try:
            # browser_page 是 Playwright 的 Page 对象
            page = browser_page  # type: ignore
            screenshot_bytes = await page.screenshot(type="png")
            b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

            return ScreenshotFrame(
                timestamp=time.time(),
                image_base64=b64,
            )
        except Exception as e:
            logger.debug("截图捕获失败: {}", e)
            return None

    async def get_latest_screenshot(self, data_dir: str = "data") -> Optional[ScreenshotFrame]:
        """从 data 目录获取最新的截图文件。

        这是一个不依赖浏览器实例的降级方案。
        """
        try:
            data_path = Path(data_dir)
            if not data_path.exists():
                return None

            screenshots = sorted(
                data_path.glob("*.png"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not screenshots:
                return None

            latest = screenshots[0]
            b64 = base64.b64encode(latest.read_bytes()).decode("utf-8")
            return ScreenshotFrame(
                timestamp=latest.stat().st_mtime,
                image_base64=b64,
            )
        except Exception as e:
            logger.debug("获取最新截图失败: {}", e)
            return None


# 全局单例
live_view = LiveViewManager()
