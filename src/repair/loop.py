"""
修复闭环编排器

RepairLoop 是 v0.4 的核心大脑，串联完整的修复流程：
1. 对 Bug 列表进行分类（阻塞/非阻塞）
2. 按优先级排序（阻塞性优先，严重度高优先）
3. 逐个 Bug：AI 生成修复方案 → 应用补丁 → 重测失败步骤 → 验证
4. 修复失败自动回滚，超过重试次数标记为需人工介入
5. 生成修复报告
"""

import time
from datetime import datetime, timezone
from typing import Callable, Optional

from loguru import logger

from src.core.ai_client import AIClient
from src.core.exceptions import PatchApplyError, RepairAnalysisError
from src.repair.fixer import CodeFixer
from src.repair.models import (
    AttemptStatus,
    FixAttempt,
    RepairReport,
)
from src.repair.patcher import PatchApplier
from src.testing.models import (
    BugReport,
    BugSeverity,
    FixStatus,
    StepResult,
    TestReport,
)

# 每个 Bug 最多修复尝试次数
MAX_FIX_ATTEMPTS = 2

# Bug 严重度排序权重（越大越优先修复）
SEVERITY_ORDER = {
    BugSeverity.CRITICAL: 4,
    BugSeverity.HIGH: 3,
    BugSeverity.MEDIUM: 2,
    BugSeverity.LOW: 1,
}


