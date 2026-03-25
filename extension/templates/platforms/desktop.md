<!-- TestPilot-Template-Version: 7 -->
# Windows 桌面应用平台蓝本规则（platform = "desktop"）

> 本文件定义 Windows 桌面应用（WPF/WinForms/Electron/Qt 等）蓝本的完整规则。
> 桌面测试通过 pywinauto / UI Automation 驱动。
> 生成蓝本前**必须**通读本文件，不得跳过任何章节。

---

## 零、生成蓝本前必须先通读源代码（强制执行）

**蓝本的唯一依据是代码，不是猜测，不是常识，不是用户描述。**

在写任何 JSON 之前，必须按顺序完成：

0. **先读 `testpilot/CHANGELOG.md`（如果存在）** — 了解当前已覆盖的功能和尚未测试的模块，避免重复写或漏写；如果不存在则跳过
1. **读主窗口/入口文件** — 了解应用结构（如 `MainWindow.xaml`、`main.py`、`app.py`）
2. **读每个窗口的 UI 文件** — 找出所有控件，记录真实的 `Name`、`AutomationId`、`Content` 属性
3. **记录元素的真实标识** — `automationid:xxx` 或 `name:控件显示文字`（选择器的唯一来源）
4. **读事件处理逻辑** — 确认每个按钮点击的真实结果（弹出什么窗口、显示什么文字）
5. **确认提示方式** — 成功/失败提示是 `MessageBox`（阻塞弹窗，需 click 关闭）还是标签文字（可断言）
6. **列出已实现功能** — 代码里有什么就测什么，未实现的功能不写蓝本

**禁止跳过代码阅读直接生成蓝本。凭想象写的选择器和断言几乎必然失败。**

---

## 一、必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"desktop"` | `"desktop"` |
| `window_title` | 主窗口标题（精确匹配） | `"财务管理系统"` |
| `base_url` | **留空** `""` | `""` |
| `app_name` | 应用名称 | `"财务管理系统"` |
| `description` | 50-200字功能描述 | |
| `start_command` | 启动命令（可选） | `"MyApp.exe"` |
| `start_cwd` | 启动目录（可选） | `"./dist"` |

### 反面禁止

- ❌ `base_url` 填了 HTTP URL → 桌面应用不是 Web，留空
- ❌ 填了 `app_package` / `bundle_id`（移动端字段）
- ❌ `window_title` 填错（必须与应用标题栏完全一致）

---

## 二、封闭式动作表（只允许以下动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(窗口标题或命令), `description` | 启动/重启应用 |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `wait` | `description` | 等待（`value` 指定毫秒） |
| `assert_text` | `expected`, `description` | 断言窗口内包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动作

- ❌ `select`、`navigate_to`、`evaluate`、`call_method`（非桌面动作）
- ❌ `reset_state`、`page_query`、`scroll`（非桌面动作）

---

## 三、选择器规则

### 桌面应用选择器格式

桌面应用元素通过 **屏幕上可见的原文** 定位：

```
name:屏幕上可见的原文
```

| 界面元素 | 蓝本选择器 |
|---------|-----------|
| 按钮文字 "Login" | `name:Login` |
| 按钮文字 "确定" | `name:确定` |
| 输入框旁标签 "用户名" | `name:用户名` |
| 菜单项 "文件" | `name:文件` |
| 标签页 "设置" | `name:设置` |

### ⚠️ 绝对禁止的写法

- ❌ `name:Login按钮`（禁止在原文后加中文后缀）
- ❌ `name:确定按钮`（屏幕上只显示"确定"，不是"确定按钮"）
- ❌ `name:用户名输入框`（屏幕上只显示"用户名"，不是"用户名输入框"）
- ❌ `#id`、`.class`（Web CSS 选择器，桌面不支持）
- ❌ `accessibility_id:xxx`（移动端选择器，桌面不支持）

**核心原则：`name:` 后面跟的必须是屏幕上肉眼可见的原文，不多不少。**

---

## 四、瞬态 UI 不可断言清单

| 组件 | 说明 |
|------|------|
| 系统托盘通知 | 气泡提示，短暂显示 |
| Splash Screen | 启动画面，几秒后消失 |
| 状态栏瞬态提示 | 短暂显示后恢复原文 |
| ToolTip | 鼠标悬停提示，移开消失 |

### 代码稽核—持久性验证

```
✅ 可以断言：
   - 窗口标题栏文字
   - 按钮/标签持久显示的文字
   - 列表项、表格单元格文字
   - 状态栏持久化文字

❌ 不能断言：
   - 气泡通知
   - 启动画面
   - 工具提示（ToolTip）
```

---

## 五、等待时间计算公式

```
wait 时间 = 操作耗时 + 1500ms（预留窗口刷新 + UI Automation 响应）
```

