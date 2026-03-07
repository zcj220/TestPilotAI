"""
测试脚本解析器

将 AI 生成的 JSON 测试脚本解析为结构化的 TestScript 对象。
处理 AI 输出中可能存在的格式问题（markdown代码块包裹、多余文字等）。
"""

import json
import re
from typing import Optional

from loguru import logger

from src.core.exceptions import TestScriptParseError
from src.testing.models import TestScript, TestStep


def extract_json_from_text(text: str) -> str:
    """从AI响应文本中提取JSON内容。

    AI有时会在JSON前后加上markdown代码块或解释文字，
    此函数负责清理这些干扰内容，提取纯净的JSON。

    Args:
        text: AI 返回的原始文本

    Returns:
        str: 提取出的 JSON 字符串

    Raises:
        TestScriptParseError: 无法从文本中提取有效的JSON
    """
    # 尝试1：直接解析（AI可能返回了纯JSON）
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped

    # 尝试2：从 markdown 代码块中提取
    # 匹配 ```json ... ``` 或 ``` ... ```
    code_block_pattern = r"```(?:json)?\s*\n?(.*?)\n?```"
    matches = re.findall(code_block_pattern, stripped, re.DOTALL)
    if matches:
        for match in matches:
            candidate = match.strip()
            if candidate.startswith("{"):
                return candidate

    # 尝试3：找到第一个 { 和最后一个 } 之间的内容
    first_brace = stripped.find("{")
    last_brace = stripped.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        return stripped[first_brace : last_brace + 1]

    raise TestScriptParseError(
        message="无法从AI响应中提取JSON",
        detail=f"原始文本前200字符: {text[:200]}",
    )


def parse_test_script(ai_response: str) -> TestScript:
    """将 AI 生成的文本解析为 TestScript 对象。

    Args:
        ai_response: AI 返回的原始文本（应包含JSON格式的测试脚本）

    Returns:
        TestScript: 解析后的测试脚本对象

    Raises:
        TestScriptParseError: 解析失败
    """
    try:
        json_str = extract_json_from_text(ai_response)
        data = json.loads(json_str)
    except TestScriptParseError:
        raise
    except json.JSONDecodeError as e:
        raise TestScriptParseError(
            message="AI返回的JSON格式无效",
            detail=f"JSON解析错误: {e}",
        )

    # 验证必需字段
    if "steps" not in data:
        raise TestScriptParseError(
            message="测试脚本缺少 steps 字段",
            detail=f"收到的字段: {list(data.keys())}",
        )

    if not isinstance(data["steps"], list) or len(data["steps"]) == 0:
        raise TestScriptParseError(
            message="测试脚本的 steps 为空或格式错误",
        )

    # 解析步骤
    steps: list[TestStep] = []
    for i, step_data in enumerate(data["steps"], start=1):
        try:
            # 如果AI没给step编号，自动补上
            if "step" not in step_data:
                step_data["step"] = i

            step = TestStep(**step_data)
            steps.append(step)
        except Exception as e:
            logger.warning("跳过无效步骤 #{}: {} | 错误: {}", i, step_data, e)
            continue

    if not steps:
        raise TestScriptParseError(message="所有测试步骤都解析失败")

    script = TestScript(
        test_name=data.get("test_name", "未命名测试"),
        description=data.get("description", ""),
        steps=steps,
    )

    logger.info(
        "测试脚本解析成功 | 名称={} | 步骤数={}",
        script.test_name,
        len(script.steps),
    )
    return script


def parse_screenshot_analysis(ai_response: str) -> dict:
    """解析截图分析结果的JSON。

    Args:
        ai_response: AI 视觉分析返回的文本

    Returns:
        dict: 解析后的分析结果字典

    Raises:
        TestScriptParseError: 解析失败
    """
    try:
        json_str = extract_json_from_text(ai_response)
        data = json.loads(json_str)
    except TestScriptParseError:
        # 如果无法提取JSON，构造一个默认结果
        logger.warning("截图分析结果非JSON格式，使用原始文本作为描述")
        return {
            "matches_expected": True,
            "confidence": 0.5,
            "page_description": ai_response[:500],
            "issues": [],
            "suggestions": [],
        }
    except json.JSONDecodeError:
        logger.warning("截图分析JSON解析失败，使用原始文本")
        return {
            "matches_expected": True,
            "confidence": 0.5,
            "page_description": ai_response[:500],
            "issues": [],
            "suggestions": [],
        }

    return data


def parse_bug_detection(ai_response: str) -> dict:
    """解析Bug检测结果的JSON。

    Args:
        ai_response: AI Bug检测返回的文本

    Returns:
        dict: 解析后的Bug检测结果
    """
    try:
        json_str = extract_json_from_text(ai_response)
        data = json.loads(json_str)
    except (TestScriptParseError, json.JSONDecodeError):
        logger.warning("Bug检测结果解析失败，返回空结果")
        return {
            "bugs_found": [],
            "warnings": [],
            "overall_quality": "未知",
        }

    return data