class RepairLoop:
    """修复闭环编排器。

    典型使用：
        loop = RepairLoop(ai_client, project_path, retest_fn)
        repair_report = await loop.run(test_report)
    """

    def __init__(
        self,
        ai_client: AIClient,
        project_path: str,
        retest_func: Optional[Callable] = None,
    ) -> None:
        """初始化修复闭环。

        Args:
            ai_client: AI 客户端
            project_path: 被测项目的根路径
            retest_func: 重测回调函数，签名为 async (list[int]) -> list[StepResult]
                         参数为需要重测的步骤编号列表，返回重测结果
        """
        self._ai = ai_client
        self._project_path = project_path
        self._fixer = CodeFixer(ai_client, project_path)
        self._patcher = PatchApplier(project_path)
        self._retest_func = retest_func

    async def run(
        self,
        test_report: TestReport,
        reasoning_effort: Optional[str] = None,
    ) -> RepairReport:
        """执行完整的修复闭环。

        Args:
            test_report: 测试报告（含 Bug 列表和步骤结果）
            reasoning_effort: AI 思考深度

        Returns:
            RepairReport: 修复报告
        """
        report = RepairReport(project_path=self._project_path)
        bugs = test_report.bugs

        if not bugs:
            logger.info("没有 Bug 需要修复")
            report.end_time = datetime.now(timezone.utc)
            report.summary = "没有 Bug 需要修复"
            return report

        logger.info("═" * 60)
        logger.info("开始修复闭环 | Bug 数量={}", len(bugs))

        # 阶段1：Bug 分类
        logger.info("【阶段1/3】Bug 分类...")
        step_results_map = {r.step: r for r in test_report.step_results}
        for bug in bugs:
            step_result = step_results_map.get(bug.step_number) if bug.step_number else None
            bug.is_blocking = self._fixer.classify_bug(bug, step_result)
            logger.info(
                "  {} | {} | 阻塞={}",
                bug.severity.value, bug.title, bug.is_blocking,
            )

        # 阶段2：排序（阻塞性优先，然后按严重度）
        sorted_bugs = sorted(
            bugs,
            key=lambda b: (b.is_blocking, SEVERITY_ORDER.get(b.severity, 0)),
            reverse=True,
        )

        report.total_bugs = len(sorted_bugs)
        report.blocking_bugs = sum(1 for b in sorted_bugs if b.is_blocking)

        # 阶段3：逐个修复
        logger.info(
            "【阶段2/3】逐个修复 | 阻塞性={} | 非阻塞性={}",
            report.blocking_bugs, report.total_bugs - report.blocking_bugs,
        )

        for i, bug in enumerate(sorted_bugs):
            logger.info(
                "── 修复 Bug {}/{}: {} ──",
                i + 1, len(sorted_bugs), bug.title,
            )
            attempt = await self._fix_single_bug(
                bug, step_results_map, reasoning_effort,
            )
            report.attempts.append(attempt)

            # 更新统计
            if attempt.status == AttemptStatus.RETEST_PASSED:
                report.fixed_bugs += 1
                bug.fix_status = FixStatus.VERIFIED
            elif attempt.status in (AttemptStatus.PATCHED,):
                # 补丁已应用但无法重测（没有 retest_func）
                report.fixed_bugs += 1
                bug.fix_status = FixStatus.FIXED
            elif attempt.status in (
                AttemptStatus.PATCH_FAILED,
                AttemptStatus.RETEST_FAILED,
                AttemptStatus.ROLLED_BACK,
            ):
                report.failed_bugs += 1
                bug.fix_status = FixStatus.FIX_FAILED
            else:
                report.needs_human_bugs += 1
                bug.fix_status = FixStatus.NEEDS_HUMAN

        # 阶段4：生成总结
        logger.info("【阶段3/3】生成修复报告...")
        report.end_time = datetime.now(timezone.utc)
        report.summary = self._generate_summary(report)

        logger.info(
            "修复闭环完成 | 修复={}/{} | 失败={} | 需人工={} | 耗时={:.1f}秒",
            report.fixed_bugs, report.total_bugs,
            report.failed_bugs, report.needs_human_bugs,
            report.duration_seconds,
        )
        return report

    async def _fix_single_bug(
        self,
        bug: BugReport,
        step_results_map: dict[int, StepResult],
        reasoning_effort: Optional[str],
    ) -> FixAttempt:
        """对单个 Bug 执行修复尝试（含重试）。"""
        for attempt_num in range(1, MAX_FIX_ATTEMPTS + 1):
            attempt = FixAttempt(
                attempt_number=attempt_num,
                bug_title=bug.title,
            )
            t0 = time.time()

            try:
                # 步骤1：AI 生成修复方案
                bug.fix_status = FixStatus.FIXING
                plan = self._fixer.generate_fix(bug, reasoning_effort)
                attempt.fix_plan = plan

                if not plan.can_fix:
                    logger.warning(
                        "AI 判断无法修复 | Bug='{}' | 原因: {}",
                        bug.title, plan.analysis,
                    )
                    attempt.status = AttemptStatus.PATCH_FAILED
                    attempt.error_message = f"AI 无法修复: {plan.analysis}"
                    attempt.duration_seconds = time.time() - t0
                    return attempt

                if not plan.patches:
                    logger.warning("AI 返回空补丁列表 | Bug='{}'", bug.title)
                    attempt.status = AttemptStatus.PATCH_FAILED
                    attempt.error_message = "AI 返回空补丁列表"
                    attempt.duration_seconds = time.time() - t0
                    return attempt

                # 步骤2：应用补丁
                logger.info(
                    "应用补丁 | 第{}次尝试 | 补丁数={}",
                    attempt_num, len(plan.patches),
                )
                backups = self._patcher.apply(plan)
                attempt.backups = backups
                attempt.status = AttemptStatus.PATCHED

                # 步骤3：重测（如果有重测函数）
                if self._retest_func and bug.step_number:
                    logger.info("重测步骤 {}...", bug.step_number)
                    retest_results = await self._retest_func([bug.step_number])

                    # 检查重测是否通过
                    passed = all(
                        r.status.value == "passed" for r in retest_results
                    )

                    if passed:
                        logger.info("✓ 重测通过 | Bug='{}'", bug.title)
                        attempt.status = AttemptStatus.RETEST_PASSED
                        attempt.duration_seconds = time.time() - t0
                        return attempt
                    else:
                        logger.warning(
                            "✗ 重测未通过 | Bug='{}' | 第{}次尝试",
                            bug.title, attempt_num,
                        )
                        # 回滚并重试
                        self._patcher.rollback(backups)
                        attempt.status = AttemptStatus.RETEST_FAILED
                        attempt.error_message = "重测未通过"

                        if attempt_num < MAX_FIX_ATTEMPTS:
                            logger.info("准备第{}次修复尝试...", attempt_num + 1)
                            continue
                        else:
                            attempt.status = AttemptStatus.ROLLED_BACK
                            attempt.error_message = (
                                f"超过最大尝试次数({MAX_FIX_ATTEMPTS})，已回滚"
                            )
                else:
                    # 没有重测函数，补丁应用即视为成功
                    logger.info("补丁已应用（无重测函数） | Bug='{}'", bug.title)
                    attempt.duration_seconds = time.time() - t0
                    return attempt

            except RepairAnalysisError as e:
                logger.error("修复分析失败 | Bug='{}': {}", bug.title, e)
                attempt.status = AttemptStatus.PATCH_FAILED
                attempt.error_message = str(e)
            except PatchApplyError as e:
                logger.error("补丁应用失败 | Bug='{}': {}", bug.title, e)
                attempt.status = AttemptStatus.PATCH_FAILED
                attempt.error_message = str(e)
            except Exception as e:
                logger.error("修复过程意外错误 | Bug='{}': {}", bug.title, e)
                attempt.status = AttemptStatus.PATCH_FAILED
                attempt.error_message = f"意外错误: {e}"

            attempt.duration_seconds = time.time() - t0

        return attempt

    @staticmethod
    def _generate_summary(report: RepairReport) -> str:
        """生成修复报告摘要。"""
        lines = [
            f"# 自动修复报告",
            f"",
            f"- **总 Bug 数**: {report.total_bugs}",
            f"- **阻塞性 Bug**: {report.blocking_bugs}",
            f"- **成功修复**: {report.fixed_bugs}",
            f"- **修复失败**: {report.failed_bugs}",
            f"- **需人工介入**: {report.needs_human_bugs}",
            f"- **修复率**: {report.fix_rate:.0%}",
            f"- **耗时**: {report.duration_seconds:.1f}秒",
        ]

        if report.attempts:
            lines.append("")
            lines.append("## 修复详情")
            lines.append("")
            for a in report.attempts:
                icon = {
                    "retest_passed": "✅",
                    "patched": "✅",
                    "patch_failed": "❌",
                    "retest_failed": "❌",
                    "rolled_back": "↩️",
                }.get(a.status.value, "❓")
                lines.append(f"- {icon} **{a.bug_title}** [{a.status.value}]")
                if a.error_message:
                    lines.append(f"  - {a.error_message}")
                if a.fix_plan and a.fix_plan.analysis:
                    lines.append(f"  - 分析: {a.fix_plan.analysis}")

        return "\n".join(lines)
