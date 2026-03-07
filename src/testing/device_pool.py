"""
设备池管理器（v9.0 Phase3）

管理可用测试设备/浏览器实例，支持：设备注册/注销、自动分配、健康检查、并发控制。
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from loguru import logger


class DeviceType(str, Enum):
    """设备类型。"""
    BROWSER = "browser"
    ANDROID = "android"
    IOS = "ios"
    DESKTOP = "desktop"
    MINIPROGRAM = "miniprogram"


class DeviceState(str, Enum):
    """设备状态。"""
    AVAILABLE = "available"
    IN_USE = "in_use"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


@dataclass
class DeviceInfo:
    """设备信息。"""
    device_id: str
    device_type: DeviceType
    name: str = ""
    state: DeviceState = DeviceState.AVAILABLE
    capabilities: dict = field(default_factory=dict)
    assigned_to: str = ""        # 分配给哪个玩家
    last_heartbeat: float = 0.0
    registered_at: float = 0.0
    tags: list[str] = field(default_factory=list)


class DevicePoolManager:
    """设备池管理器。"""

    def __init__(self, max_devices: int = 20) -> None:
        self.max_devices = max_devices
        self._devices: dict[str, DeviceInfo] = {}

    @property
    def device_count(self) -> int:
        return len(self._devices)

    @property
    def available_count(self) -> int:
        return sum(1 for d in self._devices.values() if d.state == DeviceState.AVAILABLE)

    def register(self, device_id: str, device_type: DeviceType,
                 name: str = "", capabilities: dict = None, tags: list[str] = None) -> DeviceInfo:
        """注册设备到池中。"""
        if len(self._devices) >= self.max_devices:
            raise ValueError(f"设备池已满 ({self.max_devices})")
        if device_id in self._devices:
            raise ValueError(f"设备 {device_id} 已存在")

        device = DeviceInfo(
            device_id=device_id,
            device_type=device_type,
            name=name or device_id,
            capabilities=capabilities or {},
            tags=tags or [],
            registered_at=time.time(),
            last_heartbeat=time.time(),
        )
        self._devices[device_id] = device
        logger.info("设备注册 | {} | 类型: {} | 池中: {}", device_id, device_type.value, len(self._devices))
        return device

    def unregister(self, device_id: str) -> None:
        """从池中注销设备。"""
        if device_id not in self._devices:
            raise KeyError(f"设备 {device_id} 不存在")
        del self._devices[device_id]
        logger.info("设备注销 | {} | 剩余: {}", device_id, len(self._devices))

    def get(self, device_id: str) -> Optional[DeviceInfo]:
        return self._devices.get(device_id)

    def acquire(self, player_id: str, device_type: DeviceType = None,
                tags: list[str] = None) -> Optional[DeviceInfo]:
        """为玩家分配一个可用设备。

        Args:
            player_id: 请求设备的玩家
            device_type: 需要的设备类型（None=任意）
            tags: 需要匹配的标签（全部匹配）
        """
        for device in self._devices.values():
            if device.state != DeviceState.AVAILABLE:
                continue
            if device_type and device.device_type != device_type:
                continue
            if tags and not all(t in device.tags for t in tags):
                continue

            device.state = DeviceState.IN_USE
            device.assigned_to = player_id
            logger.info("设备分配 | {} -> {} | 类型: {}", device.device_id, player_id, device.device_type.value)
            return device

        logger.warning("无可用设备 | 玩家: {} | 类型: {} | 标签: {}", player_id, device_type, tags)
        return None

    def release(self, device_id: str) -> None:
        """释放设备，使其可重新分配。"""
        device = self._devices.get(device_id)
        if not device:
            raise KeyError(f"设备 {device_id} 不存在")
        device.state = DeviceState.AVAILABLE
        device.assigned_to = ""
        logger.info("设备释放 | {}", device_id)

    def heartbeat(self, device_id: str) -> None:
        """更新设备心跳。"""
        device = self._devices.get(device_id)
        if device:
            device.last_heartbeat = time.time()

    def set_state(self, device_id: str, state: DeviceState) -> None:
        """设置设备状态。"""
        device = self._devices.get(device_id)
        if not device:
            raise KeyError(f"设备 {device_id} 不存在")
        device.state = state

    def check_health(self, timeout_seconds: float = 60) -> list[str]:
        """检查设备健康：超过 timeout 无心跳的标记为 offline。返回离线设备ID列表。"""
        now = time.time()
        offline = []
        for device in self._devices.values():
            if device.state == DeviceState.OFFLINE:
                continue
            if now - device.last_heartbeat > timeout_seconds:
                device.state = DeviceState.OFFLINE
                offline.append(device.device_id)
                logger.warning("设备离线 | {} | 最后心跳: {:.0f}s前", device.device_id, now - device.last_heartbeat)
        return offline

    def list_devices(self, device_type: DeviceType = None,
                     state: DeviceState = None) -> list[DeviceInfo]:
        """列出设备（可按类型/状态过滤）。"""
        devices = list(self._devices.values())
        if device_type:
            devices = [d for d in devices if d.device_type == device_type]
        if state:
            devices = [d for d in devices if d.state == state]
        return devices

    def auto_assign(self, player_configs: list[dict]) -> dict[str, Optional[str]]:
        """批量自动分配设备。

        Args:
            player_configs: [{"player_id": "p1", "device_type": "browser", "tags": [...]}]
        Returns:
            {player_id: device_id or None}
        """
        result = {}
        for cfg in player_configs:
            pid = cfg.get("player_id", "")
            dtype = DeviceType(cfg["device_type"]) if "device_type" in cfg else None
            tags = cfg.get("tags", [])
            device = self.acquire(pid, dtype, tags)
            result[pid] = device.device_id if device else None
        return result

    def release_all(self) -> int:
        """释放所有在用设备。"""
        count = 0
        for device in self._devices.values():
            if device.state == DeviceState.IN_USE:
                device.state = DeviceState.AVAILABLE
                device.assigned_to = ""
                count += 1
        return count

    def clear(self) -> None:
        """清空设备池。"""
        self._devices.clear()

    def get_summary(self) -> dict:
        """获取设备池摘要。"""
        by_type = {}
        by_state = {}
        for d in self._devices.values():
            by_type[d.device_type.value] = by_type.get(d.device_type.value, 0) + 1
            by_state[d.state.value] = by_state.get(d.state.value, 0) + 1
        return {
            "total": len(self._devices),
            "max": self.max_devices,
            "available": self.available_count,
            "by_type": by_type,
            "by_state": by_state,
            "devices": [
                {
                    "id": d.device_id,
                    "type": d.device_type.value,
                    "name": d.name,
                    "state": d.state.value,
                    "assigned_to": d.assigned_to,
                }
                for d in self._devices.values()
            ],
        }
