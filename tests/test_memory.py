"""
记忆存储系统的单元测试。

验证：
- 数据库初始化和表创建
- 测试结果保存和查询
- 经验保存和查询
- 页面指纹更新和查询
- 统计信息
"""

import tempfile
from pathlib import Path

from src.memory.store import MemoryStore


class TestMemoryStore:
    """记忆存储测试。"""

    def _create_store(self) -> MemoryStore:
        """创建临时数据库用于测试。"""
        tmp = tempfile.mktemp(suffix=".db")
        return MemoryStore(db_path=Path(tmp))

    def test_init_creates_db(self) -> None:
        """初始化应创建数据库文件。"""
        store = self._create_store()
        assert store._db_path.exists() or store._conn is not None
        store.close()

    def test_save_and_query_history(self) -> None:
        """保存测试结果后应能查询到。"""
        store = self._create_store()
        rid = store.save_test_result(
            test_name="login_test",
            url="http://localhost:3000",
            total_steps=5,
            passed_steps=4,
            failed_steps=1,
            pass_rate=0.8,
        )
        assert rid > 0

        history = store.get_history()
        assert len(history) == 1
        assert history[0]["test_name"] == "login_test"
        assert history[0]["pass_rate"] == 0.8
        store.close()

    def test_query_by_url(self) -> None:
        """按URL过滤查询应正确。"""
        store = self._create_store()
        store.save_test_result(test_name="t1", url="http://localhost:3000/login", pass_rate=1.0)
        store.save_test_result(test_name="t2", url="http://localhost:3000/home", pass_rate=0.5)
        store.save_test_result(test_name="t3", url="http://example.com", pass_rate=0.9)

        results = store.get_history(url="localhost:3000")
        assert len(results) == 2
        store.close()

    def test_save_and_query_experience(self) -> None:
        """保存经验后应能查询到。"""
        store = self._create_store()
        eid = store.save_experience(
            category="selector",
            content="#login-btn selector often fails, use [data-testid=login] instead",
            relevance_score=0.9,
        )
        assert eid > 0

        exps = store.get_experiences(category="selector")
        assert len(exps) == 1
        assert "login" in exps[0]["content"]
        store.close()

    def test_page_fingerprint_create_and_update(self) -> None:
        """页面指纹应正确创建和更新。"""
        store = self._create_store()
        store.save_test_result(test_name="t1", url="http://example.com", pass_rate=0.8)
        fp = store.get_page_fingerprint("http://example.com")
        assert fp is not None
        assert fp["test_count"] == 1
        assert fp["avg_pass_rate"] == 0.8

        # 再测一次，应该更新
        store.save_test_result(test_name="t2", url="http://example.com", pass_rate=1.0)
        fp2 = store.get_page_fingerprint("http://example.com")
        assert fp2["test_count"] == 2
        assert fp2["avg_pass_rate"] == 0.9  # (0.8 + 1.0) / 2
        store.close()

    def test_stats(self) -> None:
        """统计信息应正确。"""
        store = self._create_store()
        assert store.get_stats()["total_tests"] == 0

        store.save_test_result(test_name="t1", url="http://a.com", pass_rate=1.0)
        store.save_experience(category="bug", content="test")

        stats = store.get_stats()
        assert stats["total_tests"] == 1
        assert stats["total_experiences"] == 1
        assert stats["known_pages"] == 1
        store.close()

    def test_history_limit(self) -> None:
        """查询限制应生效。"""
        store = self._create_store()
        for i in range(10):
            store.save_test_result(test_name=f"t{i}", url="http://a.com", pass_rate=0.5)

        results = store.get_history(limit=3)
        assert len(results) == 3
        store.close()
