"""
三AI交叉验证引擎（v3.0）

通过多角色、多轮分析提升测试结果的可信度：
1. AI-A（测试AI）— 执行测试步骤并分析截图
2. AI-B（数据AI）— 独立生成测试数据，避免自我一致性偏差
3. AI-C（审查AI）— 最终仲裁，聚合多次分析结果

核心策略：
- 重复验证：对同一页面多次截图分析，过滤AI随机误判
- 置信度聚合：综合多次分析结果计算最终置信度
- 独立数据生成：AI-B用不同prompt生成测试输入数据
- 深度分析降级：置信度低于阈值时自动触发高思考深度
"""

import json
from typing import Optional

from loguru import logger

from src.core.ai_client import AIClient
from src.core.prompts import PROMPT_ANALYZE_SCREENSHOT, SYSTEM_SCREENSHOT_ANALYZER
from src.testing.models import ScreenshotAnalysis, StepResult, StepStatus
from src.testing.parser import parse_screenshot_analysis


# ── AI-B 数据生成提示词 ──────────────────────────────

SYSTEM_DATA_GENERATOR = """你是 TestPilot AI 的独立测试数据生成引擎（AI-B角色）。
你的任务是为给定的测试场景生成真实、多样化的测试输入数据。

你必须独立思考，不要受测试步骤描述的暗示，要生成：
1. 正常数据 — 合理的正确输入
2. 边界数据 — 空值、超长字符串、特殊字符
3. 异常数据 — SQL注入、XSS、非法格式

严格按JSON格式返回：
```json
{
  "test_inputs": [
    {
      "field": "字段名",
      "normal": "正常值",
      "boundary": "边界值",
      "abnormal": "异常值",
      "description": "为什么选这些值"
    }
  ],
  "scenarios": [
    {
      "name": "场景名",
      "inputs": {"字段名": "值"},
      "expected": "预期结果"
    }
  ]
}
```"""

PROMPT_GENERATE_TEST_DATA = """请为以下测试场景生成独立的测试数据：

应用描述：{app_description}
页面URL：{page_url}
测试重点：{test_focus}
页面包含的输入字段：{input_fields}

请生成全面、多样的测试输入数据和测试场景。"""

# ── AI-C 审查提示词 ──────────────────────────────────

SYSTEM_REVIEWER = """你是 TestPilot AI 的最终审查引擎（AI-C角色）。
你的任务是审查多次AI分析的结果，做出最终裁决。

你会收到同一个页面的多次分析结果，需要：
1. 判断哪些发现是真正的Bug，哪些是误报
2. 综合多次分析给出最终置信度
3. 对有分歧的结果做出仲裁

严格按JSON格式返回：
```json
{
  "final_verdict": "pass" | "fail",
  "confidence": 0.0-1.0,
  "confirmed_issues": ["确认的问题"],
  "dismissed_issues": ["排除的误报"],
  "reasoning": "仲裁理由"
}
```"""


