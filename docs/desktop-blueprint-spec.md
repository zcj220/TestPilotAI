# 桌面应用蓝本规范（Desktop Blueprint Specification）

> TestPilot AI 桌面测试蓝本编写指南，适用于所有 Windows 桌面应用。

## 一、蓝本结构

```json
{
  "app_name": "应用名称",
  "description": "测试说明",
  "platform": "desktop",
  "base_url": "",
  "window_title": "窗口标题（必填，用于定位窗口）",
  "app_exe": "启动命令（可选，支持相对路径，在蓝本目录执行）",
  "pages": [
    {
      "url": "",
      "name": "测试模块名",
      "description": "模块说明",
      "scenarios": [
        {
          "name": "场景名",
          "description": "场景说明",
          "steps": [...]
        }
      ]
    }
  ]
}
```

## 二、必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `app_name` | string | 应用名称，显示在报告中 |
| `platform` | string | 固定为 `"desktop"` |
| `window_title` | string | **窗口标题**，引擎通过 `FindWindow` 定位窗口。必须与应用标题栏文字完全一致 |

## 三、可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `app_exe` | string | 启动命令。引擎行为：有旧窗口→关闭→重启；无旧窗口→直接启动。在蓝本所在目录执行，支持相对路径 |
| `description` | string | 测试说明 |
| `base_url` | string | 桌面测试留空 |

## 四、启动策略

### 4.1 自动启动（推荐）

蓝本写 `app_exe`，引擎自动管理应用生命周期：

```json
{
  "window_title": "MyApp",
  "app_exe": "python my_app.py"
}
```

引擎执行流程：
1. `FindWindow("MyApp")` 查找旧窗口
2. 如果存在 → `WM_CLOSE` 关闭 → 等待窗口消失
3. 在**蓝本所在目录**执行 `app_exe`（`subprocess.Popen(app_exe, shell=True, cwd=蓝本目录)`）
4. 等待 3 秒让应用初始化
5. 开始测试

### 4.2 手动启动

不写 `app_exe`，用户需自己启动应用后再跑测试。适用于需要复杂环境准备的应用。

### 4.3 app_exe 示例

```json
"app_exe": "python my_app.py"
"app_exe": "notepad.exe"
"app_exe": "D:\\Programs\\MyApp\\MyApp.exe"
"app_exe": "start /B my_app.exe --port 8080"
```

## 五、步骤动作（actions）

| 动作 | 必填参数 | 说明 |
|------|----------|------|
| `click` | `target`, `description` | 点击元素。先 UI Automation 精确查找，失败则 AI 视觉降级 |
| `fill` | `target`, `value`, `description` | 输入文本。自动清空旧内容（Ctrl+A + Backspace），再输入 |
| `screenshot` | `description` | 截图保存（仅客户区，不含标题栏） |
| `assert_text` | `expected`, `description` | 断言页面包含指定文本。通过 AI OCR 识别页面所有可见文字 |
| `wait` | `description` | 等待 1.5 秒（页面切换/动画完成） |
| `navigate` | `description` | 桌面测试中通常不用（Web 专用） |

## 六、target 写法（关键！直接决定定位成功率）

引擎定位优先级：
1. **UI Automation**（精确）：搜索 `Name`、`AutomationId`、`ClassName` 匹配
2. **AI 视觉**（降级）：截图发给 AI，用 `target` + `description` 定位元素

### ⚠️ 铁律：target 必须使用屏幕上可见的原文

`target` 的 `name:` 后面写的文字必须是**应用界面上肉眼可见的原文**，不要加任何中文后缀（按钮、输入框、列表项等）。

```
✅ 正确写法（屏幕原文）：
"target": "name:Login"
"target": "name:Add"
"target": "name:Toggle Done"
"target": "name:Buy milk"
"target": "name:输入待办事项..."     （placeholder也算可见文字）

❌ 错误写法（加了中文后缀）：
"target": "name:Login按钮"           ← 屏幕上只有"Login"，没有"按钮"
"target": "name:Add按钮"             ← 屏幕上只有"Add"
"target": "name:Buy milk列表项"      ← 屏幕上只有"○ Buy milk"
"target": "name:用户名输入框"         ← 屏幕上只有placeholder文字
```

