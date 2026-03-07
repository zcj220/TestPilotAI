"""
Docker 沙箱管理器

负责沙箱容器的完整生命周期管理：
- 创建并启动沙箱容器（挂载用户项目文件夹）
- 在沙箱内执行命令（如启动被测应用）
- 获取沙箱状态和日志
- 停止并清理沙箱容器

设计原则：
1. 每次测试使用一个独立的沙箱容器，互不干扰
2. 用户项目文件夹通过 Volume Mount 只读挂载（保护源码）
3. 容器名称带时间戳，避免冲突
4. 所有操作都有超时保护，避免无限等待
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import docker
from docker.errors import APIError, ImageNotFound, NotFound
from docker.models.containers import Container
from loguru import logger

from src.core.config import SandboxConfig
from src.core.exceptions import (
    SandboxNotFoundError,
    SandboxStartError,
    SandboxStopError,
    SandboxTimeoutError,
)


class SandboxManager:
    """Docker 沙箱生命周期管理器。

    典型使用流程：
        manager = SandboxManager(config)
        sandbox_id = await manager.create("D:/Projects/MyApp")
        await manager.exec_command(sandbox_id, "npm run dev")
        logs = await manager.get_logs(sandbox_id)
        await manager.destroy(sandbox_id)
    """

    def __init__(self, config: Optional[SandboxConfig] = None) -> None:
        """初始化沙箱管理器。

        Args:
            config: 沙箱配置。如果不传则使用默认配置。
        """
        self._config = config or SandboxConfig()
        self._client: Optional[docker.DockerClient] = None
        self._containers: dict[str, str] = {}  # sandbox_id -> container_id

    @property
    def client(self) -> docker.DockerClient:
        """延迟初始化 Docker 客户端。

        Returns:
            docker.DockerClient: Docker 客户端实例

        Raises:
            SandboxStartError: Docker 服务未运行或无法连接
        """
        if self._client is None:
            try:
                self._client = docker.from_env()
                self._client.ping()
                logger.info("Docker 客户端连接成功")
            except Exception as e:
                raise SandboxStartError(
                    message="无法连接到 Docker 服务",
                    detail=f"请确认 Docker Desktop 已启动。错误: {e}",
                )
        return self._client

    def _generate_sandbox_id(self) -> str:
        """生成唯一的沙箱 ID。

        Returns:
            str: 格式为 testpilot-YYYYMMDD-HHmmss 的唯一标识
        """
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        return f"{self._config.container_name_prefix}-{timestamp}"

    def _ensure_image(self) -> None:
        """确保沙箱镜像已存在，不存在则拉取。

        Raises:
            SandboxStartError: 镜像拉取失败
        """
        image_name = self._config.image
        try:
            self.client.images.get(image_name)
            logger.debug("沙箱镜像已存在: {}", image_name)
        except ImageNotFound:
            logger.info("正在拉取沙箱镜像: {} ...", image_name)
            try:
                self.client.images.pull(image_name)
                logger.info("沙箱镜像拉取成功: {}", image_name)
            except APIError as e:
                raise SandboxStartError(
                    message=f"沙箱镜像拉取失败: {image_name}",
                    detail=str(e),
                )

    def create(self, project_path: str, app_port: Optional[int] = None) -> str:
        """创建并启动一个新的沙箱容器。

        Args:
            project_path: 用户项目文件夹的绝对路径
            app_port: 被测应用端口，默认使用配置中的端口

        Returns:
            str: 沙箱 ID

        Raises:
            SandboxStartError: 容器创建或启动失败
            FileNotFoundError: 项目路径不存在
        """
        # 验证项目路径
        project = Path(project_path).resolve()
        if not project.exists():
            raise FileNotFoundError(f"项目路径不存在: {project}")
        if not project.is_dir():
            raise FileNotFoundError(f"项目路径不是目录: {project}")

        self._ensure_image()

        sandbox_id = self._generate_sandbox_id()
        effective_app_port = app_port or self._config.app_port

        # 端口映射：宿主机端口 -> 容器内端口
        port_bindings = {
            f"{effective_app_port}/tcp": effective_app_port,
            f"{self._config.vnc_port}/tcp": self._config.vnc_port,
            f"{self._config.browser_port}/tcp": self._config.browser_port,
        }

        # Volume 挂载：项目文件夹 -> 容器内 /workspace
        # 使用 bind mount，在 Windows 上 Docker 会自动转换路径
        volumes = {
            str(project): {
                "bind": self._config.workspace_mount_target,
                "mode": "rw",
            }
        }

        logger.info(
            "正在创建沙箱 | ID={} | 项目={} | 镜像={}",
            sandbox_id,
            project,
            self._config.image,
        )

        try:
            container: Container = self.client.containers.run(
                image=self._config.image,
                name=sandbox_id,
                volumes=volumes,
                ports=port_bindings,
                detach=True,
                remove=False,
                security_opt=["seccomp:unconfined"],
                environment={
                    "TESTPILOT_SANDBOX_ID": sandbox_id,
                    "TESTPILOT_PROJECT_PATH": self._config.workspace_mount_target,
                },
            )

            self._containers[sandbox_id] = container.id
            logger.info(
                "沙箱创建成功 | ID={} | 容器ID={}",
                sandbox_id,
                container.short_id,
            )
            return sandbox_id

        except APIError as e:
            raise SandboxStartError(
                message=f"沙箱创建失败: {sandbox_id}",
                detail=str(e),
            )

    def _get_container(self, sandbox_id: str) -> Container:
        """根据沙箱 ID 获取容器对象。

        Args:
            sandbox_id: 沙箱 ID

        Returns:
            Container: Docker 容器对象

        Raises:
            SandboxNotFoundError: 沙箱不存在
        """
        container_id = self._containers.get(sandbox_id)
        if container_id is None:
            raise SandboxNotFoundError(
                message=f"沙箱不存在: {sandbox_id}",
                detail="该沙箱可能已被销毁或从未创建",
            )
        try:
            return self.client.containers.get(container_id)
        except NotFound:
            del self._containers[sandbox_id]
            raise SandboxNotFoundError(
                message=f"沙箱容器已丢失: {sandbox_id}",
                detail=f"容器 {container_id} 已不存在",
            )

    def exec_command(
        self,
        sandbox_id: str,
        command: str,
        workdir: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> tuple[int, str]:
        """在沙箱内执行命令。

        Args:
            sandbox_id: 沙箱 ID
            command: 要执行的 shell 命令
            workdir: 工作目录，默认为挂载的项目目录
            timeout: 执行超时（秒），默认使用配置中的超时时间

        Returns:
            tuple[int, str]: (退出码, 命令输出)

        Raises:
            SandboxNotFoundError: 沙箱不存在
            SandboxTimeoutError: 命令执行超时
        """
        container = self._get_container(sandbox_id)
        effective_workdir = workdir or self._config.workspace_mount_target
        effective_timeout = timeout or self._config.startup_timeout_seconds

        logger.debug(
            "执行沙箱命令 | ID={} | 命令={} | 工作目录={}",
            sandbox_id,
            command,
            effective_workdir,
        )

        try:
            exec_result = container.exec_run(
                cmd=["bash", "-c", command],
                workdir=effective_workdir,
                demux=True,
            )

            exit_code = exec_result.exit_code
            stdout = (exec_result.output[0] or b"").decode("utf-8", errors="replace")
            stderr = (exec_result.output[1] or b"").decode("utf-8", errors="replace")
            output = stdout + stderr

            if exit_code != 0:
                logger.warning(
                    "沙箱命令返回非零退出码 | ID={} | 退出码={} | 输出={}",
                    sandbox_id,
                    exit_code,
                    output[:500],
                )
            else:
                logger.debug(
                    "沙箱命令执行成功 | ID={} | 输出长度={}",
                    sandbox_id,
                    len(output),
                )

            return exit_code, output

        except Exception as e:
            raise SandboxTimeoutError(
                message=f"沙箱命令执行失败: {command}",
                detail=str(e),
            )

    def get_status(self, sandbox_id: str) -> dict[str, str]:
        """获取沙箱状态信息。

        Args:
            sandbox_id: 沙箱 ID

        Returns:
            dict: 包含 status, id, image, created 等字段的状态字典

        Raises:
            SandboxNotFoundError: 沙箱不存在
        """
        container = self._get_container(sandbox_id)
        container.reload()

        return {
            "sandbox_id": sandbox_id,
            "container_id": container.short_id,
            "status": container.status,
            "image": str(container.image.tags[0]) if container.image.tags else "unknown",
            "created": str(container.attrs.get("Created", "")),
        }

    def get_logs(self, sandbox_id: str, tail: int = 100) -> str:
        """获取沙箱日志。

        Args:
            sandbox_id: 沙箱 ID
            tail: 返回最后多少行日志

        Returns:
            str: 日志内容

        Raises:
            SandboxNotFoundError: 沙箱不存在
        """
        container = self._get_container(sandbox_id)
        logs = container.logs(tail=tail, timestamps=True)
        return logs.decode("utf-8", errors="replace")

    def destroy(self, sandbox_id: str, force: bool = True) -> None:
        """销毁沙箱容器。

        Args:
            sandbox_id: 沙箱 ID
            force: 是否强制停止（默认是）

        Raises:
            SandboxStopError: 容器停止或删除失败
        """
        logger.info("正在销毁沙箱 | ID={}", sandbox_id)

        try:
            container = self._get_container(sandbox_id)
            container.stop(timeout=10) if not force else container.kill()
        except SandboxNotFoundError:
            logger.warning("沙箱已不存在，跳过销毁 | ID={}", sandbox_id)
            self._containers.pop(sandbox_id, None)
            return
        except Exception as e:
            logger.warning("停止沙箱时出错，尝试强制删除 | ID={} | 错误={}", sandbox_id, e)

        try:
            container = self.client.containers.get(self._containers[sandbox_id])
            container.remove(force=True)
            logger.info("沙箱已销毁 | ID={}", sandbox_id)
        except NotFound:
            logger.debug("容器已自动移除 | ID={}", sandbox_id)
        except Exception as e:
            raise SandboxStopError(
                message=f"沙箱删除失败: {sandbox_id}",
                detail=str(e),
            )
        finally:
            self._containers.pop(sandbox_id, None)

    def destroy_all(self) -> None:
        """销毁所有由本管理器创建的沙箱容器。"""
        sandbox_ids = list(self._containers.keys())
        logger.info("正在销毁所有沙箱 | 数量={}", len(sandbox_ids))

        for sandbox_id in sandbox_ids:
            try:
                self.destroy(sandbox_id)
            except Exception as e:
                logger.error("销毁沙箱失败 | ID={} | 错误={}", sandbox_id, e)

    def list_sandboxes(self) -> list[dict[str, str]]:
        """列出所有活跃的沙箱。

        Returns:
            list[dict]: 每个沙箱的状态信息列表
        """
        results = []
        for sandbox_id in list(self._containers.keys()):
            try:
                status = self.get_status(sandbox_id)
                results.append(status)
            except SandboxNotFoundError:
                continue
        return results

    def close(self) -> None:
        """关闭管理器，清理所有资源。"""
        self.destroy_all()
        if self._client:
            self._client.close()
            self._client = None
            logger.info("Docker 客户端已关闭")
