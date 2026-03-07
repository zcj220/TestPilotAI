"""
记忆压缩器（v1.3 → v1.4）

两层压缩策略：
1. 规则压缩（零成本）：从结构化BugReport/FixPlan字段直接提取记忆
2. AI周期压缩（低频）：累积N次后，让AI合并为跨次经验总结

核心理念（来自用户）：
- Bug报告和修复方案都是结构化字段，记忆直接从字段提取
- Bug发现是我们应用干的，修复方案是编程AI干的
- 经验 = Bug发现 + 修复方案，两者合在一起才是完整记忆

v1.4 新增：
- ai_compress: 累积N次测试后，用AI将Bug模式+修复经验压缩为一句话经验总结
- 触发条件：同URL测试≥compress_threshold次，且有未压缩的新Bug模式
- 结果存入experiences表，category="ai_summary"
"""

import json
from typing import Optional

from loguru import logger

from src.memory.store import MemoryStore
from src.testing.models import BugReport, TestReport

# AI压缩触发阈值：同URL测试达到此次数后触发
DEFAULT_COMPRESS_THRESHOLD = 3


class MemoryCompressor:
    """记忆压缩器。

    两层策略：
    - 规则提取：每次测试后自动调用，零AI成本
    - AI压缩：累积N次测试后触发，用AI总结跨次经验

    典型使用：
        compressor = MemoryCompressor(memory_store, ai_client)
        compressor.extract_from_report(report)
        compressor.ai_compress_if_needed(url)  # 检查是否需要AI压缩
    """

    def __init__(
        self,
        store: MemoryStore,
        ai_client=None,
        compress_threshold: int = DEFAULT_COMPRESS_THRESHOLD,
    ) -> None:
        self._store = store
        self._ai = ai_client
        self._compress_threshold = compress_threshold

    def extract_from_report(self, report: TestReport) -> dict:
        """从测试报告中提取记忆（规则压缩，零AI成本）。

        提取内容：
        1. 每个Bug → bug_patterns表（字段直接映射）
        2. 测试结果 → test_history表（已有逻辑）
        3. 页面指纹 → page_fingerprints表（已有逻辑）

        Args:
            report: 测试报告

        Returns:
            dict: 提取统计
        """
        url = report.url
        new_patterns = 0
        hit_patterns = 0

        for bug in report.bugs:
            bug_id = self._store.save_bug_pattern(
                url=url,
                severity=bug.severity.value,
                category=bug.category,
                title=bug.title,
                description=bug.description[:200],
                location=bug.location,
            )
            # save_bug_pattern 返回已有记录ID时说明是命中
            existing = self._store.get_bug_patterns(url=url, limit=100)
            for p in existing:
                if p["id"] == bug_id and p["hit_count"] > 1:
                    hit_patterns += 1
                    break
            else:
                new_patterns += 1

        stats = {
            "url": url,
            "bugs_total": len(report.bugs),
            "new_patterns": new_patterns,
            "hit_patterns": hit_patterns,
        }
        logger.info(
            "记忆提取完成 | {} | Bug={}个 | 新模式={}个 | 命中={}个",
            url, len(report.bugs), new_patterns, hit_patterns,
        )
        return stats

    def extract_fix_experience(
        self,
        url: str,
        bug: BugReport,
        fix_analysis: str,
        fix_patches: list[dict],
        fix_confidence: float = 0.0,
        fix_risk_level: str = "medium",
        fix_verified: bool = False,
    ) -> int:
        """从修复结果中提取经验（Bug发现+修复方案的完整记忆）。

        这个方法在RepairLoop修复成功后调用：
        - Bug信息来自BugReport（我们应用发现的）
        - 修复方案来自FixPlan（编程AI生成的）
        - 两者合在一起 = 完整的修复经验

        Args:
            url: 被测应用URL
            bug: Bug报告
            fix_analysis: AI对Bug根因的分析
            fix_patches: 修复补丁列表
            fix_confidence: 修复置信度
            fix_risk_level: 风险等级
            fix_verified: 是否经重测验证

        Returns:
            int: 记录ID
        """
        record_id = self._store.save_fix_experience(
            url=url,
            bug_title=bug.title,
            bug_severity=bug.severity.value,
            bug_category=bug.category,
            bug_description=bug.description[:200],
            fix_analysis=fix_analysis[:200],
            fix_patches_json=json.dumps(fix_patches, ensure_ascii=False)[:500],
            fix_confidence=fix_confidence,
            fix_risk_level=fix_risk_level,
            fix_verified=fix_verified,
        )

        # 如果修复已验证，标记Bug模式为已解决
        if fix_verified:
            self._store.mark_bug_resolved(
                url=url,
                severity=bug.severity.value,
                category=bug.category,
                title=bug.title,
            )
            logger.info("Bug已标记为已修复 | {}", bug.title[:40])

        return record_id

    def get_prompt_context(self, url: str) -> str:
        """获取注入提示词的记忆上下文。

        直接代理MemoryStore.get_context_for_url，
        供BlueprintRunner/Orchestrator调用。
        """
        return self._store.get_context_for_url(url)

    # ── AI 周期压缩（v1.4）──────────────────────────────────────

    def ai_compress_if_needed(self, url: str) -> Optional[str]:
        """检查是否需要AI压缩，如需则执行。

        触发条件：
        1. 同URL测试次数 ≥ compress_threshold
        2. 有未压缩的Bug模式（至少1条）
        3. ai_client 已配置

        压缩过程：
        1. 收集同URL的Bug模式 + 修复经验
        2. 构建压缩提示词
        3. 调用AI生成一句话经验总结
        4. 保存到experiences表（category="ai_summary"）

        Returns:
            str: AI总结文本，无需压缩时返回None
        """
        if not self._ai:
            return None

        # 检查测试次数
        fp = self._store.get_page_fingerprint(url)
        if not fp or fp["test_count"] < self._compress_threshold:
            return None

        # 检查是否有Bug模式
        bugs = self._store.get_bug_patterns(url=url, unresolved_only=False, limit=20)
        if not bugs:
            return None

        # 检查是否已有最近的AI总结（避免重复压缩）
        existing_summaries = self._store.get_experiences(category="ai_summary", limit=10)
        for s in existing_summaries:
            if url in s.get("content", ""):
                # 如果已有总结，检查Bug模式是否有更新
                last_bug_seen = max(b["last_seen_at"] for b in bugs)
                if s["created_at"] >= last_bug_seen:
                    logger.debug("AI总结已是最新，跳过压缩 | {}", url)
                    return None

        # 构建压缩材料
        fixes = self._store.get_fix_experiences(url=url, limit=10)
        prompt = self._build_compress_prompt(url, bugs, fixes, fp)

        # 调用AI压缩
        try:
            summary = self._ai.chat(prompt)
            if not summary or len(summary.strip()) < 5:
                logger.warning("AI压缩返回空结果，跳过 | {}", url)
                return None

            summary = summary.strip()
            # 限制长度
            if len(summary) > 300:
                summary = summary[:297] + "..."

            # 保存到experiences表
            self._store.save_experience(
                category="ai_summary",
                content=f"[{url}] {summary}",
                relevance_score=2.0,  # AI总结权重高于普通经验
            )
            logger.info("AI周期压缩完成 | {} | 总结={}字", url, len(summary))
            return summary

        except Exception as e:
            logger.warning("AI周期压缩失败: {} | {}", url, str(e)[:80])
            return None

    def _build_compress_prompt(
        self,
        url: str,
        bugs: list[dict],
        fixes: list[dict],
        fingerprint: dict,
    ) -> str:
        """构建AI压缩提示词。"""
        lines = [
            f"你是一个测试经验总结专家。请根据以下测试数据，用1-3句话总结这个页面的核心问题和修复经验。",
            f"",
            f"页面: {url}",
            f"测试次数: {fingerprint['test_count']}",
            f"平均通过率: {fingerprint['avg_pass_rate']:.0%}",
            f"",
            f"发现的Bug模式（{len(bugs)}个）:",
        ]

        for b in bugs[:10]:
            resolved = "已修复" if b["is_resolved"] else f"未修复，出现{b['hit_count']}次"
            lines.append(f"  - [{b['severity']}] {b['title']} ({resolved})")

        if fixes:
            lines.append(f"")
            lines.append(f"修复经验（{len(fixes)}条）:")
            for f in fixes[:5]:
                verified = "已验证" if f["fix_verified"] else "未验证"
                lines.append(f"  - {f['bug_title']}: {f['fix_analysis'][:60]} ({verified})")

        lines.extend([
            "",
            "请输出简洁的经验总结（1-3句话），重点说明：",
            "1. 这个页面最常见的问题类型",
            "2. 问题的根本原因（如果能看出规律）",
            "3. 推荐的修复方向",
            "",
            "只输出总结，不要输出其他内容。",
        ])

        return "\n".join(lines)
