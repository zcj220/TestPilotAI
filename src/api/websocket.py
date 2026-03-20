"""
WebSocket 连接管理器（v2.0 增强）

管理 IDE 插件和 Web 仪表盘的 WebSocket 连接：
- 步骤开始/完成
- Bug 发现
- 修复开始/完成
- 测试完成
- 日志消息
- v2.0：截图推送、测试状态推送、控制命令接收
"""

import asyncio
import json
from typing import Any, Callable, Coroutine, Optional

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger


# 控制命令回调类型
ControlCallback = Callable[[str, dict], Coroutine[Any, Any, None]]


class ConnectionManager:
    """WebSocket 连接管理器。

    维护活跃连接列表，支持广播消息给所有已连接的客户端。
    v2.0：增加截图推送、状态推送、控制命令接收。
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._control_callback: Optional[ControlCallback] = None

    def set_control_callback(self, callback: ControlCallback) -> None:
        """设置控制命令回调（由API路由注册）。"""
        self._control_callback = callback

    async def connect(self, ws: WebSocket) -> None:
        """接受并注册新的 WebSocket 连接。"""
        # 清理可能的死连接（超过3个说明有残留）
        if len(self._connections) >= 3:
            alive: list[WebSocket] = []
            for old_ws in self._connections:
                try:
                    await old_ws.send_text('{"type":"ping"}')
                    alive.append(old_ws)
                except Exception:
                    logger.debug("清理死连接")
            self._connections = alive
        await ws.accept()
        self._connections.append(ws)
        logger.info("WebSocket 客户端已连接 | 当前连接数={}", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        """移除断开的连接。"""
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WebSocket 客户端已断开 | 当前连接数={}", len(self._connections))

    async def handle_message(self, ws: WebSocket, raw: str) -> None:
        """处理从客户端收到的消息（v2.0：控制命令）。

        消息格式：{"type": "control", "action": "pause|resume|stop|step", ...}
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")
        if msg_type == "control" and self._control_callback:
            action = msg.get("action", "")
            data = msg.get("data", {})
            try:
                await self._control_callback(action, data)
            except Exception as e:
                logger.warning("控制命令处理失败: {} | {}", action, str(e)[:80])

    async def broadcast(self, message_type: str, data: dict[str, Any]) -> None:
        """向所有连接的客户端广播消息。

        Args:
            message_type: 消息类型（step_start/step_done/bug_found/...）
            data: 消息数据
        """
        if not self._connections:
            return

        payload = json.dumps(
            {"type": message_type, "data": data},
            ensure_ascii=False,
        )

        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)

    async def send_log(self, message: str) -> None:
        """发送日志消息的便捷方法。"""
        await self.broadcast("log", {"message": message})

    async def send_step_start(self, step: int, description: str) -> None:
        """发送步骤开始通知。"""
        await self.broadcast("step_start", {
            "step": step,
            "message": f"步骤 {step}: {description}",
        })

    async def send_step_done(
        self, step: int, status: str, description: str,
    ) -> None:
        """发送步骤完成通知。"""
        await self.broadcast("step_done", {
            "step": step,
            "status": status,
            "message": f"步骤 {step} [{status}]: {description}",
        })

    async def send_bug_found(self, title: str, severity: str) -> None:
        """发送 Bug 发现通知。"""
        await self.broadcast("bug_found", {
            "title": title,
            "severity": severity,
            "message": f"发现 Bug [{severity}]: {title}",
        })

    async def send_repair_start(self, bug_title: str) -> None:
        """发送修复开始通知。"""
        await self.broadcast("repair_start", {
            "message": f"开始修复: {bug_title}",
        })

    async def send_repair_done(self, bug_title: str, success: bool) -> None:
        """发送修复完成通知。"""
        status_text = "成功" if success else "失败"
        await self.broadcast("repair_done", {
            "success": success,
            "message": f"修复{status_text}: {bug_title}",
        })

    async def send_test_started(self) -> None:
        """发送测试开始通知，让插件显示控制按钮。"""
        await self.broadcast("test_started", {"message": "测试已开始"})

    async def send_test_done(
        self, pass_rate: float, bug_count: int,
        full_report: dict[str, Any] | None = None,
    ) -> None:
        """发送测试完成通知（含完整报告作为HTTP后备）。"""
        data: dict[str, Any] = {
            "pass_rate": pass_rate,
            "bug_count": bug_count,
            "message": f"测试完成 | 通过率 {pass_rate:.0f}% | Bug {bug_count} 个",
        }
        if full_report is not None:
            data["report"] = full_report
        await self.broadcast("test_done", data)

    # ── v2.0 新增推送 ────────────────────────────────

    async def send_screenshot(self, step: int, image_base64: str) -> None:
        """推送步骤截图（替代前端轮询）。"""
        await self.broadcast("screenshot", {
            "step": step,
            "image_base64": image_base64,
        })

    async def send_state_change(self, state: str, detail: dict | None = None) -> None:
        """推送测试状态变化（RUNNING/PAUSED/STOPPED/IDLE）。"""
        data: dict[str, Any] = {"state": state}
        if detail:
            data.update(detail)
        await self.broadcast("state_change", data)

    @property
    def active_count(self) -> int:
        """当前活跃连接数。"""
        return len(self._connections)


# 全局单例
ws_manager = ConnectionManager()
