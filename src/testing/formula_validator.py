"""
公式验证器（v1.4）

蓝本 assert_text 的 value 字段支持公式验证：
- 普通文本匹配：value="共3项"  →  检查元素文本包含"共3项"
- 精确数值：value="=16.50"  →  提取元素中的数值，验证等于16.50
- 计算表达式：value="=3*5.50" 或 "=3×5.50"  →  计算结果16.5，验证元素数值等于16.5
- 引用其他元素值：value="=#shopPrice * #shopQty"  →  （v2.0，暂不实现）

零AI成本，纯规则计算，100%准确。
"""

import re
from typing import Optional

from loguru import logger


class FormulaResult:
    """公式验证结果。"""

    def __init__(
        self,
        passed: bool,
        expected_value: float,
        actual_value: Optional[float],
        actual_text: str,
        detail: str,
    ):
        self.passed = passed
        self.expected_value = expected_value
        self.actual_value = actual_value
        self.actual_text = actual_text
        self.detail = detail

    def __repr__(self) -> str:
        return f"FormulaResult(passed={self.passed}, expected={self.expected_value}, actual={self.actual_value})"


def is_formula(value: str) -> bool:
    """判断 value 是否为公式（以=开头）。"""
    return value.strip().startswith("=")


def evaluate_formula(formula: str) -> Optional[float]:
    """安全计算公式表达式，返回结果数值。

    支持：
    - 纯数字：=16.50
    - 四则运算：=3*5.50, =3×5.50, =10+20, =100-30, =100/3
    - 混合运算：=3*5.50+2*12.80
    - 括号：=(3+2)*5.50

    不支持（安全考虑）：
    - 变量引用、函数调用、import等

    Returns:
        计算结果，解析失败返回None
    """
    expr = formula.strip().lstrip("=").strip()
    if not expr:
        return None

    # 替换中文运算符
    expr = expr.replace("×", "*").replace("÷", "/").replace("＋", "+").replace("－", "-")

    # 安全检查：只允许数字、运算符、括号、小数点、空格
    if not re.match(r'^[\d\s\.\+\-\*\/\(\)]+$', expr):
        logger.warning("公式包含不安全字符，拒绝计算: {}", expr)
        return None

    try:
        result = eval(expr, {"__builtins__": {}}, {})
        return float(result)
    except Exception as e:
        logger.warning("公式计算失败: {} | {}", expr, e)
        return None


def extract_number(text: str) -> Optional[float]:
    """从文本中提取数值。

    支持格式：
    - "¥16.50" → 16.50
    - "共 3 项" → 3.0
    - "合计：¥42.10" → 42.10
    - "16.50" → 16.50
    - "-5.3" → -5.3
    - "已完成 2" → 2.0

    策略：提取文本中最后一个数值（通常是关键数据）。
    如果文本只有一个数值，则返回该数值。
    """
    # 匹配所有数值（含负数和小数）
    numbers = re.findall(r'-?\d+\.?\d*', text)
    if not numbers:
        return None

    # 如果只有一个数值，直接返回
    if len(numbers) == 1:
        return float(numbers[0])

    # 多个数值时，返回最后一个（通常是金额/结果）
    return float(numbers[-1])


def validate_formula(formula_value: str, actual_text: str, tolerance: float = 0.01) -> FormulaResult:
    """验证元素文本是否满足公式预期。

    Args:
        formula_value: 以=开头的公式，如 "=16.50" 或 "=3*5.50"
        actual_text: 页面元素的实际文本
        tolerance: 浮点数比较容差（默认0.01，即1分钱误差内算通过）

    Returns:
        FormulaResult 验证结果
    """
    expected = evaluate_formula(formula_value)
    if expected is None:
        return FormulaResult(
            passed=False,
            expected_value=0.0,
            actual_value=None,
            actual_text=actual_text,
            detail=f"公式解析失败: {formula_value}",
        )

    actual = extract_number(actual_text)
    if actual is None:
        return FormulaResult(
            passed=False,
            expected_value=expected,
            actual_value=None,
            actual_text=actual_text,
            detail=f"元素文本中未找到数值: '{actual_text}'，预期={expected}",
        )

    passed = abs(actual - expected) <= tolerance

    if passed:
        detail = f"验证通过: 预期={expected}, 实际={actual}"
    else:
        detail = f"数值不匹配: 预期={expected}, 实际={actual}（差值={actual - expected:.4f}）"

    logger.debug("公式验证 | {} | 预期={} | 实际文本='{}' | 提取={} | {}", 
                 formula_value, expected, actual_text[:30], actual, "✓" if passed else "✗")

    return FormulaResult(
        passed=passed,
        expected_value=expected,
        actual_value=actual,
        actual_text=actual_text,
        detail=detail,
    )
