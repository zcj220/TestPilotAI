"""
公式验证器测试（v1.4）
"""

import pytest

from src.testing.formula_validator import (
    FormulaResult,
    evaluate_formula,
    extract_number,
    is_formula,
    validate_formula,
)


class TestIsFormula:
    """测试公式判断。"""

    def test_formula_starts_with_equals(self):
        assert is_formula("=16.50") is True

    def test_formula_with_expression(self):
        assert is_formula("=3*5.50") is True

    def test_formula_with_spaces(self):
        assert is_formula("  =16.50") is True

    def test_not_formula_plain_text(self):
        assert is_formula("共3项") is False

    def test_not_formula_empty(self):
        assert is_formula("") is False

    def test_not_formula_number(self):
        assert is_formula("16.50") is False


class TestEvaluateFormula:
    """测试公式计算。"""

    def test_simple_number(self):
        assert evaluate_formula("=16.50") == 16.50

    def test_multiplication(self):
        assert evaluate_formula("=3*5.50") == 16.50

    def test_chinese_multiply(self):
        assert evaluate_formula("=3×5.50") == 16.50

    def test_addition(self):
        assert evaluate_formula("=16.50+25.60") == 42.10

    def test_complex_expression(self):
        result = evaluate_formula("=3*5.50+2*12.80")
        assert abs(result - 42.10) < 0.01

    def test_parentheses(self):
        assert evaluate_formula("=(3+2)*5.50") == 27.50

    def test_division(self):
        assert evaluate_formula("=100/4") == 25.0

    def test_chinese_divide(self):
        assert evaluate_formula("=100÷4") == 25.0

    def test_subtraction(self):
        assert evaluate_formula("=100-30") == 70.0

    def test_empty_returns_none(self):
        assert evaluate_formula("=") is None

    def test_unsafe_expression_rejected(self):
        assert evaluate_formula("=__import__('os')") is None

    def test_letters_rejected(self):
        assert evaluate_formula("=abc") is None

    def test_integer(self):
        assert evaluate_formula("=5") == 5.0

    def test_zero(self):
        assert evaluate_formula("=0") == 0.0

    def test_spaces_in_formula(self):
        assert evaluate_formula("= 3 * 5.50 ") == 16.50


class TestExtractNumber:
    """测试从文本提取数值。"""

    def test_plain_number(self):
        assert extract_number("16.50") == 16.50

    def test_currency_prefix(self):
        assert extract_number("¥16.50") == 16.50

    def test_text_with_number(self):
        assert extract_number("共 3 项") == 3.0

    def test_label_with_value(self):
        assert extract_number("合计：¥42.10") == 42.10

    def test_integer(self):
        assert extract_number("5") == 5.0

    def test_no_number(self):
        assert extract_number("暂无数据") is None

    def test_empty(self):
        assert extract_number("") is None

    def test_multiple_numbers_returns_last(self):
        assert extract_number("¥5.50 × 3 = ¥16.50") == 16.50

    def test_single_number_in_sentence(self):
        assert extract_number("已完成 2") == 2.0

    def test_negative_number(self):
        assert extract_number("-5.3") == -5.3


class TestValidateFormula:
    """测试完整的公式验证流程。"""

    def test_exact_match(self):
        result = validate_formula("=16.50", "¥16.50")
        assert result.passed is True
        assert result.expected_value == 16.50
        assert result.actual_value == 16.50

    def test_calculated_match(self):
        result = validate_formula("=3*5.50", "¥16.50")
        assert result.passed is True

    def test_mismatch(self):
        result = validate_formula("=16.50", "¥5.50")
        assert result.passed is False
        assert result.expected_value == 16.50
        assert result.actual_value == 5.50
        assert "数值不匹配" in result.detail

    def test_complex_formula_match(self):
        result = validate_formula("=3*5.50+2*12.80", "¥42.10")
        assert result.passed is True

    def test_complex_formula_mismatch(self):
        result = validate_formula("=3*5.50+2*12.80", "¥18.30")
        assert result.passed is False

    def test_no_number_in_text(self):
        result = validate_formula("=16.50", "暂无数据")
        assert result.passed is False
        assert "未找到数值" in result.detail

    def test_invalid_formula(self):
        result = validate_formula("=abc*def", "16.50")
        assert result.passed is False
        assert "公式解析失败" in result.detail

    def test_tolerance(self):
        # 0.001 差值在默认容差0.01内
        result = validate_formula("=16.50", "¥16.501")
        assert result.passed is True

    def test_tolerance_exceeded(self):
        result = validate_formula("=16.50", "¥16.52")
        assert result.passed is False

    def test_integer_formula(self):
        result = validate_formula("=5", "5")
        assert result.passed is True

    def test_zero_formula(self):
        result = validate_formula("=0", "¥0.00")
        assert result.passed is True

    def test_shopping_cart_scenario(self):
        """模拟购物清单场景：苹果5.50×3 = 16.50，但页面显示5.50（Bug）"""
        result = validate_formula("=3*5.50", "¥5.50")
        assert result.passed is False
        assert result.expected_value == 16.50
        assert result.actual_value == 5.50

    def test_total_price_scenario(self):
        """模拟合计验证：3*5.50 + 2*12.80 = 42.10"""
        result = validate_formula("=3*5.50+2*12.80", "合计 ¥42.10")
        assert result.passed is True
