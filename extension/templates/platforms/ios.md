<!-- TestPilot-Template-Version: 9 -->
# iOS/SwiftUI 平台蓝本规则（platform = "ios"�?

> 本文件定�?iOS 原生应用�?SwiftUI 应用蓝本的完整规则�?
> iOS 测试通过 Appium + XCUITest 驱动�?*�?macOS 环境支持**�?
> 生成蓝本�?*必须**通读本文件，不得跳过任何章节�?

---

## 零、生成蓝本前必须先通读源代码（强制执行�?

**蓝本的唯一依据是代码，不是猜测，不是常识，不是用户描述�?*

在写任何 JSON 之前，必须按顺序完成�?

0. **先读 `testpilot/CHANGELOG.md`（如果存在）** �?了解当前已覆盖的功能和尚未测试的模块，避免重复写或漏写；如果不存在则跳过
1. **读入�?路由文件** �?了解应用整体结构和页面列表（�?`ContentView.swift`、`@main App`�?
2. **读每个页面的 UI 文件** �?找出所有可操作元素（Button、TextField、NavigationLink 等）
3. **记录 accessibilityIdentifier** �?`.accessibilityIdentifier("xxx")` 是选择器的唯一来源，没有则无法定位
4. **读业务逻辑** �?确认每个操作的真实结果（跳转哪里、显示什么文字）
5. **确认提示方式** �?成功/失败提示�?`.alert()`（瞬态，**不可断言**）还是持久化 `Text`（可断言�?
6. **列出已实现功�?* �?代码里有什么就测什么，未实现的功能不写蓝本

**禁止跳过代码阅读直接生成蓝本。凭想象写的选择器和断言几乎必然失败�?*

---

