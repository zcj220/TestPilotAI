"""
经验匿名化 + 分享价值评分 + 内容审核（v13.0-C）

职责：
1. 脱敏：去除项目名、文件路径、变量名、业务数据、IP
2. 保留：框架名、错误类型、修复策略、平台信息、选择器模式
3. 评分：calc_share_score() 评估经验的分享价值
4. 审核：validate_content() 拦截垃圾/误导/恶意内容
"""

import re
from dataclasses import dataclass, field


# ── 脱敏正则 ──────────────────────────────────────

_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Windows / Unix 绝对路径
    (re.compile(r'[A-Z]:\\(?:[^\s\\/:*?"<>|]+\\)*[^\s\\/:*?"<>|]+', re.IGNORECASE), '<PATH>'),
    (re.compile(r'/(?:home|Users|var|opt|srv|tmp)/\S+'), '<PATH>'),
    # 项目名占位（常见模式）
    (re.compile(r'(?:my[-_]?app|my[-_]?project|our[-_]?app)\b', re.IGNORECASE), '<APP>'),
    # IPv4 / IPv6
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '<IP>'),
    (re.compile(r'\b[0-9a-fA-F]+(?::[0-9a-fA-F]+){2,7}\b'), '<IP>'),  # IPv6 (requires colons)
    # 邮箱
    (re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b'), '<EMAIL>'),
    # 手机号（放在 IPv6/长串前，避免被误匹配）
    (re.compile(r'\b1[3-9]\d{9}\b'), '<PHONE>'),
    # 身份证
    (re.compile(r'\b\d{17}[\dXx]\b'), '<ID_CARD>'),
    # API Key / Token (支持 sk_live_xxx, pk_test_xxx 等)
    (re.compile(r'\b(?:sk|pk|key|token|secret|password)[_\-]?[A-Za-z0-9_\-]{16,}\b', re.IGNORECASE), '<SECRET>'),
    (re.compile(r'\b[A-Za-z0-9]{40,}\b'), '<TOKEN>'),
]

# 安全保留的关键词（不脱敏）
_SAFE_KEYWORDS = frozenset({
    'react', 'vue', 'angular', 'flutter', 'django', 'fastapi', 'flask',
    'playwright', 'appium', 'selenium', 'pytest', 'jest', 'mocha',
    'timeout', 'element_not_found', 'crash', 'assertion', 'layout',
    'uiautomator2', 'xctest', 'miniprogram', 'wechat', 'weixin',
    'npm', 'pip', 'poetry', 'cargo', 'gradle', 'cocoapods',
    'localhost', 'docker', 'kubernetes', 'github', 'gitlab',
    'css', 'html', 'javascript', 'typescript', 'python', 'dart', 'kotlin', 'swift',
    'querySelector', 'getElementById', 'xpath', 'accessibility_id',
    'setState', 'useEffect', 'useState', 'onMounted', 'componentDidMount',
})


def anonymize_text(text: str) -> str:
    """对文本执行脱敏处理。"""
    if not text:
        return text
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def anonymize_code(code: str) -> str:
    """对代码片段执行脱敏（保守处理，主要去路径和密钥）。"""
    if not code:
        return code
    result = code
    result = re.sub(r'[A-Z]:\\(?:[^\s\\/:*?"<>|]+\\)*[^\s\\/:*?"<>|]+', '<PATH>', result, flags=re.IGNORECASE)
    result = re.sub(r'/(?:home|Users|var|opt|srv|tmp)/\S+', '<PATH>', result)
    result = re.sub(r'(?:api_?)?(?:sk|pk|key|token|secret|password)\w*\s*=\s*["\']?[A-Za-z0-9_\-]{16,}["\']?', '<SECRET> = ***', result, flags=re.IGNORECASE)
    return result


def anonymize_experience(data: dict) -> dict:
    """对整条经验数据执行匿名化。返回脱敏后的新字典。"""
    result = dict(data)
    for field_name in ('problem_desc', 'solution_desc', 'root_cause', 'title'):
        if field_name in result and result[field_name]:
            result[field_name] = anonymize_text(result[field_name])
    if result.get('code_snippet'):
        result['code_snippet'] = anonymize_code(result['code_snippet'])
    result.pop('project_name', None)
    result.pop('project_path', None)
    result.pop('user_name', None)
    result.pop('user_email', None)
    return result


# ── 分享价值评分 ──────────────────────────────────

@dataclass
class ShareScoreBreakdown:
    """评分明细。"""
    total: float = 0.0
    has_problem: float = 0.0
    has_solution: float = 0.0
    has_root_cause: float = 0.0
    has_code: float = 0.0
    has_tags: float = 0.0
    problem_length: float = 0.0
    solution_length: float = 0.0
    platform_bonus: float = 0.0
    error_type_bonus: float = 0.0


