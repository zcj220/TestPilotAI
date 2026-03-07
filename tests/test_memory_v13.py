"""MemoryStore v1.3 增强功能 + MemoryCompressor 单元测试。"""

import json
import tempfile
from pathlib import Path

import pytest

from src.memory.store import MemoryStore
from src.memory.compressor import MemoryCompressor
from src.testing.models import BugReport, BugSeverity, StepResult, StepStatus, ActionType, TestReport


@pytest.fixture
def store(tmp_path):
    """创建临时数据库的MemoryStore。"""
    db_path = tmp_path / "test_memory.db"
    return MemoryStore(db_path=db_path)


@pytest.fixture
def compressor(store):
    return MemoryCompressor(store)


class TestBugPatterns:
    def test_save_new_pattern(self, store):
        record_id = store.save_bug_pattern(
            url="http://localhost:8080",
            severity="high",
            category="JS错误",
            title="Cannot read properties of undefined",
            description="删除按钮触发JS报错",
        )
        assert record_id > 0

    def test_hit_count_increments(self, store):
        url = "http://localhost:8080"
        store.save_bug_pattern(url=url, severity="high", category="JS错误", title="Bug A")
        store.save_bug_pattern(url=url, severity="high", category="JS错误", title="Bug A")
        store.save_bug_pattern(url=url, severity="high", category="JS错误", title="Bug A")

        patterns = store.get_bug_patterns(url=url)
        assert len(patterns) == 1
        assert patterns[0]["hit_count"] == 3

    def test_different_bugs_separate(self, store):
        url = "http://localhost:8080"
        store.save_bug_pattern(url=url, severity="high", category="JS错误", title="Bug A")
        store.save_bug_pattern(url=url, severity="medium", category="布局", title="Bug B")

        patterns = store.get_bug_patterns(url=url)
        assert len(patterns) == 2

    def test_mark_resolved(self, store):
        url = "http://localhost:8080"
        store.save_bug_pattern(url=url, severity="high", category="JS", title="Bug X")
        store.mark_bug_resolved(url=url, severity="high", category="JS", title="Bug X")

        # 默认只查未解决的
        patterns = store.get_bug_patterns(url=url, unresolved_only=True)
        assert len(patterns) == 0

        # 查全部包含已解决
        all_patterns = store.get_bug_patterns(url=url, unresolved_only=False)
        assert len(all_patterns) == 1
        assert all_patterns[0]["is_resolved"] == 1

    def test_resolved_reopen_on_new_hit(self, store):
        url = "http://localhost:8080"
        store.save_bug_pattern(url=url, severity="high", category="JS", title="Bug Y")
        store.mark_bug_resolved(url=url, severity="high", category="JS", title="Bug Y")

        # 再次出现 → 重新打开
        store.save_bug_pattern(url=url, severity="high", category="JS", title="Bug Y")
        patterns = store.get_bug_patterns(url=url, unresolved_only=True)
        assert len(patterns) == 1
        assert patterns[0]["is_resolved"] == 0
        assert patterns[0]["hit_count"] == 2


class TestFixExperiences:
    def test_save_and_query(self, store):
        record_id = store.save_fix_experience(
            url="http://localhost:8080",
            bug_title="小计计算错误",
            bug_severity="high",
            bug_category="计算错误",
            bug_description="subtotal未乘数量",
            fix_analysis="app.js第45行subtotal应为price*qty",
            fix_patches_json=json.dumps([{"file": "app.js", "old": "item.price", "new": "item.price * item.qty"}]),
            fix_confidence=0.9,
            fix_verified=True,
        )
        assert record_id > 0

        fixes = store.get_fix_experiences(url="localhost:8080")
        assert len(fixes) == 1
        assert fixes[0]["fix_verified"] == 1
        assert fixes[0]["fix_confidence"] == 0.9

    def test_verified_first(self, store):
        url = "http://localhost:8080"
        store.save_fix_experience(url=url, bug_title="Bug1", bug_severity="low", fix_verified=False)
        store.save_fix_experience(url=url, bug_title="Bug2", bug_severity="high", fix_verified=True)

        fixes = store.get_fix_experiences(url=url)
        assert fixes[0]["bug_title"] == "Bug2"  # verified排前面


