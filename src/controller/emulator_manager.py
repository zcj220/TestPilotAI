"""
Docker Android 模拟器管理器（v5.1）

管理 Docker 容器中的 Android 模拟器生命周期：
- 启动/停止 docker-compose 服务
- 等待模拟器和 Appium 就绪
- 健康检查
- CI 模式集成

使用方式：
    manager = EmulatorManager()
    await manager.start()           # 启动容器
    await manager.wait_ready()      # 等待就绪
    # ... 执行测试 ...
    await manager.stop()            # 停止容器

CI 模式：
    manager = EmulatorManager(compose_file="docker-compose.android.yml")
    async with manager:
        # 模拟器已就绪
        controller = AndroidController(MobileConfig(appium_url=manager.appium_url))
        await controller.launch()
"""

import asyncio
import json
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from loguru import logger


class EmulatorManager:
    """Docker Android 模拟器管理器。"""

    def __init__(
        self,
        compose_file: str = "docker-compose.android.yml",
        project_dir: Optional[str] = None,
        appium_host: str = "127.0.0.1",
        appium_port: int = 4723,
        vnc_port: int = 6080,
        startup_timeout: int = 300,
    ) -> None:
        self._compose_file = compose_file
        self._project_dir = project_dir or str(Path.cwd())
        self._appium_host = appium_host
        self._appium_port = appium_port
        self._vnc_port = vnc_port
        self._startup_timeout = startup_timeout
        self._is_running = False

    @property
    def appium_url(self) -> str:
        return f"http://{self._appium_host}:{self._appium_port}"

    @property
    def vnc_url(self) -> str:
        return f"http://{self._appium_host}:{self._vnc_port}"

    @property
    def is_running(self) -> bool:
        return self._is_running

    def _run_compose(self, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """执行 docker compose 命令。"""
        cmd = ["docker", "compose", "-f", self._compose_file] + list(args)
        logger.debug("执行: {}", " ".join(cmd))
        return subprocess.run(
            cmd,
            cwd=self._project_dir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    async def start(self) -> None:
        """启动 Docker Android 模拟器容器。"""
        logger.info("正在启动 Android 模拟器容器...")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._run_compose("up", "-d", timeout=120),
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"启动容器失败: {result.stderr[:500]}"
            )

        self._is_running = True
        logger.info("容器已启动，等待模拟器就绪...")

    async def stop(self) -> None:
        """停止并清理容器。"""
        logger.info("正在停止 Android 模拟器容器...")

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._run_compose("down", "--volumes", timeout=60),
        )

        self._is_running = False
        if result.returncode == 0:
            logger.info("容器已停止")
        else:
            logger.warning("停止容器时出错: {}", result.stderr[:200])

    async def wait_ready(self, timeout: Optional[int] = None) -> bool:
        """等待 Appium Server 就绪。

        Args:
            timeout: 超时秒数，默认使用构造函数中的 startup_timeout

        Returns:
            True 如果就绪，False 如果超时
        """
        effective_timeout = timeout or self._startup_timeout
        logger.info("等待 Appium Server 就绪 | 超时={}s", effective_timeout)

        loop = asyncio.get_event_loop()
        elapsed = 0
        interval = 5

        while elapsed < effective_timeout:
            ready = await loop.run_in_executor(None, self._check_appium_status)
            if ready:
                logger.info("Appium Server 已就绪 | 耗时={}s", elapsed)
                return True

            await asyncio.sleep(interval)
            elapsed += interval
            if elapsed % 30 == 0:
                logger.info("仍在等待模拟器启动... ({}s/{}s)", elapsed, effective_timeout)

        logger.error("模拟器启动超时 ({}s)", effective_timeout)
        return False

    def _check_appium_status(self) -> bool:
        """检查 Appium Server 是否可用。"""
        try:
            url = f"{self.appium_url}/status"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("value", {}).get("ready", False)
        except (urllib.error.URLError, urllib.error.HTTPError, Exception):
            return False

    async def health_check(self) -> dict:
        """获取模拟器和 Appium 的健康状态。

        Returns:
            {"appium_ready": bool, "appium_url": str, "vnc_url": str, "container_running": bool}
        """
        loop = asyncio.get_event_loop()
        appium_ready = await loop.run_in_executor(None, self._check_appium_status)

        container_running = False
        try:
            result = await loop.run_in_executor(
                None,
                lambda: self._run_compose("ps", "--format", "json", timeout=10),
            )
            if result.returncode == 0 and result.stdout.strip():
                container_running = True
        except Exception:
            pass

        return {
            "appium_ready": appium_ready,
            "appium_url": self.appium_url,
            "vnc_url": self.vnc_url,
            "container_running": container_running,
        }

    async def get_emulator_info(self) -> dict:
        """获取模拟器设备信息。"""
        loop = asyncio.get_event_loop()

        def _get_info():
            try:
                url = f"{self.appium_url}/status"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    build = data.get("value", {}).get("build", {})
                    return {
                        "appium_version": build.get("version", "unknown"),
                        "ready": data.get("value", {}).get("ready", False),
                    }
            except Exception:
                return {"appium_version": "unknown", "ready": False}

        return await loop.run_in_executor(None, _get_info)

    # ── Context Manager ──

    async def __aenter__(self) -> "EmulatorManager":
        await self.start()
        ready = await self.wait_ready()
        if not ready:
            await self.stop()
            raise RuntimeError("模拟器启动超时")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
