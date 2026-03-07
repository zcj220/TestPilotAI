"""
智能输入生成器的单元测试。

验证：
- auto: 前缀识别
- 各种类型的值生成（数字、文本、邮箱、手机号、日期、密码）
- 非 auto: 值原样返回
"""

import re

from src.testing.smart_input import generate_smart_value, is_auto_value


class TestIsAutoValue:
    """auto: 前缀识别测试。"""

    def test_auto_prefix(self) -> None:
        assert is_auto_value("auto:number:1-100") is True
        assert is_auto_value("auto:email") is True
        assert is_auto_value("auto:text:人名") is True

    def test_non_auto(self) -> None:
        assert is_auto_value("hello") is False
        assert is_auto_value("") is False
        assert is_auto_value(None) is False

    def test_partial_auto(self) -> None:
        assert is_auto_value("AUTO:number") is False  # 大小写敏感
        assert is_auto_value("auto") is False  # 没有冒号


class TestGenerateNumber:
    """数字生成测试。"""

    def test_integer_range(self) -> None:
        for _ in range(20):
            val = generate_smart_value("auto:number:1-100")
            num = int(val)
            assert 1 <= num <= 100

    def test_float_range(self) -> None:
        for _ in range(20):
            val = generate_smart_value("auto:number:0.01-99.99")
            num = float(val)
            assert 0.01 <= num <= 99.99

    def test_default_number(self) -> None:
        val = generate_smart_value("auto:number:")
        num = int(val)
        assert 1 <= num <= 100


class TestGenerateText:
    """文本生成测试。"""

    def test_chinese_name(self) -> None:
        val = generate_smart_value("auto:text:人名")
        assert len(val) >= 2  # 至少一个姓+一个名

    def test_company_name(self) -> None:
        val = generate_smart_value("auto:text:公司名")
        assert "公司" in val

    def test_address(self) -> None:
        val = generate_smart_value("auto:text:地址")
        assert "市" in val

    def test_sentence(self) -> None:
        val = generate_smart_value("auto:text:句子")
        assert len(val) > 3

    def test_generic_text(self) -> None:
        val = generate_smart_value("auto:text:自定义标签")
        assert "自定义标签" in val


class TestGenerateOther:
    """其他类型生成测试。"""

    def test_email(self) -> None:
        val = generate_smart_value("auto:email")
        assert "@" in val
        assert "." in val

    def test_phone(self) -> None:
        val = generate_smart_value("auto:phone")
        assert len(val) == 11
        assert val.isdigit()

    def test_date(self) -> None:
        val = generate_smart_value("auto:date")
        assert re.match(r"\d{4}-\d{2}-\d{2}", val)

    def test_password(self) -> None:
        val = generate_smart_value("auto:password")
        assert 8 <= len(val) <= 12
        assert any(c.isupper() for c in val)
        assert any(c.islower() for c in val)
        assert any(c.isdigit() for c in val)


class TestPassthrough:
    """非auto值原样返回测试。"""

    def test_plain_text(self) -> None:
        assert generate_smart_value("hello world") == "hello world"

    def test_empty_string(self) -> None:
        assert generate_smart_value("") == ""

    def test_unknown_auto_type(self) -> None:
        val = generate_smart_value("auto:unknown_type")
        assert val == "auto:unknown_type"