class CrossValidator:
    """交叉验证引擎。

    典型使用：
        validator = CrossValidator(ai_client)
        final = validator.validate_step(step_result, expected="页面显示登录表单")
    """

    # 置信度低于此阈值时触发深度分析
    CONFIDENCE_THRESHOLD = 0.7
    # 默认验证轮次
    DEFAULT_ROUNDS = 2

    def __init__(self, ai_client: AIClient) -> None:
        self._ai = ai_client

    def validate_step(
        self,
        result: StepResult,
        expected: str,
        rounds: int = DEFAULT_ROUNDS,
    ) -> StepResult:
        """对单个步骤结果进行交叉验证。

        Args:
            result: 原始步骤执行结果（含截图路径）
            expected: 预期结果描述
            rounds: 验证轮次（默认2轮，加上原始分析共3次）

        Returns:
            StepResult: 更新后的步骤结果（置信度更可靠）
        """
        if not result.screenshot_path:
            return result

        # 收集所有分析结果（包括原始的）
        analyses: list[ScreenshotAnalysis] = []
        if result.analysis:
            analyses.append(result.analysis)

        # 额外轮次的验证
        for i in range(rounds):
            logger.debug("交叉验证轮次 {}/{} | 步骤{}", i + 1, rounds, result.step)
            analysis = self._analyze_once(
                result.screenshot_path,
                result.description,
                expected,
                reasoning_effort="low",
            )
            if analysis:
                analyses.append(analysis)

        if not analyses:
            return result

        # 聚合结果
        aggregated = self._aggregate_analyses(analyses)

        # 如果置信度低，用高思考深度再分析一次
        if aggregated.confidence < self.CONFIDENCE_THRESHOLD:
            logger.info(
                "置信度较低({:.2f})，触发深度分析 | 步骤{}",
                aggregated.confidence, result.step,
            )
            deep = self._analyze_once(
                result.screenshot_path,
                result.description,
                expected,
                reasoning_effort="high",
            )
            if deep:
                # 深度分析权重更高，重新聚合
                analyses.append(deep)
                analyses.append(deep)  # 双倍权重
                aggregated = self._aggregate_analyses(analyses)

        # 更新结果
        result.analysis = aggregated
        if aggregated.matches_expected:
            result.status = StepStatus.PASSED
            result.error_message = ""
        else:
            result.status = StepStatus.FAILED
            result.error_message = "; ".join(aggregated.issues) if aggregated.issues else "页面不符合预期"

        logger.info(
            "交叉验证完成 | 步骤{} | 最终={} | 置信度={:.2f} | 分析次数={}",
            result.step, result.status.value, aggregated.confidence, len(analyses),
        )
        return result

    def _analyze_once(
        self,
        screenshot_path: str,
        step_desc: str,
        expected: str,
        reasoning_effort: str,
    ) -> Optional[ScreenshotAnalysis]:
        """执行一次截图分析。"""
        prompt = PROMPT_ANALYZE_SCREENSHOT.format(
            step_description=step_desc,
            expected=expected,
        )
        try:
            resp = self._ai.analyze_screenshot(
                image_path=screenshot_path,
                prompt=prompt,
                system_prompt=SYSTEM_SCREENSHOT_ANALYZER,
                reasoning_effort=reasoning_effort,
            )
            data = parse_screenshot_analysis(resp)
            return ScreenshotAnalysis(**data)
        except Exception as e:
            logger.warning("交叉验证分析失败: {}", e)
            return None

    @staticmethod
    def _aggregate_analyses(analyses: list[ScreenshotAnalysis]) -> ScreenshotAnalysis:
        """聚合多次分析结果。

        规则：
        - matches_expected: 多数投票（超过半数认为匹配才算匹配）
        - confidence: 加权平均
        - issues: 合并去重（出现2次以上的问题更可信）
        - page_description: 取置信度最高的那次
        """
        if len(analyses) == 1:
            return analyses[0]

        # 投票
        match_votes = sum(1 for a in analyses if a.matches_expected)
        total = len(analyses)
        matches = match_votes > total / 2

        # 平均置信度
        avg_confidence = sum(a.confidence for a in analyses) / total

        # 合并issues（统计频次，出现多次的更可信）
        issue_count: dict[str, int] = {}
        for a in analyses:
            for issue in a.issues:
                issue_count[issue] = issue_count.get(issue, 0) + 1
        # 只保留出现超过1次的issue，或者如果总分析次数<=2则全部保留
        if total <= 2:
            confirmed_issues = list(issue_count.keys())
        else:
            confirmed_issues = [i for i, c in issue_count.items() if c > 1]

        # 合并suggestions
        all_suggestions: list[str] = []
        seen: set[str] = set()
        for a in analyses:
            for s in a.suggestions:
                if s not in seen:
                    all_suggestions.append(s)
                    seen.add(s)

        # 取置信度最高的描述
        best = max(analyses, key=lambda a: a.confidence)

        return ScreenshotAnalysis(
            matches_expected=matches,
            confidence=avg_confidence,
            page_description=best.page_description,
            issues=confirmed_issues,
            suggestions=all_suggestions,
        )

    # ── AI-B: 独立测试数据生成（v3.0）────────────────

    def generate_test_data(
        self,
        app_description: str,
        page_url: str,
        test_focus: str = "核心功能",
        input_fields: str = "",
    ) -> dict:
        """AI-B角色：独立生成测试数据。

        与AI-A（编程AI）完全独立，使用不同的系统提示词，
        避免自我一致性偏差（同一个AI既写代码又写测试数据）。

        Args:
            app_description: 应用描述
            page_url: 页面URL
            test_focus: 测试重点
            input_fields: 页面包含的输入字段描述

        Returns:
            dict: 包含 test_inputs 和 scenarios 的测试数据
        """
        prompt = PROMPT_GENERATE_TEST_DATA.format(
            app_description=app_description,
            page_url=page_url,
            test_focus=test_focus,
            input_fields=input_fields or "自动检测",
        )

        try:
            resp = self._ai.chat(
                prompt,
                system_prompt=SYSTEM_DATA_GENERATOR,
                reasoning_effort="medium",
            )
            # 解析JSON响应
            data = self._parse_json_response(resp)
            logger.info(
                "AI-B数据生成完成 | 字段数={} | 场景数={}",
                len(data.get("test_inputs", [])),
                len(data.get("scenarios", [])),
            )
            return data
        except Exception as e:
            logger.warning("AI-B数据生成失败: {}", e)
            return {"test_inputs": [], "scenarios": []}

    # ── AI-C: 最终审查仲裁（v3.0）────────────────────

    def review_analyses(
        self,
        analyses_summary: list[dict],
        step_description: str,
    ) -> dict:
        """AI-C角色：审查多次分析结果，做出最终仲裁。

        当多次分析结果有分歧时，使用独立的审查角色
        综合判断哪些是真Bug、哪些是误报。

        Args:
            analyses_summary: 多次分析结果的摘要列表
            step_description: 测试步骤描述

        Returns:
            dict: 包含 final_verdict, confidence, confirmed_issues 等
        """
        review_prompt = f"""请审查以下测试步骤的多次分析结果：

测试步骤：{step_description}

各次分析结果：
{json.dumps(analyses_summary, ensure_ascii=False, indent=2)}

请综合判断，给出最终裁决。"""

        try:
            resp = self._ai.chat(
                review_prompt,
                system_prompt=SYSTEM_REVIEWER,
                reasoning_effort="high",
            )
            data = self._parse_json_response(resp)
            logger.info(
                "AI-C审查完成 | 裁决={} | 置信度={:.2f} | 确认问题={}",
                data.get("final_verdict", "unknown"),
                data.get("confidence", 0),
                len(data.get("confirmed_issues", [])),
            )
            return data
        except Exception as e:
            logger.warning("AI-C审查失败: {}", e)
            return {
                "final_verdict": "unknown",
                "confidence": 0.5,
                "confirmed_issues": [],
                "dismissed_issues": [],
                "reasoning": f"审查失败: {e}",
            }

    @staticmethod
    def _parse_json_response(text: str) -> dict:
        """从AI响应中解析JSON。"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 尝试从markdown代码块中提取
        if "```json" in text:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        if "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        # 尝试找到第一个 { 和最后一个 }
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1:
            return json.loads(text[first:last + 1])
        raise ValueError(f"无法从AI响应中解析JSON: {text[:200]}")
