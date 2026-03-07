"""
多端协同测试 Phase3 测试（v9.0）

覆盖：NetworkSimulator、DevicePoolManager
"""

import asyncio
import time
import pytest

from src.testing.network_simulator import (
    NetworkProfile, NetworkConfig, NetworkEvent, NetworkSimulator, PROFILE_CONFIGS,
)
from src.testing.device_pool import (
    DeviceType, DeviceState, DeviceInfo, DevicePoolManager,
)


# ── NetworkConfig & Profile ─────────────────────

class TestNetworkModels:
    def test_profile_values(self):
        assert NetworkProfile.PERFECT == "perfect"
        assert NetworkProfile.MOBILE_3G == "3g"
        assert NetworkProfile.OFFLINE == "offline"

    def test_config_defaults(self):
        cfg = NetworkConfig()
        assert cfg.latency_ms == 0
        assert cfg.packet_loss == 0.0

    def test_config_from_profile_wifi(self):
        cfg = NetworkConfig.from_profile(NetworkProfile.WIFI)
        assert cfg.latency_ms == 20
        assert cfg.packet_loss == 0.0

    def test_config_from_profile_3g(self):
        cfg = NetworkConfig.from_profile(NetworkProfile.MOBILE_3G)
        assert cfg.latency_ms == 200
        assert cfg.packet_loss == 0.05

    def test_config_from_profile_offline(self):
        cfg = NetworkConfig.from_profile(NetworkProfile.OFFLINE)
        assert cfg.packet_loss == 1.0

    def test_all_profiles_have_config(self):
        for p in NetworkProfile:
            assert p in PROFILE_CONFIGS

    def test_network_event(self):
        e = NetworkEvent(player_id="p1", event_type="delay", detail="100ms")
        assert e.player_id == "p1"


# ── NetworkSimulator ────────────────────────────

class TestNetworkSimulator:
    def test_init(self):
        ns = NetworkSimulator()
        assert not ns.is_enabled

    def test_enable_disable(self):
        ns = NetworkSimulator()
        ns.enable()
        assert ns.is_enabled
        ns.disable()
        assert not ns.is_enabled

    def test_set_global(self):
        ns = NetworkSimulator()
        cfg = NetworkConfig(latency_ms=100)
        ns.set_global(cfg)
        assert ns.get_config("any").latency_ms == 100

    def test_set_player_overrides_global(self):
        ns = NetworkSimulator()
        ns.set_global(NetworkConfig(latency_ms=100))
        ns.set_player("p1", NetworkConfig(latency_ms=500))
        assert ns.get_config("p1").latency_ms == 500
        assert ns.get_config("p2").latency_ms == 100

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
        ns.clear()
        assert not ns.is_enabled
        assert ns.get_config("p1").latency_ms == 0

    @pytest.mark.asyncio
    async def test_simulate_disabled(self):
        ns = NetworkSimulator()
        result = await ns.simulate("p1")
        assert result is True  # disabled = no effect

    @pytest.mark.asyncio
    async def test_simulate_perfect(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig.from_profile(NetworkProfile.PERFECT))
        result = await ns.simulate("p1")
        assert result is True

    @pytest.mark.asyncio
    async def test_simulate_offline_drops(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig.from_profile(NetworkProfile.OFFLINE))
        results = [await ns.simulate("p1") for _ in range(10)]
        assert all(r is False for r in results)

    @pytest.mark.asyncio
    async def test_simulate_delay(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig(latency_ms=50, jitter_ms=0, packet_loss=0.0))
        start = time.time()
        await ns.simulate("p1")
        elapsed = time.time() - start
        assert elapsed >= 0.04  # at least ~40ms (some slack)

    @pytest.mark.asyncio
    async def test_simulate_records_events(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig(latency_ms=10, packet_loss=0.0))
        await ns.simulate("p1")
        assert len(ns.events) >= 1
        assert ns.events[0].event_type == "delay"

    def test_get_stats_empty(self):
        ns = NetworkSimulator()
        stats = ns.get_stats()
        assert stats["total_events"] == 0
        assert stats["enabled"] is False

    @pytest.mark.asyncio
    async def test_get_stats_with_data(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig(latency_ms=10, packet_loss=0.0))
        await ns.simulate("p1")
        await ns.simulate("p2")
        stats = ns.get_stats()
        assert stats["total_events"] >= 2
        assert "p1" in stats["player_stats"]

    @pytest.mark.asyncio
    async def test_simulate_jitter(self):
        ns = NetworkSimulator()
        ns.enable()
        ns.set_global(NetworkConfig(latency_ms=10, jitter_ms=5, packet_loss=0.0))
        await ns.simulate("p1")
        assert len(ns.events) >= 1


# ── DeviceInfo & DeviceType ─────────────────────