def calc_share_score(data: dict) -> ShareScoreBreakdown:
    """
    计算分享价值评分（0-10 分）。

    评分维度：
    - 问题描述存在且有意义: 2分
    - 解决方案存在且有意义: 3分（最重要）
    - 根因分析: 1.5分
    - 代码示例: 1分
    - 标签: 0.5分
    - 描述长度奖励: 最多1分
    - 平台/错误类型加成: 最多1分
    """
    s = ShareScoreBreakdown()

    problem = (data.get('problem_desc') or '').strip()
    solution = (data.get('solution_desc') or '').strip()
    root_cause = (data.get('root_cause') or '').strip()
    code = (data.get('code_snippet') or '').strip()
    tags = data.get('tags') or []
    platform = data.get('platform', '')
    error_type = data.get('error_type', '')

    if len(problem) >= 10:
        s.has_problem = 2.0
    elif len(problem) >= 5:
        s.has_problem = 1.0

    if len(solution) >= 20:
        s.has_solution = 3.0
    elif len(solution) >= 10:
        s.has_solution = 2.0
    elif len(solution) >= 5:
        s.has_solution = 1.0

    if len(root_cause) >= 10:
        s.has_root_cause = 1.5
    elif len(root_cause) >= 5:
        s.has_root_cause = 0.5

    if len(code) >= 10:
        s.has_code = 1.0

    if len(tags) >= 2:
        s.has_tags = 0.5
    elif len(tags) >= 1:
        s.has_tags = 0.25

    combined_len = len(problem) + len(solution)
    if combined_len >= 200:
        s.problem_length = 1.0
    elif combined_len >= 100:
        s.problem_length = 0.5

    if platform and error_type:
        s.platform_bonus = 1.0
    elif platform or error_type:
        s.platform_bonus = 0.5

    s.total = round(
        s.has_problem + s.has_solution + s.has_root_cause
        + s.has_code + s.has_tags + s.problem_length
        + s.platform_bonus,
        1,
    )
    return s


# ── 内容审核 ──────────────────────────────────────

@dataclass
class ValidationResult:
    """内容审核结果。"""
    valid: bool = True
    reasons: list[str] = field(default_factory=list)


_SPAM_PATTERNS = [
    re.compile(r'(https?://\S+.*){3,}', re.IGNORECASE),  # 3+ URLs = likely spam
    re.compile(r'(加微信|加QQ|扫码|关注公众号|加群)', re.IGNORECASE),
    re.compile(r'(buy|sell|discount|coupon|promo|click here|subscribe)', re.IGNORECASE),
]

_MIN_PROBLEM_LEN = 10
_MIN_SOLUTION_LEN = 10
_MAX_TITLE_LEN = 200
_MAX_FIELD_LEN = 50_000


def validate_content(data: dict) -> ValidationResult:
    """
    审核上传内容，拦截不符合要求的提交。

    检查项：
    1. 必填字段不为空（title, platform, problem_desc, solution_desc）
    2. 最小长度（防空内容）
    3. 最大长度（防滥用）
    4. 平台合法
    5. 垃圾内容检测（广告链接、联系方式）
    6. 标题和内容不能完全相同（复制粘贴灌水）
    7. 问题和方案不能完全相同（无意义提交）
    """
    r = ValidationResult()

    title = (data.get('title') or '').strip()
    platform = (data.get('platform') or '').strip()
    problem = (data.get('problem_desc') or '').strip()
    solution = (data.get('solution_desc') or '').strip()
    code = (data.get('code_snippet') or '').strip()

    if not title:
        r.valid = False
        r.reasons.append('title is required')
    elif len(title) > _MAX_TITLE_LEN:
        r.valid = False
        r.reasons.append(f'title exceeds {_MAX_TITLE_LEN} characters')

    valid_platforms = {'web', 'android', 'ios', 'miniprogram', 'desktop'}
    if not platform:
        r.valid = False
        r.reasons.append('platform is required')
    elif platform not in valid_platforms:
        r.valid = False
        r.reasons.append(f'invalid platform: {platform}')

    if len(problem) < _MIN_PROBLEM_LEN:
        r.valid = False
        r.reasons.append(f'problem_desc must be at least {_MIN_PROBLEM_LEN} characters')

    if len(solution) < _MIN_SOLUTION_LEN:
        r.valid = False
        r.reasons.append(f'solution_desc must be at least {_MIN_SOLUTION_LEN} characters')

    for field_name, value in [('problem_desc', problem), ('solution_desc', solution), ('code_snippet', code)]:
        if len(value) > _MAX_FIELD_LEN:
            r.valid = False
            r.reasons.append(f'{field_name} exceeds {_MAX_FIELD_LEN} characters')

    if title and problem and title.strip().lower() == problem.strip().lower():
        r.valid = False
        r.reasons.append('title and problem_desc should not be identical')

    if problem and solution and problem.strip().lower() == solution.strip().lower():
        r.valid = False
        r.reasons.append('problem_desc and solution_desc should not be identical')

    combined = f"{title} {problem} {solution}"
    for pattern in _SPAM_PATTERNS:
        if pattern.search(combined):
            r.valid = False
            r.reasons.append('content flagged as spam or promotional')
            break

    return r
