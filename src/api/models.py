"""
API 请求和响应的数据模型定义。

所有模型使用 Pydantic v2，提供自动验证和文档生成。
"""

from typing import Optional

from pydantic import BaseModel, Field


# ── 请求模型 ──────────────────────────────────────────────


class CreateSandboxRequest(BaseModel):
    """创建沙箱的请求体。"""
    project_path: str = Field(..., description="用户项目文件夹的绝对路径")
    app_port: Optional[int] = Field(default=None, description="被测应用端口")


class ExecCommandRequest(BaseModel):
    """在沙箱内执行命令的请求体。"""
    command: str = Field(..., description="要执行的 shell 命令")
    workdir: Optional[str] = Field(default=None, description="工作目录")


class NavigateRequest(BaseModel):
    """浏览器导航请求体。"""
    url: str = Field(..., description="目标 URL")
    wait_until: str = Field(default="load", description="等待条件")


class ClickRequest(BaseModel):
    """浏览器点击请求体。"""
    selector: str = Field(..., description="CSS 选择器")


class FillRequest(BaseModel):
    """浏览器输入请求体。"""
    selector: str = Field(..., description="输入框的 CSS 选择器")
    text: str = Field(..., description="要输入的文本")


class ScreenshotRequest(BaseModel):
    """浏览器截图请求体。"""
    name: str = Field(default="", description="截图名称")
    full_page: bool = Field(default=False, description="是否截取全页")


# ── 响应模型 ──────────────────────────────────────────────


class SandboxResponse(BaseModel):
    """沙箱操作响应体。"""
    sandbox_id: str
    message: str
    status: Optional[dict] = None


class CommandResponse(BaseModel):
    """命令执行响应体。"""
    exit_code: int
    output: str


class BrowserResponse(BaseModel):
    """浏览器操作响应体。"""
    success: bool
    message: str
    data: Optional[dict] = None


class HealthResponse(BaseModel):
    """健康检查响应体。"""
    status: str
    version: str
    sandbox_count: int
    browser_ready: bool


# ── 测试任务模型 ──────────────────────────────────────────


class RunBlueprintRequest(BaseModel):
    """蓝本模式测试请求体。"""
    blueprint_path: str = Field(..., description="testpilot.json 蓝本文件路径")
    base_url: str = Field(default="", description="基础URL（覆盖蓝本中的base_url）")
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="AI 思考深度：minimal / low / medium / high",
    )
    cloud_token: Optional[str] = Field(
        default=None,
        description="云端用户JWT token，提供后启用积分校验与扣减",
    )


class RunMobileBlueprintRequest(BaseModel):
    """手机蓝本模式测试请求体。"""
    blueprint_path: str = Field(..., description="testpilot.json 蓝本文件路径")
    mobile_session_id: str = Field(default="", description="已创建的移动端 Session ID（留空则自动创建）")
    base_url: str = Field(default="", description="基础URL（覆盖蓝本中的base_url）")


class ExploreRequest(BaseModel):
    """快速探索测试请求体。"""
    url: str = Field(..., description="被测应用的 URL")
    description: str = Field(default="", description="应用描述")
    max_actions: int = Field(default=15, description="最大操作数（默认15）")


class GenerateBlueprintRequest(BaseModel):
    """蓝本自动生成请求体（v10.1）。"""
    url: str = Field(..., description="被测应用的 URL")
    app_name: str = Field(default="", description="应用名称（空则从页面标题自动推断）")
    description: str = Field(default="", description="应用描述（帮助AI理解上下文）")
    output_path: str = Field(default="", description="保存路径（空则不保存文件，只返回JSON）")
    platform: str = Field(default="web", description="平台类型：web/miniprogram/android/desktop")


class GenerateBlueprintResponse(BaseModel):
    """蓝本自动生成响应体（v10.1）。"""
    success: bool
    app_name: str
    base_url: str
    total_scenarios: int
    total_steps: int
    blueprint_json: dict = Field(description="完整蓝本JSON")
    saved_path: str = Field(default="", description="保存路径（如已保存）")


