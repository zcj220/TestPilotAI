"""设备池管理器测试（v9.0 Phase3）。"""

import time

import pytest

from src.testing.device_pool import (
    DeviceInfo,
    DevicePoolManager,
    DeviceState,
    DeviceType,
)


# ── 枚举和数据类 ──

class TestDeviceType:
    def test_values(self):
        assert DeviceType.BROWSER == "browser"
        assert DeviceType.ANDROID == "android"
        assert DeviceType.DESKTOP == "desktop"


class TestDeviceState:
    def test_values(self):
        assert DeviceState.AVAILABLE == "available"
        assert DeviceState.IN_USE == "in_use"
        assert DeviceState.OFFLINE == "offline"


class TestDeviceInfo:
    def test_defaults(self):
        d = DeviceInfo(device_id="d1", device_type=DeviceType.BROWSER)
        assert d.device_id == "d1"
        assert d.state == DeviceState.AVAILABLE
        assert d.assigned_to == ""
        assert d.tags == []


# ── DevicePoolManager ──

class TestDevicePoolManager:
    def test_initial_state(self):
        pool = DevicePoolManager()
        assert pool.device_count == 0
        assert pool.available_count == 0

    def test_register(self):
        pool = DevicePoolManager()
        d = pool.register("d1", DeviceType.BROWSER, name="Chrome")
        assert d.device_id == "d1"
        assert d.name == "Chrome"
        assert pool.device_count == 1

    def test_register_duplicate_raises(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        with pytest.raises(ValueError, match="已存在"):
            pool.register("d1", DeviceType.BROWSER)

    def test_register_pool_full(self):
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

    def test_unregister_nonexistent(self):
        pool = DevicePoolManager()
        with pytest.raises(KeyError):
            pool.unregister("nope")

    def test_get(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        assert pool.get("d1") is not None
        assert pool.get("d2") is None

    def test_acquire(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        d = pool.acquire("player1")
        assert d is not None
        assert d.device_id == "d1"
        assert d.state == DeviceState.IN_USE
        assert d.assigned_to == "player1"

    def test_acquire_by_type(self):
        pool = DevicePoolManager()
        pool.register("b1", DeviceType.BROWSER)
        pool.register("a1", DeviceType.ANDROID)
        d = pool.acquire("p1", device_type=DeviceType.ANDROID)
        assert d.device_id == "a1"

    def test_acquire_by_tags(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER, tags=["chrome"])
        pool.register("d2", DeviceType.BROWSER, tags=["firefox"])
        d = pool.acquire("p1", tags=["firefox"])
        assert d.device_id == "d2"

    def test_acquire_none_available(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.acquire("p1")  # 占用唯一设备
        d = pool.acquire("p2")
        assert d is None

    def test_release(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.acquire("p1")
        assert pool.available_count == 0
        pool.release("d1")
        assert pool.available_count == 1
        assert pool.get("d1").assigned_to == ""

    def test_release_nonexistent(self):
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

    def test_set_state_nonexistent(self):
        pool = DevicePoolManager()
        with pytest.raises(KeyError):
            pool.set_state("nope", DeviceState.OFFLINE)

    def test_check_health(self):
        pool = DevicePoolManager()
        d = pool.register("d1", DeviceType.BROWSER)
        d.last_heartbeat = time.time() - 120  # 2分钟前
        offline = pool.check_health(timeout_seconds=60)
        assert "d1" in offline
        assert pool.get("d1").state == DeviceState.OFFLINE

    def test_check_health_healthy(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        offline = pool.check_health(timeout_seconds=60)
        assert len(offline) == 0

    def test_list_devices(self):
        pool = DevicePoolManager()
        pool.register("b1", DeviceType.BROWSER)
        pool.register("a1", DeviceType.ANDROID)
        all_devs = pool.list_devices()
        assert len(all_devs) == 2
        browsers = pool.list_devices(device_type=DeviceType.BROWSER)
        assert len(browsers) == 1

    def test_list_devices_by_state(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.BROWSER)
        pool.acquire("p1")  # d1 -> IN_USE
        avail = pool.list_devices(state=DeviceState.AVAILABLE)
        assert len(avail) == 1

    def test_auto_assign(self):
        pool = DevicePoolManager()
        pool.register("b1", DeviceType.BROWSER)
        pool.register("a1", DeviceType.ANDROID)
        configs = [
            {"player_id": "p1", "device_type": "browser"},
            {"player_id": "p2", "device_type": "android"},
        ]
        result = pool.auto_assign(configs)
        assert result["p1"] == "b1"
        assert result["p2"] == "a1"

    def test_auto_assign_not_enough(self):
        pool = DevicePoolManager()
        pool.register("b1", DeviceType.BROWSER)
        configs = [
            {"player_id": "p1", "device_type": "browser"},
            {"player_id": "p2", "device_type": "browser"},
        ]
        result = pool.auto_assign(configs)
        assert result["p1"] == "b1"
        assert result["p2"] is None

    def test_release_all(self):
        pool = DevicePoolManager()
        pool.register("d1", DeviceType.BROWSER)
        pool.register("d2", DeviceType.BROWSER)
        pool.acquire("p1")
        pool.acquire("p2")
        assert pool.available_count == 0
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
        pool.register("b1", DeviceType.BROWSER)
        pool.register("a1", DeviceType.ANDROID)
        pool.acquire("p1")
        s = pool.get_summary()
        assert s["total"] == 2
        assert s["max"] == 10
        assert s["available"] == 1
        assert "browser" in s["by_type"]
        assert len(s["devices"]) == 2