class TestDeviceModels:
    def test_device_type_values(self):
        assert DeviceType.BROWSER == "browser"
        assert DeviceType.ANDROID == "android"
        assert DeviceType.IOS == "ios"

    def test_device_state_values(self):
        assert DeviceState.AVAILABLE == "available"
        assert DeviceState.IN_USE == "in_use"

    def test_device_info(self):
        d = DeviceInfo(device_id="d1", device_type=DeviceType.BROWSER, name="Chrome")
        assert d.device_id == "d1"
        assert d.state == DeviceState.AVAILABLE


# ── DevicePoolManager ───────────────────────────

class TestDevicePoolManager:
    def test_init(self):
        pool = DevicePoolManager()
        assert pool.device_count == 0
        assert pool.available_count == 0

    def test_register(self):
        pool = DevicePoolManager()
        d = pool.register("d1", DeviceType.BROWSER, "Chrome")
        assert d.device_id == "d1"
        assert pool.device_count == 1

    def test_register_duplicate(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        with pytest.raises(ValueError, match="已存在"):
            pool.register("d1", DeviceType.BROWSER)

    def test_register_full(self):
        pool = DevicePoolManager(max_devices=2)
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.BROWSER)
        with pytest.raises(ValueError, match="已满"):
            pool.register("d3", DeviceType.BROWSER)

    def test_unregister(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.unregister("d1")
        assert pool.device_count == 0

    def test_unregister_not_found(self):
        pool = DevicePoolManager()
        with pytest.raises(KeyError):
            pool.unregister("nope")

    def test_get(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.ANDROID, "Pixel")
        d = pool.get("d1")
        assert d.name == "Pixel"
        assert pool.get("nope") is None

    def test_acquire(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        d = pool.acquire("p1")
        assert d.device_id == "d1"
        assert d.state == DeviceState.IN_USE
        assert d.assigned_to == "p1"

    def test_acquire_by_type(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.ANDROID)
        d = pool.acquire("p1", DeviceType.ANDROID)
        assert d.device_id == "d2"

    def test_acquire_by_tags(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER, tags=["chrome"])
        pool.register("d2", DeviceType.BROWSER, tags=["firefox"])
        d = pool.acquire("p1", tags=["firefox"])
        assert d.device_id == "d2"

    def test_acquire_none_available(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.acquire("p1")
        d = pool.acquire("p2")
        assert d is None

    def test_release(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.acquire("p1")
        pool.release("d1")
        d = pool.get("d1")
        assert d.state == DeviceState.AVAILABLE
        assert d.assigned_to == ""

    def test_release_not_found(self):
        pool = DevicePoolManager()
        with pytest.raises(KeyError):
            pool.release("nope")

    def test_heartbeat(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        old_hb = pool.get("d1").last_heartbeat
        time.sleep(0.01)
        pool.heartbeat("d1")
        assert pool.get("d1").last_heartbeat > old_hb

    def test_set_state(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.set_state("d1", DeviceState.MAINTENANCE)
        assert pool.get("d1").state == DeviceState.MAINTENANCE

    def test_set_state_not_found(self):
        pool = DevicePoolManager()
        with pytest.raises(KeyError):
            pool.set_state("nope", DeviceState.OFFLINE)

    def test_check_health(self):
        pool = DevicePoolManager()
        d = pool.register("d1", DeviceType.BROWSER)
        d.last_heartbeat = time.time() - 120  # 2 minutes ago
        offline = pool.check_health(timeout_seconds=60)
        assert "d1" in offline
        assert pool.get("d1").state == DeviceState.OFFLINE

    def test_check_health_ok(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        offline = pool.check_health(timeout_seconds=60)
        assert len(offline) == 0

    def test_list_devices(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.ANDROID)
        pool.register("d3", DeviceType.BROWSER)
        assert len(pool.list_devices()) == 3
        assert len(pool.list_devices(device_type=DeviceType.BROWSER)) == 2
        pool.acquire("p1")
        assert len(pool.list_devices(state=DeviceState.IN_USE)) == 1

    def test_auto_assign(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.ANDROID)
        result = pool.auto_assign([
            {"player_id": "p1", "device_type": "browser"},
            {"player_id": "p2", "device_type": "android"},
        ])
        assert result["p1"] == "d1"
        assert result["p2"] == "d2"

    def test_auto_assign_partial(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        result = pool.auto_assign([
            {"player_id": "p1", "device_type": "browser"},
            {"player_id": "p2", "device_type": "android"},
        ])
        assert result["p1"] == "d1"
        assert result["p2"] is None

    def test_release_all(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.ANDROID)
        pool.acquire("p1")
        pool.acquire("p2")
        count = pool.release_all()
        assert count == 2
        assert pool.available_count == 2

    def test_clear(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.clear()
        assert pool.device_count == 0

    def test_get_summary(self):
        pool = DevicePoolManager(max_devices=10)
        pool.register("d1", DeviceType.BROWSER, "Chrome")
        pool.register("d2", DeviceType.ANDROID, "Pixel")
        pool.acquire("p1")
        s = pool.get_summary()
        assert s["total"] == 2
        assert s["max"] == 10
        assert s["available"] == 1
        assert s["by_type"]["browser"] == 1
        assert len(s["devices"]) == 2
