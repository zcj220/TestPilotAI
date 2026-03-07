"""
AI 自动扮演引擎（v9.0 Phase2）

让 AI 分析每个端的截图/页面源码，自动决定下一步操作。
支持：策略配置、1真人+N个AI混合模式、操作历史记录。
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from loguru import logger


class AIStrategy(str, Enum):
    """AI 玩家策略。"""
    RANDOM = "random"          # 随机点击可交互元素
    NORMAL = "normal"          # 模拟正常用户行为
    BOUNDARY = "boundary"      # 故意触发边界条件
    EXPLORER = "explorer"      # 探索型：尝试点击所有未访问的元素


@dataclass
class AIAction:
    """AI 决策的一次操作。"""
    action: str               # tap / input / navigate / screenshot / wait
    params: dict = field(default_factory=dict)
    reason: str = ""          # AI 为什么做这个决策
    confidence: float = 0.0   # 置信度 0-1
    timestamp: float = 0.0


@dataclass
class AIPlayerConfig:
    """AI 玩家配置。"""
    strategy: AIStrategy = AIStrategy.NORMAL
    max_actions: int = 50          # 最大操作次数
    action_delay: float = 1.0      # 每次操作间隔（秒）
    screenshot_interval: int = 5   # 每N次操作截图一次
    analyze_before_action: bool = True  # 操作前是否分析截图


class AIPlayerEngine:
    """AI 自动扮演引擎。

    为指定玩家生成操作决策，驱动控制器执行。
    """

    def __init__(self, config: AIPlayerConfig = None) -> None:
        self.config = config or AIPlayerConfig()
        self.action_history: list[AIAction] = []
        self._running = False
        self._action_count = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def action_count(self) -> int:
        return self._action_count

    async def analyze_screen(self, page_source: str, strategy: AIStrategy = None) -> AIAction:
        """分析页面源码，决定下一步操作。

        根据策略生成操作决策。实际 AI 分析可接入 LLM。
        """
        strategy = strategy or self.config.strategy
        elements = self._extract_interactive_elements(page_source)

        if not elements:
            return AIAction(
                action="wait", params={"duration": 1},
                reason="未找到可交互元素", confidence=0.3,
                timestamp=time.time(),
            )

        if strategy == AIStrategy.RANDOM:
            return self._strategy_random(elements)
        elif strategy == AIStrategy.BOUNDARY:
            return self._strategy_boundary(elements)
        elif strategy == AIStrategy.EXPLORER:
            return self._strategy_explorer(elements)
        else:
            return self._strategy_normal(elements)

    def _extract_interactive_elements(self, source: str) -> list[dict]:
        """从页面源码提取可交互元素。"""
        elements = []
        import re

        button_patterns = [
            (r'<button[^>]*class="([^"]*)"', "button"),
            (r'<input[^>]*class="([^"]*)"', "input"),
            (r'<a[^>]*href="([^"]*)"', "link"),
            (r'<view[^>]*bindtap="([^"]*)"', "view_tap"),
            (r'class="([^"]*btn[^"]*)"', "btn_class"),
            (r'data-testid="([^"]*)"', "testid"),
        ]

        for pattern, elem_type in button_patterns:
            for match in re.finditer(pattern, source):
                elements.append({
                    "type": elem_type,
                    "selector": f".{match.group(1).split()[0]}" if elem_type != "link" else match.group(1),
                    "raw": match.group(0),
                })

        return elements

    def _strategy_random(self, elements: list[dict]) -> AIAction:
        """随机选择一个元素操作。"""
        import random
        elem = random.choice(elements)
        action = "input" if elem["type"] == "input" else "tap"
        params = {"selector": elem["selector"]}
        if action == "input":
            params["text"] = f"AI随机输入_{int(time.time()) % 1000}"
        return AIAction(
            action=action, params=params,
            reason=f"随机选择: {elem['type']} {elem['selector']}",
            confidence=0.5, timestamp=time.time(),
        )

    def _strategy_normal(self, elements: list[dict]) -> AIAction:
        """模拟正常用户行为：优先按钮 > 输入框 > 链接。"""
        priority = {"button": 1, "btn_class": 1, "view_tap": 2, "input": 3, "link": 4, "testid": 2}
        elements.sort(key=lambda e: priority.get(e["type"], 5))
        elem = elements[0]

        visited = {a.params.get("selector") for a in self.action_history}
        for e in elements:
            if e["selector"] not in visited:
                elem = e
                break

        action = "input" if elem["type"] == "input" else "tap"
        params = {"selector": elem["selector"]}
        if action == "input":
            params["text"] = "测试数据"
        return AIAction(
            action=action, params=params,
            reason=f"正常操作: {elem['type']} {elem['selector']}",
            confidence=0.7, timestamp=time.time(),
        )

    def _strategy_boundary(self, elements: list[dict]) -> AIAction:
        """边界条件策略：输入极端值、连续点击等。"""
        boundary_inputs = [
            "", " ", "a" * 1000, "0", "-1", "99999999",
            "<script>alert(1)</script>", "' OR 1=1 --",
            "🎮🎯🎲", "\n\n\n", "null", "undefined",
        ]
        import random

        input_elems = [e for e in elements if e["type"] == "input"]
        if input_elems:
            elem = random.choice(input_elems)
            text = random.choice(boundary_inputs)
            return AIAction(
                action="input", params={"selector": elem["selector"], "text": text},
                reason=f"边界测试: 输入 '{text[:20]}...'",
                confidence=0.8, timestamp=time.time(),
            )

        elem = random.choice(elements)
        return AIAction(
            action="tap", params={"selector": elem["selector"]},
            reason=f"边界测试: 连续点击 {elem['selector']}",
            confidence=0.6, timestamp=time.time(),
        )

    def _strategy_explorer(self, elements: list[dict]) -> AIAction:
        """探索策略：优先点击未访问的元素。"""
        visited = {a.params.get("selector") for a in self.action_history}
        unvisited = [e for e in elements if e["selector"] not in visited]

        if unvisited:
            elem = unvisited[0]
            return AIAction(
                action="tap", params={"selector": elem["selector"]},
                reason=f"探索未访问: {elem['selector']} (剩余{len(unvisited)-1})",
                confidence=0.8, timestamp=time.time(),
            )

        import random
        elem = random.choice(elements)
        return AIAction(
            action="tap", params={"selector": elem["selector"]},
            reason="全部已访问，随机选择",
            confidence=0.4, timestamp=time.time(),
        )

    async def run_player(self, orchestrator: Any, player_id: str) -> list[AIAction]:
        """自动驱动指定玩家执行操作。"""
        self._running = True
        self._action_count = 0
        self.action_history.clear()

        logger.info("AI玩家启动 | {} | 策略: {} | 最大操作: {}",
                     player_id, self.config.strategy.value, self.config.max_actions)

        while self._running and self._action_count < self.config.max_actions:
            try:
                source = ""
                if self.config.analyze_before_action:
                    source = await orchestrator.execute_action(player_id, "get_source")

                ai_action = await self.analyze_screen(source or "", self.config.strategy)
                self.action_history.append(ai_action)

                if ai_action.action == "wait":
                    await asyncio.sleep(ai_action.params.get("duration", 1))
                else:
                    await orchestrator.execute_action(
                        player_id, ai_action.action, **ai_action.params
                    )

                self._action_count += 1

                if self._action_count % self.config.screenshot_interval == 0:
                    await orchestrator.execute_action(
                        player_id, "screenshot",
                        name=f"ai_{player_id}_{self._action_count}",
                    )

                await asyncio.sleep(self.config.action_delay)

            except Exception as e:
                logger.warning("AI玩家操作异常 | {} | {}", player_id, e)
                self.action_history.append(AIAction(
                    action="error", params={"error": str(e)},
                    reason="操作异常", confidence=0, timestamp=time.time(),
                ))
                self._action_count += 1
                await asyncio.sleep(self.config.action_delay)

        self._running = False
        logger.info("AI玩家结束 | {} | 执行: {}次", player_id, self._action_count)
        return self.action_history

    def stop(self) -> None:
        self._running = False

    def get_report(self) -> dict:
        """生成 AI 玩家操作报告。"""
        actions_by_type = {}
        for a in self.action_history:
            actions_by_type[a.action] = actions_by_type.get(a.action, 0) + 1
        return {
            "strategy": self.config.strategy.value,
            "total_actions": self._action_count,
            "action_breakdown": actions_by_type,
            "avg_confidence": round(
                sum(a.confidence for a in self.action_history) / max(len(self.action_history), 1), 2
            ),
            "history": [
                {"action": a.action, "params": a.params, "reason": a.reason,
                 "confidence": a.confidence}
                for a in self.action_history[-20:]
            ],
        }
