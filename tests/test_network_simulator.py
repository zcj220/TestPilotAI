"""网络模拟器测试（v9.0 Phase3）。"""

import asyncio
from unittest.mock import patch

import pytest

from src.testing.network_simulator import (
    NetworkConfig,
    NetworkEvent,
    NetworkProfile,
    NetworkSimulator,
    PROFILE_CONFIGS,
)


# ── NetworkProfile 枚举 ──

class TestNetworkProfile:
    def test_all_profiles_have_config(self):
        for p in NetworkProfile:
            assert p in PROFILE_CONFIGS

    def test_offline_full_loss(self):
        cfg = PROFILE_CONFIGS[NetworkProfile.OFFLINE]
        assert cfg["packet_loss"] == 1.0

    def test_perfect_no_issues(self):
        cfg = PROFILE_CONFIGS[NetworkProfile.PERFECT]
        assert cfg["latency_ms"] == 0
        assert cfg["packet_loss"] == 0.0


# ── NetworkConfig ──

class TestNetworkConfig:
    def test_defaults(self):
        c = NetworkConfig()
        assert c.latency_ms == 0
        assert c.jitter_ms == 0
        assert c.packet_loss == 0.0
        assert c.bandwidth_kbps == 0

    def test_from_profile_4g(self):
        c = NetworkConfig.from_profile(NetworkProfile.MOBILE_4G)
        assert c.latency_ms == 50
        assert c.packet_loss == 0.01

    def test_from_profile_3g(self):
        c = NetworkConfig.from_profile(NetworkProfile.MOBILE_3G)
        assert c.latency_ms == 200
        assert c.packet_loss == 0.05

    def test_from_profile_slow(self):
        c = NetworkConfig.from_profile(NetworkProfile.SLOW)
        assert c.latency_ms == 500


# ── NetworkEvent ──

class TestNetworkEvent:
    def test_creation(self):
        e = NetworkEvent(player_id="p1", event_type="drop", detail="丢包")
        assert e.player_id == "p1"
        assert e.event_type == "drop"


# ── NetworkSimulator ──

class TestNetworkSimulator:
    def test_initial_state(self):
        ns = NetworkSimulator()
        assert not ns.is_enabled
        assert len(ns.events) == 0

    def test_enable_disable(self):
        ns = NetworkSimulator()
        ns.enable()
        assert ns.is_enabled
        ns.disable()
        assert not ns.is_enabled

    def test_set_global(self):
        ns = NetworkSimulator()
        cfg = NetworkConfig(latency_ms=100, packet_loss=0.1)
        ns.set_global(cfg)
        assert ns.get_config("any_player").latency_ms == 100

    def test_set_player_overrides_global(self):
        ns = NetworkSimulator()
        ns.set_global(NetworkConfig(latency_ms=100))
        ns.set_player("p1", NetworkConfig(latency_ms=500))
        assert ns.get_config("p1").latency_ms == 500
        assert ns.get_config("p2").latency_ms == 100  # 回退到全局

    def test_remove_player(self):
        ns = NetworkSimulator()
        ns.set_global(NetworkConfig(latency_ms=50))
        ns.set_player("p1", NetworkConfig(latency_ms=999))
        ns.remove_player("p1")
        assert ns.get_config("p1").latency_ms == 50

    def test_clear(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig(latency_ms=100))
        ns.set_player("p1", NetworkConfig(latency_ms=200))
        ns.events.append(NetworkEvent(player_id="p1", event_type="drop", detail="test"))
        ns.clear()
        assert not ns.is_enabled
        assert len(ns.events) == 0
        assert ns.get_config("p1").latency_ms == 0

    @pytest.mark.asyncio
    async def test_simulate_disabled_always_passes(self):
        ns = NetworkSimulator()
        # 即使配置了100%丢包，禁用时也应通过
        ns.set_global(NetworkConfig(packet_loss=1.0))
        result = await ns.simulate("p1")
        assert result is True

    @pytest.mark.asyncio
    async def test_simulate_offline_drops(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_player("p1", NetworkConfig.from_profile(NetworkProfile.OFFLINE))
        result = await ns.simulate("p1")
        assert result is False
        assert len(ns.events) == 1
        assert ns.events[0].event_type == "drop"

    @pytest.mark.asyncio
    async def test_simulate_perfect_passes(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_player("p1", NetworkConfig.from_profile(NetworkProfile.PERFECT))
        result = await ns.simulate("p1")
        assert result is True

    @pytest.mark.asyncio
    async def test_simulate_with_latency(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_player("p1", NetworkConfig(latency_ms=10, jitter_ms=0, packet_loss=0.0))
        result = await ns.simulate("p1")
        assert result is True
        assert len(ns.events) == 1
        assert ns.events[0].event_type == "delay"

    def test_get_stats_empty(self):
        ns = NetworkSimulator()
        stats = ns.get_stats()
        assert stats["enabled"] is False
        assert stats["total_events"] == 0

    def test_get_stats_with_events(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig(latency_ms=50))
        ns.events.append(NetworkEvent(player_id="p1", event_type="drop", detail="test"))
        ns.events.append(NetworkEvent(player_id="p1", event_type="delay", detail="50ms"))
        ns.events.append(NetworkEvent(player_id="p2", event_type="delay", detail="50ms"))
        stats = ns.get_stats()
        assert stats["total_events"] == 3
        assert stats["total_drops"] == 1
        assert stats["total_delays"] == 2
        assert "p1" in stats["player_stats"]
        assert stats["player_stats"]["p1"]["drops"] == 1