## 一、必填字�?

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"ios"` | `"ios"` |
| `bundle_id` | 应用 Bundle Identifier | `"com.example.myapp"` |
| `base_url` | **必须留空** `""` | `""` |
| `app_name` | 应用名称 | `"财务记账系统"` |
| `description` | 50-200字功能描�?| |
| `udid` | 可选，多设备时必填 | `""` |

### 反面禁止

- �?`base_url` 填了 Bundle ID �?必须�?`""`
- �?填了 `app_package` / `app_activity`（那�?Android 字段�?
- �?填了 `start_command`（iOS 不需要命令行启动�?
- �?页面 `url` 填了 HTTP 链接 �?留空 `""`

---

## 二、封闭式动作表（只允许以下动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(Bundle ID), `description` | 冷启动应用（terminateApp �?launchApp�?|
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `wait` | `description` | 等待（`value` 指定毫秒，或 `target`+`timeout_ms` 等待元素�?|
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动�?

- �?`select`、`reset_state`、`navigate_to`、`evaluate`、`call_method`（非 iOS 动作�?
- �?`hover`、`scroll`（Web 专用�?

---

## 三、选择器规�?

### SwiftUI accessibilityIdentifier �?XCUITest 映射

| SwiftUI 代码 | XCUITest 属�?| 蓝本选择�?|
|---|---|---|
| `.accessibilityIdentifier("btn_login")` | `accessibility id = "btn_login"` | `accessibility_id:btn_login` |
| `TextField("用户�?, text: $val).accessibilityIdentifier("tf_user")` | `accessibility id = "tf_user"` | `accessibility_id:tf_user` |
| `SecureField("密码", text: $val).accessibilityIdentifier("tf_pwd")` | `accessibility id = "tf_pwd"` | `accessibility_id:tf_pwd` |
| `Button("登录") { }.accessibilityIdentifier("btn_login")` | `accessibility id = "btn_login"` | `accessibility_id:btn_login` |
| `Text(errMsg).accessibilityIdentifier("lbl_error")` | `accessibility id = "lbl_error"` | `accessibility_id:lbl_error` |

### 🚨 选择器三步验证（强制执行，每�?target 都必须做�?

写任何一�?`target` 选择器之前，必须完成以下三步�?*缺一不可**�?

1. **定位源码**：找到该元素所在的 `.swift` 文件，定位到具体�?
2. **确认 identifier 存在**：从代码中复�?`.accessibilityIdentifier("xxx")` �?`xxx` 值（**如果没有 `.accessibilityIdentifier()`，该元素无法定位，必须先让开发者添�?*�?
3. **唯一性验�?*：在项目中全局搜索 `accessibilityIdentifier("xxx")`，确认只出现一�?

**不做三步验证就写的选择�?= 必然出错。这是选择器失败的第一大原因�?*

### 选择器优先级

1. **`accessibility_id:xxx`** �?唯一推荐方式（基�?`.accessibilityIdentifier()`�?
2. **`//XCUIElementType*[@name='xxx']`** �?XPath 兜底（性能差）
3. **`-ios predicate string:name == 'xxx'`** �?iOS Predicate 查询（高级）

### 绝对禁止的选择�?

- �?`#id`、`.class`（Web CSS 选择器，iOS 不支持）
- �?`id:xxx`（Android 格式�?
- �?`resource-id:xxx`、`uia:xxx`（Android 格式�?
- �?`//XCUIElementTypeCell[N]`（索引定位，UI 变化即失效）
- �?不带属性约束的纯类型选择器（�?`//XCUIElementTypeButton`�?

### ⚠️ SwiftUI 代码侧要�?

**必须**为所有可操作元素添加 `.accessibilityIdentifier()`，否�?XCUITest 无法定位�?

```swift
// �?正确
TextField("用户�?, text: $username).accessibilityIdentifier("tf_username")
Button("登录") { login() }.accessibilityIdentifier("btn_login")

// �?错误：没�?accessibilityIdentifier
TextField("用户�?, text: $username)
Button("登录") { login() }
```

**命名规范建议**：`btn_`（按钮）、`tf_`（输入框）、`lbl_`（标签）、`list_`（列表）

---

## 四、瞬�?UI 不可断言清单

| 组件 | 说明 |
|------|------|
| SwiftUI `.alert()` 自动关闭 | 如果设置了定时关�?|
| `UIAlertController` auto-dismiss | 短暂弹窗 |
| 系统�?Toast/HUD | 第三�?Toast 库的瞬态提�?|

**`.alert()` / `.sheet()` 弹出后需�?`wait 800` 等动画完成，然后才能操作弹窗内的元素�?*

### 代码稽核—持久性验�?

```
�?可以断言�?
   - NavigationTitle("记账�?)      �?expected: "记账�?
   - Text("欢迎回来")               �?expected: "欢迎回来"
   - Label 元素 .accessibilityIdentifier("lbl_error") 持久显示

�?不能断言�?
   - 使用定时器自动消失的 alert
   - 第三�?HUD/Toast 库的瞬态提�?
```

---

## 五、等待时间计算公�?

```
wait 时间 = 代码中的异步延迟 + 2000ms（预�?SwiftUI 渲染 + XCUITest 刷新�?
```

| 场景 | wait 时间 |
|------|----------|
| 应用冷启动（navigate�?| wait 3000 |
| `.sheet()` / `.alert()` 弹出动画 | wait 800 |
| API 异步调用 + 数据渲染 | API时间 + 2000 |
| `@Published` 属性变�?+ UI 刷新 | wait 1500 |
| NavigationLink 页面跳转 | wait 1500 |

### wait 两种格式

| 格式 | 用法 | 说明 |
|------|------|------|
| 简单等�?| `{"action": "wait", "value": "3000"}` | 固定等待毫秒�?|
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 轮询等元素出�?|

---

## 六、场景自包含原则与连续流模式（flow 强制决策�?

### ⚠️ 生成蓝本时必须对每个 page �?flow 决策

**判断规则（按顺序检查）�?*
1. �?page 下有 �? 个场景，且都需要先登录才能操作？→ **必须 `"flow": true`**
2. �?page 下有 �? 个场景是同页�?Tab 切换或连续操作？�?**必须 `"flow": true`**
3. �?page 下场景需要互相独立的干净状态（如正确登�?vs 错误登录）？�?不写 flow（默�?false�?

**简单总结：如果多个场景都要先登录再操作同一个页面，那这�?page 必须�?`"flow": true`。不�?flow 导致每个场景都冷启动+重复登录 = 严重浪费�?*

### 默认模式（`flow: false`�?

- `navigate` �?`value` �?Bundle ID，引擎自动执�?`terminateApp �?launchApp` 冷启�?
- `@Published` 属性在 terminateApp 后自动重�?
- `@AppStorage` **不会**重置（持久化�?UserDefaults�?
- 每个场景的第一步：`navigate` �?`wait 3000` �?操作
- **禁止**场景间传递状�?

### 连续流模式（`flow: true`�?

�?`page` 级别设置 `"flow": true`，同一页面内的场景将连续执行，不冷启动�?
- 仅第1个场景执�?navigate 冷启动，后续场景�?navigate **自动跳过**
- 场景间保持应用状�?
- 连续3个场景失�?�?尝试冷启动恢复后继续
- 每个场景仍需�?navigate（方便单独运行）

**重要�?* flow 场景仍需�?navigate（方便单独运行），引擎在 flow 模式下自动跳过�?

### 🚨 flow 非首场景写法（极其重要，必须遵守！）

**flow 模式下，�?个及之后的场景只�?navigate + 该场景自己的操作步骤，绝对禁止重复写登录步骤�?*

引擎会跳过非首场景的 navigate，直接从�?步开始执行。如果第2步是 `fill 用户名`，但页面此时已经登录在功能页�?�?找不到输入框 �?超时失败 �?连续3步失�?�?整个场景被熔断跳�?�?后续场景全部同样失败�?

| �?错误写法（非首场景重复登录） | �?正确写法（非首场景直接操作） |
|---|---|
| 场景2: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?实际操作 | 场景2: navigate �?实际操作 �?assert_text |
| 场景3: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?实际操作 | 场景3: navigate �?实际操作 �?assert_text |

**核心原则：flow 模式下，只有�?个场景做完整的冷启动+登录流程，后续场景的 navigate 后面直接写该场景自己的操作�?*

---

## 七、完�?JSON 模板

```json
{
  "app_name": "你的应用�?,
  "description": "50-200字功能描�?,
  "base_url": "",
  "platform": "ios",
  "bundle_id": "com.example.app",
  "udid": "",
  "pages": [
    {
      "url": "",
      "name": "登录�?,
      "scenarios": [
        {
          "name": "正确账号登录成功",
          "steps": [
            {"action": "navigate", "value": "com.example.app", "description": "冷启动应�?},
            {"action": "wait", "value": "3000", "description": "等待应用启动完成，首屏渲染需2-3�?},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "accessibility_id:btn_login", "description": "点击登录按钮，触发API验证后跳转主�?},
            {"action": "wait", "value": "3000", "description": "等待API调用+页面跳转完成"},
            {"action": "assert_text", "expected": "主页", "description": "验证NavigationTitle显示'主页'"},
            {"action": "screenshot", "description": "登录成功后的主页"}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清�?

- [ ] 所有可操作元素都有 `.accessibilityIdentifier()`
- [ ] 选择�?`accessibility_id:xxx` 与代码中�?identifier 完全一�?
- [ ] `expected` 文字是持久化渲染�?Text/Label，不是瞬态弹�?
- [ ] `bundle_id` �?Xcode 项目中的 Bundle Identifier 一�?
- [ ] `base_url` 为空字符�?`""`
- [ ] 每个 `navigate` 后有 `wait 3000`
- [ ] Sheet/Alert 弹出后有 `wait 800`
- [ ] 确认每个操作后有 `assert_text` 或 `screenshot` 验证结果

### 🚨 输出前强制回检（3项必检，不通过必须修正）

**回检1 — flow 决策**：扫描每个 page，该 page 下是否有 ≥2 个场景都需要先登录再操作？
- 是 → 该 page **必须**有 `"flow": true`，且非首场景**禁止**写登录步骤
- 否 → 不设 flow（场景各自独立登录）

**回检2 — 断言覆盖**：扫描每个 scenario，是否至少有一个 `assert_text` 步骤？
- **只有 screenshot 没有 assert_text = 不合格**，必须补充文本断言
- `expected` 必须是持久化渲染的 Text/Label，不是 `.alert()` 瞬态弹窗

**回检3 — 重复登录检查**：扫描整个蓝本，是否存在 ≥3 个场景都有完全相同的登录步骤序列？
- 是 → 必须把这些场景合并到同一个 page 并启用 `"flow": true`，只在首场景登录一次

---

## 九、踩坑清�?

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 没加 `.accessibilityIdentifier()` | 找不到元�?| 代码中必须显式添�?|
| �?CSS 选择�?`#id` | XCUITest 不支�?| �?`accessibility_id:xxx` |
| �?Android 格式 `id:xxx` | XCUITest 不支�?| �?`accessibility_id:xxx` |
| navigate 后没 wait 3000 | 元素还没渲染 | 冷启动后必须�?3 �?|
| Sheet 弹出后立即操�?| 动画未完�?| `wait 800` 后再操作 |
| `base_url` 填了 Bundle ID | 引擎困惑 | `base_url` 必须�?`""` |