| 场景 | wait 时间 |
|------|----------|
| 应用冷启动 | wait 3000-5000（视应用大小） |
| 弹出子窗口/对话框 | wait 1500 |
| 文件读写操作 | wait 2000 |
| 网络请求 | API时间 + 1500 |
| 纯 UI 控件操作 | wait 1000 |

---

## 六、场景自包含原则与连续流模式（flow 强制决策）

### ⚠️ 生成蓝本时必须对每个 page 做 flow 决策

**判断规则（按顺序检查）：**
1. 该 page 下有 ≥2 个场景，且都需要先登录才能操作？→ **必须 `"flow": true`**
2. 该 page 下有 ≥2 个场景是连续菜单操作或多标签页切换？→ **必须 `"flow": true`**
3. 该 page 下场景需要互相独立的干净状态（如正确登录 vs 错误登录）？→ 不写 flow（默认 false）

**简单总结：如果多个场景都要先登录再操作同一个窗口，那这个 page 必须设 `"flow": true`。不加 flow 导致每个场景都重启应用+重复登录 = 严重浪费。**

### 默认模式（`flow: false`）

- 引擎在每个场景间可能重启应用
- 每个场景的第一步应是 `navigate`（启动应用）+ `wait`（等启动完成）
- **禁止**场景间传递状态
- 如果场景需要特定前置状态（如已登录），必须在该场景内重新执行操作

### 连续流模式（`flow: true`）

在 `page` 级别设置 `"flow": true`，同一页面内的场景将连续执行：
- 仅第1个场景执行 navigate 启动应用，后续场景的 navigate **自动跳过**
- 场景间保持窗口状态
- 连续3个场景失败 → 尝试重启恢复后继续
- 每个场景仍需写 navigate（方便单独运行）

**重要：** flow 场景仍需写 navigate（方便单独运行），引擎在 flow 模式下自动跳过。

### 🚨 flow 非首场景写法（极其重要，必须遵守！）

**flow 模式下，第2个及之后的场景只写 navigate + 该场景自己的操作步骤，绝对禁止重复写登录步骤！**

引擎会跳过非首场景的 navigate，直接从第2步开始执行。如果第2步是 `fill 用户名`，但页面此时已经登录在主界面上 → 找不到输入框 → 超时失败 → 连续3步失败 → 整个场景被熔断跳过 → 后续场景全部同样失败。

| ❌ 错误写法（非首场景重复登录） | ✅ 正确写法（非首场景直接操作） |
|---|---|
| 场景2: navigate → wait → fill用户名 → fill密码 → click登录 → wait → 实际操作 | 场景2: navigate → 实际操作 → assert_text |
| 场景3: navigate → wait → fill用户名 → fill密码 → click登录 → wait → 实际操作 | 场景3: navigate → 实际操作 → assert_text |

**核心原则：flow 模式下，只有第1个场景做完整的启动+登录流程，后续场景的 navigate 后面直接写该场景自己的操作。**

---

## 七、完整 JSON 模板

```json
{
  "app_name": "你的应用名",
  "description": "50-200字功能描述",
  "base_url": "",
  "platform": "desktop",
  "window_title": "应用窗口标题",
  "start_command": "MyApp.exe",
  "start_cwd": ".",
  "pages": [
    {
      "url": "",
      "name": "主窗口",
      "scenarios": [
        {
          "name": "正确登录",
          "steps": [
            {"action": "navigate", "value": "应用窗口标题", "description": "启动应用"},
            {"action": "wait", "value": "3000", "description": "等待应用窗口完全加载"},
            {"action": "fill", "target": "name:用户名", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "name:密码", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "name:登录", "description": "点击登录按钮，验证账号后进入主界面"},
            {"action": "wait", "value": "2000", "description": "等待登录验证和界面切换"},
            {"action": "assert_text", "expected": "欢迎", "description": "验证主界面显示欢迎信息"},
            {"action": "screenshot", "description": "登录成功后的主界面"}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清单

- [ ] 查看应用界面，确认 `name:` 后的文字与屏幕显示完全一致
- [ ] `name:` 后没有添加"按钮"/"输入框"等中文后缀
- [ ] `window_title` 与应用标题栏完全匹配
- [ ] `base_url` 为空字符串 `""`
- [ ] `expected` 文字在界面上持久显示
- [ ] 启动后有足够的 wait 时间

---

## 九、踩坑清单

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| `name:登录按钮` | 找不到（屏幕只显示"登录"） | `name:登录` |
| `name:用户名输入框` | 找不到 | `name:用户名` |
| 用 CSS 选择器 `#id` | 桌面不支持 | 用 `name:原文` |
| 用 `accessibility_id:` | 桌面不支持 | 用 `name:原文` |
| 应用启动后没 wait | 窗口未就绪 | wait 3000-5000 |
| `window_title` 拼错 | 引擎找不到窗口 | 与标题栏完全一致 |