class TestContextRetrieval:
    def test_empty_context(self, store):
        ctx = store.get_context_for_url("http://nonexistent.com")
        assert ctx == ""

    def test_context_with_bugs(self, store):
        url = "http://localhost:8080"
        store.save_bug_pattern(url=url, severity="high", category="JS", title="undefined error")
        ctx = store.get_context_for_url(url)
        assert "undefined error" in ctx
        assert "已知Bug" in ctx

    def test_context_with_fixes(self, store):
        url = "http://localhost:8080"
        store.save_fix_experience(
            url=url, bug_title="计算错误", bug_severity="high",
            fix_analysis="乘法遗漏", fix_verified=True,
        )
        ctx = store.get_context_for_url(url)
        assert "修复经验" in ctx
        assert "计算错误" in ctx

    def test_context_max_chars(self, store):
        url = "http://localhost:8080"
        for i in range(20):
            store.save_bug_pattern(
                url=url, severity="high", category=f"cat{i}",
                title=f"很长的Bug标题描述信息第{i}条" * 5,
            )
        ctx = store.get_context_for_url(url, max_chars=200)
        assert len(ctx) <= 200

    def test_context_with_history(self, store):
        url = "http://localhost:8080"
        store.save_test_result(test_name="test1", url=url, pass_rate=0.8)
        store.save_test_result(test_name="test2", url=url, pass_rate=0.9)
        ctx = store.get_context_for_url(url)
        assert "历史" in ctx
        assert "2次" in ctx


class TestCleanup:
    def test_cleanup_old_history(self, store):
        # 手动插入一条"过期"记录
        store._conn.execute(
            """INSERT INTO test_history
               (test_name, url, created_at) VALUES (?, ?, ?)""",
            ("old_test", "http://old.com", "2020-01-01T00:00:00+00:00"),
        )
        store._conn.commit()

        stats = store.cleanup(history_days=30)
        assert stats["deleted_history"] >= 1

    def test_cleanup_excess_bug_patterns(self, store):
        url = "http://localhost:8080"
        for i in range(15):
            store.save_bug_pattern(url=url, severity="low", category=f"c{i}", title=f"Bug{i}")

        stats = store.cleanup(max_summaries_per_url=5)
        remaining = store.get_bug_patterns(url=url, unresolved_only=False, limit=100)
        assert len(remaining) <= 5


class TestMemoryCompressor:
    def _make_report(self, url="http://localhost:8080", bugs=None):
        report = TestReport(test_name="test", url=url)
        report.bugs = bugs or []
        return report

    def test_extract_empty_report(self, compressor):
        report = self._make_report(bugs=[])
        stats = compressor.extract_from_report(report)
        assert stats["bugs_total"] == 0
        assert stats["new_patterns"] == 0

    def test_extract_bugs(self, compressor, store):
        bugs = [
            BugReport(severity=BugSeverity.HIGH, category="JS", title="Bug1"),
            BugReport(severity=BugSeverity.MEDIUM, category="布局", title="Bug2"),
        ]
        report = self._make_report(bugs=bugs)
        stats = compressor.extract_from_report(report)
        assert stats["bugs_total"] == 2
        assert stats["new_patterns"] == 2

        patterns = store.get_bug_patterns(url="http://localhost:8080")
        assert len(patterns) == 2

    def test_extract_fix_experience(self, compressor, store):
        bug = BugReport(severity=BugSeverity.HIGH, category="计算", title="小计错误", description="未乘数量")
        record_id = compressor.extract_fix_experience(
            url="http://localhost:8080",
            bug=bug,
            fix_analysis="price应乘以qty",
            fix_patches=[{"file": "app.js", "old": "item.price", "new": "item.price*item.qty"}],
            fix_confidence=0.9,
            fix_verified=True,
        )
        assert record_id > 0

        # 验证Bug模式被标记为已修复
        patterns = store.get_bug_patterns(url="http://localhost:8080", unresolved_only=True)
        resolved = [p for p in patterns if p["title"] == "小计错误"]
        assert len(resolved) == 0  # 已标记resolved

    def test_get_prompt_context(self, compressor, store):
        store.save_bug_pattern(url="http://localhost:8080", severity="high", category="JS", title="Error X")
        ctx = compressor.get_prompt_context("http://localhost:8080")
        assert "Error X" in ctx


