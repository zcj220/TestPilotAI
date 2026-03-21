"""
蓝本模式数据模型与解析器（v1.x）

蓝本 = 编程AI输出的测试说明书（testpilot.json），包含：
- 页面元素映射（名称 → CSS选择器）
- 测试场景（多个步骤组成的测试用例）
- 每个步骤的精确操作和预期结果

蓝本模式工作流：
1. 编程AI生成代码后，同时输出 testpilot.json
2. TestPilot AI 读取蓝本，按精确选择器执行
3. 每步截图 + AI视觉验证预期结果
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class BlueprintStep(BaseModel):
    """蓝本中的单个测试步骤。"""

    action: str = Field(description="操作类型：navigate/click/fill/select/wait/screenshot/assert_text/assert_visible/scroll")
    target: Optional[str] = Field(default=None, description="目标元素CSS选择器")
    value: Optional[str] = Field(default=None, description="输入值（fill/select用）或URL（navigate用），支持 auto: 前缀智能生成")
    expected: Optional[str] = Field(default=None, description="预期结果描述（供AI视觉验证）")
    timeout_ms: Optional[int] = Field(default=None, description="超时毫秒数（覆盖默认）")
    wait_after_ms: Optional[int] = Field(default=None, description="操作后等待毫秒数（处理异步加载/动画）")
    description: Optional[str] = Field(default=None, description="步骤说明")


class BlueprintScenario(BaseModel):
    """蓝本中的测试场景（一组步骤组成一个用例）。"""

    name: str = Field(description="场景名称，如'添加待办'")
    description: str = Field(default="", description="场景描述")
    steps: list[BlueprintStep] = Field(default_factory=list, description="步骤列表")
    precondition: Optional[str] = Field(default=None, description="前置条件描述")


class BlueprintPage(BaseModel):
    """蓝本中的单个页面定义。"""

    url: str = Field(description="页面URL或路径")
    title: Optional[str] = Field(default=None, description="预期页面标题")
    elements: dict[str, str] = Field(default_factory=dict, description="元素映射：名称→CSS选择器")
    scenarios: list[BlueprintScenario] = Field(default_factory=list, description="该页面的测试场景")


class Blueprint(BaseModel):
    """测试蓝本（testpilot.json 的完整结构）。"""
    model_config = {"arbitrary_types_allowed": True}

    app_name: str = Field(description="应用名称")
    source_path: Optional[Path] = Field(default=None, exclude=True, description="蓝本文件的磁盘路径（运行时填充，不序列化）")
    description: str = Field(default="", description="蓝本功能说明（50-200字，描述本蓝本覆盖的功能范围）")
    base_url: str = Field(default="", description="基础URL（如 http://localhost:3001）")
    version: str = Field(default="1.0", description="蓝本版本")
    platform: str = Field(default="web", description="测试平台: web/android/ios/miniprogram/desktop")
    pages: list[BlueprintPage] = Field(default_factory=list, description="页面列表")
    global_elements: dict[str, str] = Field(default_factory=dict, description="全局元素映射（所有页面共享）")
    permissions: list[str] = Field(default_factory=list, description="Android权限列表，launch时通过adb批量授权，如 android.permission.CAMERA")
    start_command: str = Field(default="", description="应用启动命令（如 npm start / python app.py），纯HTML应用留空使用内置预览服务器")
    start_cwd: str = Field(default="", description="启动命令的工作目录（相对于蓝本文件所在目录，默认为蓝本所在项目根目录）")
    app_package: str = Field(default="", description="Android应用包名（手机测试时用）")
    app_activity: str = Field(default="", description="Android启动Activity（手机测试时用）")
    bundle_id: str = Field(default="", description="iOS应用Bundle ID（iOS测试时用，如 com.testpilot.demo）")
    udid: str = Field(default="", description="iOS设备UDID（多设备时指定，单设备留空自动检测）")

    @property
    def total_scenarios(self) -> int:
        return sum(len(p.scenarios) for p in self.pages)

    @property
    def total_steps(self) -> int:
        return sum(len(s.steps) for p in self.pages for s in p.scenarios)


class BlueprintParser:
    """蓝本解析器：读取 testpilot.json 文件并解析为 Blueprint 对象。"""

    @staticmethod
    def parse_file(filepath: str | Path) -> Blueprint:
        """从文件解析蓝本。

        Args:
            filepath: testpilot.json 文件路径

        Returns:
            Blueprint 对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: JSON格式错误或蓝本结构无效
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"蓝本文件不存在: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"蓝本JSON格式错误: {e}")

        bp = BlueprintParser.parse_dict(data)
        bp.source_path = path
        return bp

    @staticmethod
    def parse_dict(data: dict) -> Blueprint:
        """从字典解析蓝本。

        Args:
            data: 蓝本字典数据

        Returns:
            Blueprint 对象

        Raises:
            ValueError: 蓝本结构无效
        """
        try:
            return Blueprint(**data)
        except Exception as e:
            raise ValueError(f"蓝本结构无效: {e}")

    @staticmethod
    def validate(blueprint: Blueprint) -> list[str]:
        """验证蓝本完整性，返回问题列表。

        Returns:
            问题列表，空列表表示蓝本完全有效
        """
        issues: list[str] = []

        if not blueprint.app_name:
            issues.append("缺少 app_name")
        if not blueprint.pages:
            issues.append("缺少 pages（至少需要一个页面）")

        is_native_app = blueprint.platform in ("android", "ios", "flutter")

        for i, page in enumerate(blueprint.pages):
            if not page.url and not is_native_app:
                issues.append(f"页面{i+1}缺少 url")
            if not page.scenarios:
                issues.append(f"页面{i+1}（{page.url}）没有测试场景")

            for j, scenario in enumerate(page.scenarios):
                if not scenario.name:
                    issues.append(f"页面{i+1}场景{j+1}缺少 name")
                if not scenario.steps:
                    issues.append(f"页面{i+1}场景'{scenario.name}'没有步骤")

                for k, step in enumerate(scenario.steps):
                    if step.action not in (
                        "navigate", "click", "fill", "select",
                        "wait", "screenshot", "assert_text", "assert_visible",
                        "scroll",
                    ):
                        issues.append(
                            f"页面{i+1}场景'{scenario.name}'步骤{k+1}："
                            f"未知操作类型'{step.action}'"
                        )
                    needs_target = step.action in ("click", "fill", "select", "assert_visible")
                    # wait 有两种用法: wait+target=等元素, wait+value=延时
                    if step.action == "wait" and not step.target and not step.value:
                        needs_target = True
                    if needs_target and not step.target:
                        issues.append(
                            f"页面{i+1}场景'{scenario.name}'步骤{k+1}："
                            f"操作'{step.action}'需要 target 选择器"
                        )
                    if step.action == "fill" and not step.value:
                        issues.append(
                            f"页面{i+1}场景'{scenario.name}'步骤{k+1}："
                            f"fill 操作需要 value"
                        )

        return issues
