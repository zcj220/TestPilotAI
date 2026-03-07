"""
跨端状态一致性验证器（v9.0 Phase2）

所有端同时截图 → 分析差异 → 生成一致性报告。
支持：文本对比、截图哈希对比、结构相似度、差异报告。
"""

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger


@dataclass
class ScreenCapture:
    """一端的截图数据。"""
    player_id: str
    path: Path = None
    source: str = ""
    text_content: str = ""
    hash: str = ""
    captured_at: float = 0.0


@dataclass
class DiffItem:
    """一条差异记录。"""
    field: str               # 差异字段
    player_a: str
    player_b: str
    value_a: str
    value_b: str
    severity: str = "warning"  # info / warning / critical


@dataclass
class ConsistencyReport:
    """一致性检查报告。"""
    consistent: bool
    player_count: int
    checked_at: float = 0.0
    diffs: list[DiffItem] = field(default_factory=list)
    captures: list[ScreenCapture] = field(default_factory=list)
    score: float = 100.0      # 一致性得分 0-100

    @property
    def diff_count(self) -> int:
        return len(self.diffs)

    def to_dict(self) -> dict:
        return {
            "consistent": self.consistent,
            "score": round(self.score, 1),
            "player_count": self.player_count,
            "diff_count": self.diff_count,
            "diffs": [
                {
                    "field": d.field,
                    "player_a": d.player_a,
                    "player_b": d.player_b,
                    "value_a": d.value_a[:200],
                    "value_b": d.value_b[:200],
                    "severity": d.severity,
                }
                for d in self.diffs
            ],
            "captures": [
                {"player_id": c.player_id, "hash": c.hash}
                for c in self.captures
            ],
        }


class ConsistencyChecker:
    """跨端一致性验证器。"""

    def __init__(self) -> None:
        self.reports: list[ConsistencyReport] = []

    async def check(self, orchestrator: Any, player_ids: list[str] = None,
                    check_source: bool = True, check_screenshot: bool = True) -> ConsistencyReport:
        """对指定端执行一致性检查。"""
        pids = player_ids or list(orchestrator.players.keys())
        if len(pids) < 2:
            return ConsistencyReport(consistent=True, player_count=len(pids), checked_at=time.time())

        captures = []
        for pid in pids:
            cap = ScreenCapture(player_id=pid, captured_at=time.time())
            slot = orchestrator.get_player(pid)
            if slot and slot.controller:
                try:
                    if check_source:
                        cap.source = await slot.controller.get_page_source()
                        cap.hash = hashlib.md5(cap.source.encode()).hexdigest()
                    if check_screenshot:
                        path = await slot.controller.screenshot(f"consistency_{pid}")
                        cap.path = path
                except Exception as e:
                    logger.warning("一致性截图失败 | {} | {}", pid, e)
            captures.append(cap)

        diffs = []
        if check_source:
            diffs.extend(self._compare_sources(captures))

        score = self._calculate_score(captures, diffs)
        report = ConsistencyReport(
            consistent=len(diffs) == 0,
            player_count=len(pids),
            checked_at=time.time(),
            diffs=diffs,
            captures=captures,
            score=score,
        )
        self.reports.append(report)
        logger.info("一致性检查完成 | 端数: {} | 差异: {} | 得分: {:.1f}",
                     len(pids), len(diffs), score)
        return report

    def _compare_sources(self, captures: list[ScreenCapture]) -> list[DiffItem]:
        """比较各端的页面源码。"""
        diffs = []
        hashes = {}
        for cap in captures:
            if cap.hash:
                hashes[cap.player_id] = cap.hash

        unique_hashes = set(hashes.values())
        if len(unique_hashes) <= 1:
            return diffs  # 全部一致

        # 两两比较
        pids = list(hashes.keys())
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                if hashes[pids[i]] != hashes[pids[j]]:
                    cap_a = next(c for c in captures if c.player_id == pids[i])
                    cap_b = next(c for c in captures if c.player_id == pids[j])
                    diff_detail = self._find_text_diff(cap_a.source, cap_b.source)
                    diffs.append(DiffItem(
                        field="page_source",
                        player_a=pids[i],
                        player_b=pids[j],
                        value_a=f"hash={hashes[pids[i]][:8]}",
                        value_b=f"hash={hashes[pids[j]][:8]}",
                        severity="warning" if diff_detail["similarity"] > 0.8 else "critical",
                    ))
        return diffs

    def _find_text_diff(self, text_a: str, text_b: str) -> dict:
        """简单文本相似度计算。"""
        if not text_a or not text_b:
            return {"similarity": 0, "diff_chars": max(len(text_a), len(text_b))}

        set_a = set(text_a.split())
        set_b = set(text_b.split())
        if not set_a and not set_b:
            return {"similarity": 1.0, "diff_chars": 0}

        intersection = set_a & set_b
        union = set_a | set_b
        similarity = len(intersection) / len(union) if union else 1.0
        return {"similarity": similarity, "diff_chars": len(union - intersection)}

    def _calculate_score(self, captures: list[ScreenCapture], diffs: list[DiffItem]) -> float:
        """计算一致性得分（0-100）。"""
        if not captures or len(captures) < 2:
            return 100.0

        # 基础分：无差异100分
        score = 100.0

        # 每个差异扣分
        for d in diffs:
            if d.severity == "critical":
                score -= 20
            elif d.severity == "warning":
                score -= 10
            else:
                score -= 5

        # hash 一致性加分
        hashes = [c.hash for c in captures if c.hash]
        if hashes and len(set(hashes)) == 1:
            score = max(score, 95)

        return max(0, min(100, score))

    def compare_text_content(self, texts: dict[str, str]) -> list[DiffItem]:
        """比较多端的文本内容。"""
        diffs = []
        pids = list(texts.keys())
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                if texts[pids[i]] != texts[pids[j]]:
                    diffs.append(DiffItem(
                        field="text_content",
                        player_a=pids[i],
                        player_b=pids[j],
                        value_a=texts[pids[i]][:100],
                        value_b=texts[pids[j]][:100],
                        severity="warning",
                    ))
        return diffs

    def get_summary(self) -> dict:
        """获取历史检查摘要。"""
        total = len(self.reports)
        consistent = sum(1 for r in self.reports if r.consistent)
        avg_score = sum(r.score for r in self.reports) / max(total, 1)
        return {
            "total_checks": total,
            "consistent_count": consistent,
            "inconsistent_count": total - consistent,
            "avg_score": round(avg_score, 1),
            "consistency_rate": round(consistent / max(total, 1) * 100, 1),
        }
