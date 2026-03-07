"""
AI 代码修复引擎

CodeFixer 负责：
1. 对 Bug 进行分类（阻塞性/非阻塞性）
2. 读取项目源码文件，构建上下文
3. 调用 AI 生成修复补丁（FixPlan）
"""

import json
from pathlib import Path
from typing import Optional

from loguru import logger

from src.core.ai_client import AIClient
from src.core.exceptions import RepairAnalysisError
from src.core.prompts import (
    PROMPT_CLASSIFY_BUG,
    PROMPT_FIX_BUG,
    SYSTEM_BUG_CLASSIFIER,
    SYSTEM_CODE_FIXER,
)
from src.repair.models import FixPlan, PatchInfo, RiskLevel
from src.testing.models import BugReport, StepResult
from src.testing.parser import extract_json_from_text


# 读取源码文件时的最大字符数（防止 Token 爆炸）
MAX_FILE_CHARS = 8000
# 扫描项目时包含的文件扩展名
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml",
}
# 排除的目录名
EXCLUDE_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".git",
    "dist", "build", ".next", ".nuxt",
}


class CodeFixer:
    """AI 代码修复引擎。

    典型使用：
        fixer = CodeFixer(ai_client, project_path="/path/to/project")
        plan = fixer.generate_fix(bug_report)
    """

    def __init__(
        self,
        ai_client: AIClient,
        project_path: str,
    ) -> None:
        self._ai = ai_client
        self._project_path = Path(project_path)

    def classify_bug(
        self,
        bug: BugReport,
        step_result: Optional[StepResult] = None,
    ) -> bool:
        """判断 Bug 是否为阻塞性。

        先用规则快速判断，不确定时调用 AI 分类。

        Args:
            bug: Bug 报告
            step_result: 关联的步骤执行结果

        Returns:
            bool: True 表示阻塞性 Bug
        """
        # 规则1：critical 严重度直接判定为阻塞
        if bug.severity.value == "critical":
            logger.debug("Bug '{}' 规则判定为阻塞性（severity=critical）", bug.title)
            return True

        # 规则2：步骤状态为 error（执行异常）判定为阻塞
        if step_result and step_result.status.value == "error":
            logger.debug("Bug '{}' 规则判定为阻塞性（step_status=error）", bug.title)
            return True

        # 规则3：low 严重度直接判定为非阻塞
        if bug.severity.value == "low":
            logger.debug("Bug '{}' 规则判定为非阻塞性（severity=low）", bug.title)
            return False

        # 其余情况调用 AI 分类
        return self._ai_classify_bug(bug, step_result)

    def generate_fix(
        self,
        bug: BugReport,
        reasoning_effort: Optional[str] = None,
    ) -> FixPlan:
        """为 Bug 生成修复方案。

        Args:
            bug: Bug 报告
            reasoning_effort: AI 思考深度

        Returns:
            FixPlan: 修复方案

        Raises:
            RepairAnalysisError: AI 分析失败
        """
        logger.info("生成修复方案 | Bug='{}' | 严重度={}", bug.title, bug.severity.value)

        # 收集相关源码
        source_context = self._collect_source_files()
        if not source_context:
            logger.warning("未找到项目源码文件，无法生成修复方案")
            return FixPlan(
                analysis="未找到项目源码文件",
                can_fix=False,
                explanation="项目路径下未发现可分析的源码文件",
            )

        prompt = PROMPT_FIX_BUG.format(
            bug_title=bug.title,
            bug_severity=bug.severity.value,
            bug_category=bug.category,
            bug_description=bug.description,
            bug_location=bug.location,
            bug_reproduction=bug.reproduction,
            source_files=source_context,
        )

        try:
            resp = self._ai.chat(
                prompt,
                SYSTEM_CODE_FIXER,
                reasoning_effort=reasoning_effort or "high",
            )
            return self._parse_fix_plan(resp)
        except RepairAnalysisError:
            raise
        except Exception as e:
            raise RepairAnalysisError(
                message="AI 修复方案生成失败",
                detail=str(e),
            )

    def _ai_classify_bug(
        self,
        bug: BugReport,
        step_result: Optional[StepResult],
    ) -> bool:
        """调用 AI 判断 Bug 是否阻塞。"""
        prompt = PROMPT_CLASSIFY_BUG.format(
            bug_title=bug.title,
            bug_severity=bug.severity.value,
            bug_description=bug.description,
            error_message=step_result.error_message if step_result else "",
            step_status=step_result.status.value if step_result else "unknown",
        )
        try:
            resp = self._ai.chat(prompt, SYSTEM_BUG_CLASSIFIER, reasoning_effort="low")
            json_str = extract_json_from_text(resp)
            data = json.loads(json_str)
            is_blocking = bool(data.get("is_blocking", False))
            reason = data.get("reason", "")
            logger.info(
                "AI Bug分类 | '{}' | 阻塞={} | 原因: {}",
                bug.title, is_blocking, reason,
            )
            return is_blocking
        except Exception as e:
            # AI 分类失败时，按严重度保守判断
            logger.warning("AI Bug分类失败: {}，回退到规则判断", e)
            return bug.severity.value in ("critical", "high")

    def _collect_source_files(self) -> str:
        """扫描项目目录，收集源码文件内容用于 AI 分析。

        Returns:
            str: 格式化的源码文件内容（带文件路径标注）
        """
        if not self._project_path.exists():
            return ""

        parts: list[str] = []
        total_chars = 0

        for file_path in sorted(self._project_path.rglob("*")):
            if not file_path.is_file():
                continue

            # 跳过排除目录
            if any(d in file_path.parts for d in EXCLUDE_DIRS):
                continue

            # 只包含指定扩展名
            if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            # 截断过长文件
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "\n... (文件截断)"

            rel_path = file_path.relative_to(self._project_path)
            part = f"### {rel_path}\n```\n{content}\n```\n"
            parts.append(part)
            total_chars += len(part)

            # 总上下文不超过 50000 字符（约 12500 token）
            if total_chars > 50000:
                parts.append("... (更多文件省略)")
                break

        return "\n".join(parts)

    def _parse_fix_plan(self, ai_response: str) -> FixPlan:
        """解析 AI 返回的修复方案 JSON。"""
        try:
            json_str = extract_json_from_text(ai_response)
            data = json.loads(json_str)
        except Exception as e:
            raise RepairAnalysisError(
                message="AI 修复方案 JSON 解析失败",
                detail=str(e),
            )

        # 解析补丁列表
        patches: list[PatchInfo] = []
        for p in data.get("patches", []):
            try:
                patches.append(PatchInfo(
                    file_path=p.get("file_path", ""),
                    description=p.get("description", ""),
                    old_code=p.get("old_code", ""),
                    new_code=p.get("new_code", ""),
                ))
            except Exception as e:
                logger.warning("跳过无效补丁: {}", e)

        # 解析风险等级
        risk_str = data.get("risk_level", "medium")
        try:
            risk = RiskLevel(risk_str)
        except ValueError:
            risk = RiskLevel.MEDIUM

        return FixPlan(
            analysis=data.get("analysis", ""),
            can_fix=bool(data.get("can_fix", False)),
            confidence=float(data.get("confidence", 0.0)),
            patches=patches,
            explanation=data.get("explanation", ""),
            risk_level=risk,
        )