class TestAICompress:
    """AI周期压缩测试（v1.4）。"""

    def _make_mock_ai(self, response="这个页面主要存在计算类Bug，小计未乘数量，建议检查所有乘法运算。"):
        class MockAI:
            def __init__(self, resp):
                self._resp = resp
            def chat(self, prompt):
                return self._resp
        return MockAI(response)

    def _seed_data(self, store, url="http://localhost:8080", test_count=3):
        """填充足够的测试数据以触发AI压缩。"""
        for _ in range(test_count):
            store.save_test_result(
                test_name="test", url=url, total_steps=10, passed_steps=8,
                failed_steps=2, bug_count=2, pass_rate=0.8,
            )
        store.save_bug_pattern(url=url, severity="high", category="计算", title="小计错误")
        store.save_bug_pattern(url=url, severity="medium", category="UI", title="删除无响应")

    def test_compress_triggers_after_threshold(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=3)
        mock_ai = self._make_mock_ai()
        compressor = MemoryCompressor(store, ai_client=mock_ai, compress_threshold=3)

        result = compressor.ai_compress_if_needed(url)
        assert result is not None
        assert "计算" in result

        # 验证保存到了experiences表
        exps = store.get_experiences(category="ai_summary")
        assert len(exps) == 1
        assert url in exps[0]["content"]

    def test_no_compress_below_threshold(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=2)
        mock_ai = self._make_mock_ai()
        compressor = MemoryCompressor(store, ai_client=mock_ai, compress_threshold=3)

        result = compressor.ai_compress_if_needed(url)
        assert result is None

    def test_no_compress_without_ai(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=5)
        compressor = MemoryCompressor(store, ai_client=None)

        result = compressor.ai_compress_if_needed(url)
        assert result is None

    def test_no_compress_without_bugs(self, store):
        url = "http://localhost:8080"
        # 只有测试记录，没有Bug模式
        for _ in range(5):
            store.save_test_result(test_name="test", url=url, total_steps=10,
                                   passed_steps=10, pass_rate=1.0)
        mock_ai = self._make_mock_ai()
        compressor = MemoryCompressor(store, ai_client=mock_ai, compress_threshold=3)

        result = compressor.ai_compress_if_needed(url)
        assert result is None

    def test_skip_if_summary_already_fresh(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=3)
        mock_ai = self._make_mock_ai()
        compressor = MemoryCompressor(store, ai_client=mock_ai, compress_threshold=3)

        # 第一次压缩
        result1 = compressor.ai_compress_if_needed(url)
        assert result1 is not None

        # 第二次应跳过（总结已是最新）
        result2 = compressor.ai_compress_if_needed(url)
        assert result2 is None

        # experiences中只有1条
        exps = store.get_experiences(category="ai_summary")
        assert len(exps) == 1

    def test_compress_truncates_long_summary(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=3)
        long_response = "A" * 500
        mock_ai = self._make_mock_ai(long_response)
        compressor = MemoryCompressor(store, ai_client=mock_ai, compress_threshold=3)

        result = compressor.ai_compress_if_needed(url)
        assert result is not None
        assert len(result) <= 300

    def test_compress_handles_ai_error(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=3)

        class ErrorAI:
            def chat(self, prompt):
                raise RuntimeError("API error")

        compressor = MemoryCompressor(store, ai_client=ErrorAI(), compress_threshold=3)
        result = compressor.ai_compress_if_needed(url)
        assert result is None

    def test_build_compress_prompt_content(self, store):
        url = "http://localhost:8080"
        self._seed_data(store, url, test_count=3)
        compressor = MemoryCompressor(store, compress_threshold=3)

        fp = store.get_page_fingerprint(url)
        bugs = store.get_bug_patterns(url=url, unresolved_only=False)
        fixes = store.get_fix_experiences(url=url)
        prompt = compressor._build_compress_prompt(url, bugs, fixes, fp)

        assert url in prompt
        assert "小计错误" in prompt
        assert "删除无响应" in prompt
        assert "经验总结" in prompt


class TestStatsIncludeNewTables:
    def test_stats_keys(self, store):
        stats = store.get_stats()
        assert "bug_patterns" in stats
        assert "fix_experiences" in stats
        assert stats["bug_patterns"] == 0
        assert stats["fix_experiences"] == 0
