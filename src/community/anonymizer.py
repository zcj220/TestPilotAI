"""
经验匿名化模块 (v11.0-B)

将fix_log.json中的修复记录脱敏后转为可上传的经验卡片。
脱敏规则：
  保留：框架名、错误类型、修复策略、平台、API名称
  删除：项目名、文件路径、变量名、业务数据
"""

import re
from typing import Optional


class Anonymizer:
    """修复记录匿名化处理器"""

    _SENSITIVE_PATTERNS = [
        (r"[A-Z]:\\[^\"'\s]+", "<path>"),
        (r"/home/[^/\s]+/[^\"'\s]+", "<path>"),
        (r"/Users/[^/\s]+/[^\"'\s]+", "<path>"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "<email>"),
        (r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "<ip>"),
        (r"[0-9a-f]{32,}", "<token>"),
    ]

    def anonymize_fix(self, fix: dict) -> Optional[dict]:
        """将一条fix_log记录转为匿名经验卡片
        
        Args:
            fix: fix_log.json中的一条修复记录
        
        Returns:
            dict: 匿名化后的经验卡片，如果记录不符合条件返回None
        """
        if fix.get("status") != "resolved":
            return None

        attempts = fix.get("attempts", [])
        if not attempts:
            return None

        last_attempt = attempts[-1]
        failed_attempts = [
            f"尝试{a['attempt_number']}: {self._strip_sensitive(a.get('what_tried',''))} → {self._strip_sensitive(a.get('why_failed',''))}"
            for a in attempts[:-1]
            if a.get("result") in ("failed", "partial") and a.get("why_failed")
        ]

        total_time = sum(a.get("time_spent_minutes", 0) for a in attempts)
        key_apis = self._extract_apis(last_attempt.get("what_tried", ""))
        difficulty = self._calc_difficulty(len(attempts), total_time)

        return {
            "platform": fix.get("platform", ""),
            "framework": fix.get("framework", ""),
            "error_type": self._strip_sensitive(fix.get("error_type", "")),
            "error_message": self._strip_sensitive(fix.get("bug_description", ""))[:200],
            "solution_strategy": self._strip_sensitive(last_attempt.get("what_tried", ""))[:500],
            "root_cause": self._strip_sensitive(fix.get("root_cause", ""))[:500],
            "fix_pattern": self._infer_pattern(last_attempt.get("what_tried", "")),
            "key_apis": key_apis,
            "context_tags": fix.get("context_tags", []),
            "difficulty": difficulty,
            "pass_rate_before": fix.get("pass_rate_before", 0.0),
            "pass_rate_after": fix.get("pass_rate_after", 0.0),
            "time_spent_minutes": total_time,
            "total_attempts": len(attempts),
            "failed_attempts": failed_attempts,
            "verified": True,
        }

    def _strip_sensitive(self, text: str) -> str:
        """替换敏感信息"""
        for pattern, replacement in self._SENSITIVE_PATTERNS:
            text = re.sub(pattern, replacement, text)
        return text

    def _extract_apis(self, text: str) -> list[str]:
        """从描述中提取可能的API名称"""
        api_patterns = [
            r'\b[A-Z][a-zA-Z]+(?:API|Client|Manager|Controller|Handler|Service)\b',
            r'\b(?:get|set|create|delete|update|fetch|post|put)[A-Z][a-zA-Z]+\b',
            r'\b\w+\.\w+\(\)',
        ]
        apis = []
        for pat in api_patterns:
            found = re.findall(pat, text)
            apis.extend(found[:3])
        return list(dict.fromkeys(apis))[:5]

    def _infer_pattern(self, solution: str) -> str:
        """从方案描述中推断修复模式"""
        lower = solution.lower()
        if any(k in lower for k in ["等待", "wait", "sleep", "timeout"]):
            return "add_wait"
        if any(k in lower for k in ["截图", "screenshot", "client", "区域"]):
            return "capture_client_area"
        if any(k in lower for k in ["选择器", "selector", "xpath", "css"]):
            return "fix_selector"
        if any(k in lower for k in ["输入法", "ime", "keyboard", "键盘"]):
            return "input_method"
        if any(k in lower for k in ["坐标", "coordinate", "offset", "偏移"]):
            return "coordinate_fix"
        if any(k in lower for k in ["滚动", "scroll"]):
            return "scroll_to_element"
        if any(k in lower for k in ["重试", "retry", "重新"]):
            return "retry_mechanism"
        return "general_fix"

    @staticmethod
    def _calc_difficulty(attempts: int, time_minutes: int) -> str:
        """根据尝试次数和耗时计算难度"""
        if attempts >= 3 or time_minutes >= 60:
            return "hard"
        if attempts >= 2 or time_minutes >= 20:
            return "medium"
        return "easy"

    # 模型等级分类
    _HIGH_TIER_MODELS = {
        "claude-3-5-sonnet", "claude-3-opus", "claude-opus",
        "gpt-4", "gpt-4o", "gpt-4-turbo", "o1", "o3", "o1-mini",
        "gemini-1.5-pro", "gemini-2.0", "deepseek-r1",
    }
    _LOW_TIER_MODELS = {
        "free", "mini", "nano", "trae", "lite", "turbo-free",
        "qwen-free", "qwen2.5-free", "local", "ollama",
    }

    @classmethod
    def _get_model_tier(cls, model_name: str) -> str:
        """返回 'high' / 'mid' / 'low' 三个等级"""
        if not model_name:
            return "mid"
        m = model_name.lower()
        # 低端特征词（免费/mini/本地）
        if any(k in m for k in cls._LOW_TIER_MODELS):
            return "low"
        # 高端特征词（精确匹配主流高端型号）
        for h in cls._HIGH_TIER_MODELS:
            if h in m:
                return "high"
        return "mid"

    def calc_share_score(self, fix: dict, model_name: str = "") -> int:
        """计算修复步骤的分享价值得分（0-10分）

        评分维度：
          - 耗时（反映问题难度）
          - 尝试次数（需结合模型等级，低端模型多次失败不说明问题难）
          - 通过率提升（修复效果）
          - 高难标签（坐标/截图/输入法等）
          - 模型等级权重：
              high  → 尝试次数满分加成（证明真的难）
              mid   → 正常加成
              low   → 尝试次数加成减半（可能是模型能力限制，非问题本身复杂）
        """
        score = 0
        attempts = fix.get("attempts", [])
        total_time = sum(a.get("time_spent_minutes", 0) for a in attempts)
        tier = self._get_model_tier(model_name or fix.get("ai_model", ""))

        # ── 耗时维度（不受模型影响，时间是客观成本）─────
        if total_time > 60:
            score += 3
        elif total_time > 30:
            score += 2
        elif total_time > 10:
            score += 1

        # ── 尝试次数维度（受模型等级调整）──────────────
        attempt_count = len(attempts)
        if attempt_count > 2:
            if tier == "high":
                score += 3    # 高端模型仍需3+次 = 真的难
            elif tier == "mid":
                score += 2
            else:             # low：次数多可能只是模型能力不足
                score += 1
        elif attempt_count > 1:
            if tier == "low":
                score += 0    # 低端模型2次失败不增加价值评分
            else:
                score += 1

        # ── 通过率提升维度 ───────────────────────────
        improvement = fix.get("pass_rate_after", 0) - fix.get("pass_rate_before", 0)
        if improvement > 0.2:
            score += 2
        elif improvement > 0.1:
            score += 1

        # ── 高难标签维度 ─────────────────────────────
        hard_tags = {"coordinate", "ai_visual", "compatibility", "screenshot",
                     "timeout", "input_method", "ime", "坐标", "截图"}
        tags = set(fix.get("context_tags", []))
        if tags & hard_tags:
            score += 1

        # ── 高端模型额外可信度加成 ───────────────────
        if tier == "high" and attempt_count >= 2:
            score += 1    # 高端模型确认难题，可信度更高

        return min(score, 10)