**为什么？** AI视觉定位时会在截图中搜索 `target` 描述的元素。如果写"Login按钮"，AI在截图中看到的是"Login"，匹配不上"Login按钮"就会定位失败。

### description 才是辅助描述的位置

`description` 用来补充**位置、颜色、大小等辅助信息**，帮助AI更精确定位：

```json
{
  "action": "click",
  "target": "name:Delete",
  "description": "点击列表下方中间的红色Delete按钮"
}
```

```json
{
  "action": "click",
  "target": "name:Buy milk",
  "description": "点击列表中包含Buy milk文字的那一行"
}
```

### description 最佳实践

- **说明位置**：上方/下方/左侧/右侧/中间
- **说明颜色**：蓝色/红色/绿色/灰色
- **说明相邻元素**：输入框右侧的、列表下方的
- **说明元素类型**：按钮/输入框/列表行（在description里说，不在target里说）

### 完整 target 规则

| 规则 | 说明 | 示例 |
|------|------|------|
| 用屏幕原文 | `name:` 后写界面可见文字 | `name:Login` |
| 不加后缀 | 不加"按钮""输入框""列表项" | ~~`name:Login按钮`~~ |
| placeholder可用 | 输入框的占位符算可见文字 | `name:请输入用户名` |
| 列表项用内容文字 | 点击列表行时写行内文字 | `name:Buy milk` |
| description补充定位 | 颜色/位置/类型写在description | `"description": "红色按钮"` |

## 七、场景设计原则

### 7.1 状态连贯

场景按执行顺序排列，后一个场景的初始状态 = 前一个场景的结束状态。

```
场景1: 登录 → 进入主页
场景2: 主页操作（基于场景1的结束状态）
场景3: 登出 → 回到登录页
场景4: 错误登录验证（基于场景3的结束状态）
```

### 7.2 每个场景独立断言

每个场景至少包含一个 `assert_text` 或 `screenshot` 步骤来验证结果。

### 7.3 页面切换后加 wait

点击导致页面变化（登录、跳转、弹窗）后，加 `wait` 等待渲染完成：

```json
{ "action": "click", "target": "name:Login按钮", "description": "点击登录" },
{ "action": "wait", "description": "等待页面切换" },
{ "action": "screenshot", "description": "登录后的主页" }
```

## 八、完整蓝本示例

```json
{
  "app_name": "Calculator",
  "description": "Windows计算器测试",
  "platform": "desktop",
  "base_url": "",
  "window_title": "计算器",
  "app_exe": "calc.exe",
  "pages": [
    {
      "url": "",
      "name": "基本运算",
      "description": "测试加减乘除",
      "scenarios": [
        {
          "name": "加法",
          "description": "验证 2+3=5",
          "steps": [
            { "action": "screenshot", "description": "计算器初始状态" },
            { "action": "click", "target": "name:2按钮", "description": "点击数字2" },
            { "action": "click", "target": "name:加号按钮", "description": "点击加号" },
            { "action": "click", "target": "name:3按钮", "description": "点击数字3" },
            { "action": "click", "target": "name:等号按钮", "description": "点击等号" },
            { "action": "screenshot", "description": "计算结果" },
            { "action": "assert_text", "expected": "5", "description": "验证结果为5" }
          ]
        }
      ]
    }
  ]
}
```

## 九、测试时注意事项

1. **测试期间请勿操作鼠标键盘**：桌面测试通过模拟鼠标点击和键盘输入操作应用，用户操作会干扰测试
2. **窗口标题必须准确**：`window_title` 必须与应用标题栏完全一致，否则找不到窗口
3. **AI 定位依赖截图质量**：确保应用窗口不被其他窗口遮挡
4. **网络要求**：AI 视觉定位和 OCR 需要调用云端 API，确保网络通畅

## 十、适用框架

| 框架 | 点击 | 输入 | UI Automation | 备注 |
|------|------|------|---------------|------|
| WPF/WinForms | ✅ | ✅ | ✅ 完整支持 | 最佳体验 |
| Electron | ✅ | ✅ | ✅ 部分支持 | Chrome DevTools 辅助 |
| Qt/PyQt | ✅ | ✅ | ✅ 部分支持 | 需要 accessible 插件 |
| tkinter | ✅ | ✅ | ❌ 几乎为空 | 纯 AI 视觉模式 |
| Java Swing | ✅ | ✅ | ✅ 部分支持 | JAB 辅助 |
