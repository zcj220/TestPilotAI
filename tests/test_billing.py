"""
积分计量系统的单元测试
"""

import pytest

from src.billing.models import (
    API_COSTS,
    CREDIT_COSTS,
    OperationType,
    TestBill,
    UsageRecord,
    UsageSummary,
)
from src.billing.tracker import CreditTracker


class TestOperationType:
    """操作类型枚举测试。"""

    def test_all_types_have_credit_cost(self):
        for op in OperationType:
            assert op in CREDIT_COSTS

    def test_all_types_have_api_cost(self):
        for op in OperationType:
            assert op in API_COSTS

    def test_script_costs_1_credit(self):
        assert CREDIT_COSTS[OperationType.GENERATE_SCRIPT] == 1

    def test_repair_costs_3_credits(self):
        assert CREDIT_COSTS[OperationType.REPAIR_BUG] == 3

    def test_memory_compress_is_free(self):
        assert CREDIT_COSTS[OperationType.MEMORY_COMPRESS] == 0

    def test_step_costs_1_credit(self):
        assert CREDIT_COSTS[OperationType.EXECUTE_STEP] == 1


class TestUsageRecord:
    """用量记录测试。"""

    def test_create_record(self):
        r = UsageRecord(
            operation=OperationType.GENERATE_SCRIPT,
            credits=1,
            api_cost=0.008,
            detail="生成测试脚本",
        )
        assert r.credits == 1
        assert r.api_cost == 0.008
        assert r.detail == "生成测试脚本"

    def test_default_values(self):
        r = UsageRecord(operation=OperationType.EXECUTE_STEP)
        assert r.credits == 0
        assert r.api_cost == 0.0
        assert r.detail == ""


class TestTestBill:
    """测试账单测试。"""

    def test_empty_bill(self):
        bill = TestBill(test_name="测试", url="http://localhost")
        assert bill.total_credits == 0
        assert bill.total_api_cost == 0.0
        assert bill.breakdown == {}

    def test_bill_with_records(self):
        bill = TestBill(test_name="测试", url="http://localhost")
        bill.records.append(UsageRecord(
            operation=OperationType.GENERATE_SCRIPT, credits=1, api_cost=0.008,
        ))
        bill.records.append(UsageRecord(
            operation=OperationType.EXECUTE_STEP, credits=1, api_cost=0.007,
        ))
        bill.records.append(UsageRecord(
            operation=OperationType.EXECUTE_STEP, credits=1, api_cost=0.007,
        ))
        bill.records.append(UsageRecord(
            operation=OperationType.GENERATE_REPORT, credits=1, api_cost=0.013,
        ))
        assert bill.total_credits == 4
        assert bill.total_api_cost == pytest.approx(0.035, abs=0.001)
        assert bill.breakdown == {
            "generate_script": 1,
            "execute_step": 2,
            "generate_report": 1,
        }


class TestCreditTracker:
    """积分追踪器测试。"""

    def test_not_tracking_initially(self):
        tracker = CreditTracker()
        assert tracker.is_tracking is False
        assert tracker.get_current_credits() == 0

    def test_start_and_finish(self):
        tracker = CreditTracker()
        tracker.start_test("测试登录", "http://localhost:3000")
        assert tracker.is_tracking is True

        bill = tracker.finish_test()
        assert tracker.is_tracking is False
        assert bill is not None
        assert bill.test_name == "测试登录"
        assert bill.url == "http://localhost:3000"
        assert bill.end_time is not None

    def test_record_credits(self):
        tracker = CreditTracker()
        tracker.start_test("测试", "http://localhost")

        tracker.record(OperationType.GENERATE_SCRIPT, "生成脚本")
        assert tracker.get_current_credits() == 1

        tracker.record(OperationType.EXECUTE_STEP, "步骤1")
        tracker.record(OperationType.EXECUTE_STEP, "步骤2")
        assert tracker.get_current_credits() == 3

        tracker.record(OperationType.REPAIR_BUG, "修复Bug")
        assert tracker.get_current_credits() == 6

        tracker.record(OperationType.GENERATE_REPORT, "报告")
        assert tracker.get_current_credits() == 7

        bill = tracker.finish_test()
        assert bill is not None
        assert bill.total_credits == 7

    def test_finish_without_start(self):
        tracker = CreditTracker()
        bill = tracker.finish_test()
        assert bill is None

    def test_record_without_start(self):
        tracker = CreditTracker()
        record = tracker.record(OperationType.EXECUTE_STEP, "步骤1")
        assert record.credits == 1

    def test_history(self):
        tracker = CreditTracker()

        tracker.start_test("测试1", "http://a.com")
        tracker.record(OperationType.EXECUTE_STEP)
        tracker.finish_test()

        tracker.start_test("测试2", "http://b.com")
        tracker.record(OperationType.EXECUTE_STEP)
        tracker.record(OperationType.EXECUTE_STEP)
        tracker.finish_test()

        assert len(tracker.history) == 2
        assert tracker.history[0].total_credits == 1
        assert tracker.history[1].total_credits == 2

    def test_summary(self):
        tracker = CreditTracker()

        tracker.start_test("测试1", "http://a.com")
        tracker.record(OperationType.GENERATE_SCRIPT)
        tracker.record(OperationType.EXECUTE_STEP)
        tracker.record(OperationType.GENERATE_REPORT)
        tracker.finish_test()

        tracker.start_test("测试2", "http://b.com")
        tracker.record(OperationType.GENERATE_SCRIPT)
        tracker.record(OperationType.EXECUTE_STEP)
        tracker.record(OperationType.EXECUTE_STEP)
        tracker.record(OperationType.REPAIR_BUG)
        tracker.record(OperationType.GENERATE_REPORT)
        tracker.finish_test()

        summary = tracker.get_summary()
        assert summary.total_credits == 10
        assert summary.record_count == 8
        assert summary.breakdown["generate_script"] == 2
        assert summary.breakdown["execute_step"] == 3
        assert summary.breakdown["repair_bug"] == 3
        assert summary.breakdown["generate_report"] == 2


class TestTypicalScenario:
    """典型场景计费测试：20步测试 + 修复3个Bug。"""

    def test_typical_20_step_test(self):
        tracker = CreditTracker()
        tracker.start_test("电商测试", "http://localhost:3000")

        tracker.record(OperationType.GENERATE_SCRIPT)      # 1
        tracker.record(OperationType.GENERATE_TEST_DATA)    # 2

        for i in range(20):
            tracker.record(OperationType.EXECUTE_STEP)      # 20

        for i in range(3):
            tracker.record(OperationType.REPAIR_BUG)        # 9

        tracker.record(OperationType.GENERATE_REPORT)       # 1

        bill = tracker.finish_test()
        assert bill is not None
        # 1 + 2 + 20 + 9 + 1 = 33 积分
        assert bill.total_credits == 33
        # 估算成本约 0.051 元（Seed-1.8实际价格：输入0.8/输出2.0 元/百万token）
        assert bill.total_api_cost == pytest.approx(0.051, abs=0.01)
