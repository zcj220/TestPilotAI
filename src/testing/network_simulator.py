"""
网络模拟器（v9.0 Phase3）

模拟各种网络条件：延迟、丢包、限速、断网。
可针对单个端或全局设置，用于测试弱网/断网下的多端行为。
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from loguru import logger


class NetworkProfile(str, Enum):
    """预设网络环境。"""
    PERFECT = "perfect"        # 无延迟无丢包
    WIFI = "wifi"              # 好WiFi: 20ms延迟, 0%丢包
    MOBILE_4G = "4g"           # 4G: 50ms延迟, 1%丢包
    MOBILE_3G = "3g"           # 3G: 200ms延迟, 5%丢包
    SLOW = "slow"              # 慢网: 500ms延迟, 10%丢包
    UNSTABLE = "unstable"      # 不稳定: 100-2000ms随机延迟, 15%丢包
    OFFLINE = "offline"        # 断网: 100%丢包


PROFILE_CONFIGS = {
    NetworkProfile.PERFECT:   {"latency_ms": 0, "jitter_ms": 0, "packet_loss": 0.0, "bandwidth_kbps": 0},
    NetworkProfile.WIFI:      {"latency_ms": 20, "jitter_ms": 5, "packet_loss": 0.0, "bandwidth_kbps": 50000},
    NetworkProfile.MOBILE_4G: {"latency_ms": 50, "jitter_ms": 20, "packet_loss": 0.01, "bandwidth_kbps": 20000},
    NetworkProfile.MOBILE_3G: {"latency_ms": 200, "jitter_ms": 80, "packet_loss": 0.05, "bandwidth_kbps": 2000},
    NetworkProfile.SLOW:      {"latency_ms": 500, "jitter_ms": 200, "packet_loss": 0.10, "bandwidth_kbps": 500},
    NetworkProfile.UNSTABLE:  {"latency_ms": 100, "jitter_ms": 900, "packet_loss": 0.15, "bandwidth_kbps": 1000},
    NetworkProfile.OFFLINE:   {"latency_ms": 0, "jitter_ms": 0, "packet_loss": 1.0, "bandwidth_kbps": 0},
}


@dataclass
class NetworkConfig:
    """网络模拟配置。"""
    latency_ms: int = 0          # 基础延迟（毫秒）
    jitter_ms: int = 0           # 抖动范围（毫秒）
    packet_loss: float = 0.0     # 丢包率 0.0-1.0
    bandwidth_kbps: int = 0      # 带宽限制（kbps，0=不限）

    @classmethod
    def from_profile(cls, profile: NetworkProfile) -> "NetworkConfig":
        return cls(**PROFILE_CONFIGS[profile])


@dataclass
class NetworkEvent:
    """网络事件记录。"""
    player_id: str
    event_type: str       # delay / drop / throttle / error
    detail: str
    timestamp: float = 0.0


class NetworkSimulator:
    """网络模拟器：为每个端注入网络条件。"""

    def __init__(self) -> None:
        self._configs: dict[str, NetworkConfig] = {}
        self._global_config: Optional[NetworkConfig] = None
        self._enabled = False
        self.events: list[NetworkEvent] = []

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def enable(self) -> None:
        self._enabled = True
        logger.info("网络模拟已启用")

    def disable(self) -> None:
        self._enabled = False
        logger.info("网络模拟已禁用")

    def set_global(self, config: NetworkConfig) -> None:
        """设置全局网络条件。"""
        self._global_config = config
        logger.info("全局网络: latency={}ms jitter={}ms loss={:.0%} bw={}kbps",
                     config.latency_ms, config.jitter_ms, config.packet_loss, config.bandwidth_kbps)

    def set_player(self, player_id: str, config: NetworkConfig) -> None:
        """为指定端设置网络条件。"""
        self._configs[player_id] = config
        logger.info("端 {} 网络: latency={}ms loss={:.0%}",
                     player_id, config.latency_ms, config.packet_loss)

    def remove_player(self, player_id: str) -> None:
        """移除指定端的网络配置（回退到全局）。"""
        self._configs.pop(player_id, None)

    def get_config(self, player_id: str) -> NetworkConfig:
        """获取指定端的有效网络配置。"""
        return self._configs.get(player_id, self._global_config or NetworkConfig())

    def clear(self) -> None:
        self._configs.clear()
        self._global_config = None
        self.events.clear()
        self._enabled = False

    async def simulate(self, player_id: str) -> bool:
        """模拟网络条件。返回 False 表示丢包（请求应被丢弃）。"""
        if not self._enabled:
            return True

        config = self.get_config(player_id)

        # 丢包判定
        if config.packet_loss > 0 and random.random() < config.packet_loss:
            self.events.append(NetworkEvent(
                player_id=player_id, event_type="drop",
                detail=f"丢包 (rate={config.packet_loss:.0%})",
                timestamp=time.time(),
            ))
            return False

        # 延迟注入
        delay = config.latency_ms
        if config.jitter_ms > 0:
            delay += random.randint(-config.jitter_ms, config.jitter_ms)
            delay = max(0, delay)

        if delay > 0:
            self.events.append(NetworkEvent(
                player_id=player_id, event_type="delay",
                detail=f"延迟 {delay}ms",
                timestamp=time.time(),
            ))
            await asyncio.sleep(delay / 1000.0)

        return True

    def get_stats(self) -> dict:
        """获取网络模拟统计。"""
        total = len(self.events)
        drops = sum(1 for e in self.events if e.event_type == "drop")
        delays = [e for e in self.events if e.event_type == "delay"]

        player_stats = {}
        for pid in set(e.player_id for e in self.events):
            p_events = [e for e in self.events if e.player_id == pid]
            p_drops = sum(1 for e in p_events if e.event_type == "drop")
            player_stats[pid] = {
                "total_events": len(p_events),
                "drops": p_drops,
                "drop_rate": round(p_drops / max(len(p_events), 1) * 100, 1),
            }

        return {
            "enabled": self._enabled,
            "total_events": total,
            "total_drops": drops,
            "total_delays": len(delays),
            "global_config": {
                "latency_ms": self._global_config.latency_ms if self._global_config else 0,
                "jitter_ms": self._global_config.jitter_ms if self._global_config else 0,
                "packet_loss": self._global_config.packet_loss if self._global_config else 0,
                "bandwidth_kbps": self._global_config.bandwidth_kbps if self._global_config else 0,
            },
            "player_configs": {
                pid: {"latency_ms": c.latency_ms, "packet_loss": c.packet_loss}
                for pid, c in self._configs.items()
            },
            "player_stats": player_stats,
        }