class RunBlueprintBatchRequest(BaseModel):
    """批量蓝本测试请求体。"""
    blueprint_paths: list[str] = Field(..., description="蓝本文件路径列表")
    base_url: str = Field(default="", description="基础URL（覆盖所有蓝本中的base_url）")


class BlueprintSummary(BaseModel):
    """蓝本摘要信息（用于列表展示）。"""
    file_path: str = Field(description="蓝本文件绝对路径")
    file_name: str = Field(description="文件名")
    app_name: str = Field(default="", description="应用名称")
    description: str = Field(default="", description="功能说明")
    platform: str = Field(default="web", description="测试平台")
    version: str = Field(default="1.0", description="蓝本版本")
    scenario_count: int = Field(default=0, description="场景数")
    step_count: int = Field(default=0, description="步骤数")


class BlueprintListResponse(BaseModel):
    """蓝本列表响应体。"""
    blueprints: list[BlueprintSummary] = Field(default_factory=list)
    total: int = Field(default=0)


class BatchReportItem(BaseModel):
    """批量测试中单个蓝本的结果。"""
    blueprint_path: str
    app_name: str
    platform: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    bug_count: int
    pass_rate: float
    duration_seconds: float
    report_markdown: str


class BatchTestReportResponse(BaseModel):
    """批量测试汇总响应体。"""
    total_blueprints: int
    passed_blueprints: int
    failed_blueprints: int
    total_steps: int
    passed_steps: int
    failed_steps: int
    total_bugs: int
    overall_pass_rate: float
    total_duration_seconds: float
    results: list[BatchReportItem] = Field(default_factory=list)
    summary_markdown: str = Field(default="")


class RunTestRequest(BaseModel):
    """启动测试任务的请求体。"""
    url: str = Field(..., description="被测应用的 URL")
    description: str = Field(default="", description="应用描述")
    focus: str = Field(default="核心功能", description="测试重点")
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="AI 思考深度：minimal / low / medium / high",
    )
    auto_repair: bool = Field(
        default=False,
        description="是否在发现Bug后自动修复（v0.4）",
    )
    project_path: str = Field(
        default="",
        description="被测项目的根目录绝对路径（auto_repair=true时必填）",
    )


class StepDetail(BaseModel):
    """单步执行详情（含日志）。"""
    step: int = Field(..., description="步骤序号")
    action: str = Field(default="", description="操作类型")
    description: str = Field(default="", description="步骤描述")
    status: str = Field(default="pending", description="执行状态: passed/failed/error")
    duration_seconds: float = Field(default=0.0, description="执行耗时（秒）")
    error_message: str = Field(default="", description="错误信息")
    screenshot_path: Optional[str] = Field(default=None, description="截图路径")


class BugDetail(BaseModel):
    """Bug详情（含日志切片）。"""
    severity: str = Field(..., description="严重度: high/medium/low")
    title: str = Field(default="", description="Bug标题")
    description: str = Field(default="", description="详细描述（含日志切片）")
    category: str = Field(default="", description="Bug类别")
    location: str = Field(default="", description="问题位置")
    step_number: Optional[int] = Field(default=None, description="关联步骤号")
    screenshot_path: Optional[str] = Field(default=None, description="相关截图")


class TestReportResponse(BaseModel):
    """测试报告响应体。"""
    test_name: str
    url: str
    total_steps: int
    passed_steps: int
    failed_steps: int
    bug_count: int
    pass_rate: float
    duration_seconds: float
    report_markdown: str
    steps: list[StepDetail] = Field(default_factory=list, description="每步执行详情")
    bugs: list[BugDetail] = Field(default_factory=list, description="完整Bug列表（含日志切片）")
    repair_summary: Optional[str] = Field(
        default=None,
        description="自动修复报告摘要（v0.4）",
    )
    fixed_bug_count: Optional[int] = Field(
        default=None,
        description="成功修复的Bug数（v0.4）",
    )
    credits_used: Optional[int] = Field(
        default=None,
        description="本次测试消耗的积分（v0.7）",
    )
    estimated_cost: Optional[float] = Field(
        default=None,
        description="本次测试估算API成本（元）（v0.7）",
    )
    stopped: bool = Field(
        default=False,
        description="测试是否被用户手动停止（v10.6）",
    )
