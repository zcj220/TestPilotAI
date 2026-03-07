"""
智能输入生成器

解析蓝本中 auto: 前缀的 value 字段，自动生成合理的测试数据。

支持格式：
- auto:number:1-999       → 随机整数
- auto:number:0.01-99.99  → 随机浮点数
- auto:text:人名           → 随机中文人名
- auto:text:公司名         → 随机公司名
- auto:text:地址           → 随机地址
- auto:text:句子           → 随机短句
- auto:email              → 随机邮箱
- auto:phone              → 随机手机号
- auto:date               → 随机日期 YYYY-MM-DD
- auto:password            → 随机密码

固定值直接原样返回。
"""

import random
import string


# 常用中文姓氏和名字素材
_SURNAMES = ["张", "李", "王", "刘", "陈", "杨", "赵", "黄", "周", "吴",
             "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "高"]
_GIVEN_NAMES = ["伟", "芳", "敏", "静", "强", "磊", "洋", "勇", "军", "杰",
                "娜", "秀英", "丽", "桂英", "玉兰", "明", "超", "华", "建国", "志强",
                "文", "婷", "雪", "慧", "浩", "天宇", "子涵", "欣怡", "梓轩", "一诺"]

_COMPANY_SUFFIXES = ["科技有限公司", "信息技术公司", "网络科技公司", "软件开发公司",
                     "电子商务公司", "数据服务公司", "智能科技公司", "创新科技公司"]
_COMPANY_PREFIXES = ["华创", "中盛", "新锐", "博远", "鼎信", "恒达", "天合", "凯瑞",
                     "宏图", "智联", "云帆", "星辰", "卓越", "领航", "金桥"]

_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京",
           "苏州", "西安", "重庆", "长沙", "青岛", "大连", "厦门"]
_ROADS = ["中山路", "人民路", "建设路", "解放路", "和平路", "长安街",
          "科技大道", "创新路", "学院路", "滨江路", "文化路", "商业街"]

_SENTENCES = [
    "这是一条测试数据", "请验证功能是否正常", "自动化测试输入内容",
    "TestPilot 智能生成的数据", "用于验证输入框功能",
    "测试中文输入处理", "边界值测试样本", "功能回归测试数据",
]

_EMAIL_DOMAINS = ["test.com", "example.com", "demo.org", "testpilot.ai"]


def generate_smart_value(spec: str) -> str:
    """根据 auto: 规范生成测试数据。

    Args:
        spec: auto: 前缀的规范字符串，如 "auto:number:1-100"

    Returns:
        生成的值字符串。如果不是 auto: 前缀则原样返回。
    """
    if not spec.startswith("auto:"):
        return spec

    parts = spec[5:].split(":", 1)  # 去掉 "auto:" 后按 : 分割
    kind = parts[0].lower()
    param = parts[1] if len(parts) > 1 else ""

    if kind == "number":
        return _gen_number(param)
    elif kind == "text":
        return _gen_text(param)
    elif kind == "email":
        return _gen_email()
    elif kind == "phone":
        return _gen_phone()
    elif kind == "date":
        return _gen_date()
    elif kind == "password":
        return _gen_password()
    else:
        return spec  # 无法识别的规范，原样返回


def is_auto_value(value: str | None) -> bool:
    """判断是否是 auto: 前缀的值。"""
    return value is not None and value.startswith("auto:")


def _gen_number(param: str) -> str:
    """生成随机数字。param 格式: min-max"""
    try:
        if "-" in param:
            parts = param.split("-", 1)
            lo, hi = float(parts[0]), float(parts[1])
            if "." in param:
                return f"{random.uniform(lo, hi):.2f}"
            else:
                return str(random.randint(int(lo), int(hi)))
        else:
            return str(random.randint(1, 100))
    except (ValueError, TypeError):
        return str(random.randint(1, 100))


def _gen_text(param: str) -> str:
    """生成随机文本。param: 人名/公司名/地址/句子"""
    p = param.strip()
    if p in ("人名", "姓名", "name"):
        return random.choice(_SURNAMES) + random.choice(_GIVEN_NAMES)
    elif p in ("公司名", "公司", "company"):
        return random.choice(_COMPANY_PREFIXES) + random.choice(_COMPANY_SUFFIXES)
    elif p in ("地址", "address"):
        return (random.choice(_CITIES) + "市" +
                random.choice(_ROADS) +
                str(random.randint(1, 999)) + "号")
    elif p in ("句子", "sentence", "文本"):
        return random.choice(_SENTENCES)
    else:
        # 通用：返回 param 本身加随机后缀
        return f"{p}_{random.randint(100, 999)}"


def _gen_email() -> str:
    """生成随机邮箱。"""
    name = "test" + str(random.randint(100, 9999))
    domain = random.choice(_EMAIL_DOMAINS)
    return f"{name}@{domain}"


def _gen_phone() -> str:
    """生成随机中国手机号。"""
    prefixes = ["138", "139", "150", "151", "152", "186", "187", "188", "135", "136"]
    return random.choice(prefixes) + "".join(str(random.randint(0, 9)) for _ in range(8))


def _gen_date() -> str:
    """生成随机日期。"""
    year = random.randint(2020, 2026)
    month = random.randint(1, 12)
    day = random.randint(1, 28)  # 简化处理，避免月份天数问题
    return f"{year}-{month:02d}-{day:02d}"


def _gen_password() -> str:
    """生成随机密码（8-12位，包含大小写和数字）。"""
    length = random.randint(8, 12)
    chars = string.ascii_letters + string.digits + "!@#$"
    pwd = [
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.digits),
    ]
    pwd += [random.choice(chars) for _ in range(length - 3)]
    random.shuffle(pwd)
    return "".join(pwd)
