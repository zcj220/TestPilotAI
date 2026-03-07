"""
积分追踪器

在测试执行过程中追踪每个操作的积分消耗，
生成账单和用量统计。支持持久化到 SQLite。
"""

from datetime import datetime, timezone
from typing import Optional

from loguru import logger

from src.billing.models import (
    API_COSTS,
    CREDIT_COSTS,
    OperationType,
    TestBill,
    UsageRecord,
    UsageSummary,
)


class CreditTracker:
    """积分追踪器。

    在测试流程中调用 record() 记录每次操作，
    测试结束后调用 get_bill() 获取完整账单。

    典型使用：
        tracker = CreditTracker()
        tracker.start_test("测试登录", "http://localhost:3000")
        tracker.record(OperationType.GENERATE_SCRIPT, "生成测试脚本")
        tracker.record(OperationType.EXECUTE_STEP, "步骤1: 导航到首页")
        bill = tracker.finish_test()
    """

    def __init__(self) -> None:
        self._current_bill: Optional[TestBill] = None
        self._history: list[TestBill] = []

    def start_test(self, test_name: str, url: str) -> None:
        """开始新测试的计量。"""
        self._current_bill = TestBill(
            test_name=test_name,
            url=url,
        )
        logger.debug("积分追踪开始 | {}", test_name)

    def record(self, operation: OperationType, detail: str = "") -> UsageRecord:
        """记录一次操作的积分消耗。

        Args:
            operation: 操作类型
            detail: 操作详情描述

        Returns:
            UsageRecord: 本次操作的用量记录
        """
        credits = CREDIT_COSTS.get(operation, 0)
        api_cost = API_COSTS.get(operation, 0.0)

        record = UsageRecord(
            operation=operation,
            credits=credits,
            api_cost=api_cost,
            detail=detail,
        )

        if self._current_bill:
            self._current_bill.records.append(record)

        logger.debug(
            "积分消耗 | {} | {}积分 | ~{}元 | {}",
            operation.value, credits, f"{api_cost:.3f}", detail,
        )

        return record

    def finish_test(self) -> Optional[TestBill]:
        """结束当前测试的计量，返回账单。"""
        if not self._current_bill:
            return None

        self._current_bill.end_time = datetime.now(timezone.utc)
        bill = self._current_bill
        self._history.append(bill)
        self._current_bill = None

        logger.info(
            "测试账单 | {} | 总积分={} | 估算成本={}元",
            bill.test_name,
            bill.total_credits,
            f"{bill.total_api_cost:.3f}",
        )

        return bill

    def get_current_credits(self) -> int:
        """获取当前测试已消耗的积分。"""
        if not self._current_bill:
            return 0
        return self._current_bill.total_credits

    def get_summary(self) -> UsageSummary:
        """获取所有历史测试的用量统计。"""
        total_credits = 0
        total_cost = 0.0
        total_records = 0
        breakdown: dict[str, int] = {}

        for bill in self._history:
            total_credits += bill.total_credits
            total_cost += bill.total_api_cost
            total_records += len(bill.records)
            for key, val in bill.breakdown.items():
                breakdown[key] = breakdown.get(key, 0) + val

        return UsageSummary(
            total_credits=total_credits,
            total_api_cost=total_cost,
            record_count=total_records,
            breakdown=breakdown,
        )

    @property
    def history(self) -> list[TestBill]:
        """历史账单列表。"""
        return list(self._history)

    @property
    def is_tracking(self) -> bool:
        """是否正在追踪。"""
        return self._current_bill is not None
