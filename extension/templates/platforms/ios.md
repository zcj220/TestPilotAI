<!-- TestPilot-Template-Version: 2 -->
# iOS/SwiftUI 平台蓝本规则（platform = "ios"）

> 本文件定义 iOS 原生应用和 SwiftUI 应用蓝本的完整规则。
> iOS 测试通过 Appium + XCUITest 驱动，**仅 macOS 环境支持**。
> 生成蓝本前**必须**通读本文件，不得跳过任何章节。

---

## 一、必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"ios"` | `"ios"` |
| `bundle_id` | 应用 Bundle Identifier | `"com.example.myapp"` |
| `base_url` | **必须留空** `""` | `""` |
| `app_name` | 应用名称 | `"财务记账系统"` |
| `description` | 50-200字功能描述 | |
| `udid` | 可选，多设备时必填 | `""` |

### 反面禁止

- ❌ `base_url` 填了 Bundle ID → 必须为 `""`
- ❌ 填了 `app_package` / `app_activity`（那是 Android 字段）
- ❌ 填了 `start_command`（iOS 不需要命令行启动）
- ❌ 页面 `url` 填了 HTTP 链接 → 留空 `""`

---

## 二、封闭式动作表（只允许以下动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(Bundle ID), `description` | 冷启动应用（terminateApp → launchApp） |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `wait` | `description` | 等待（`value` 指定毫秒，或 `target`+`timeout_ms` 等待元素） |
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动作

- ❌ `select`、`reset_state`、`navigate_to`、`evaluate`、`call_method`（非 iOS 动作）
- ❌ `hover`、`scroll`（Web 专用）

---

## 三、选择器规则

### SwiftUI accessibilityIdentifier → XCUITest 映射

| SwiftUI 代码 | XCUITest 属性 | 蓝本选择器 |
|---|---|---|
| `.accessibilityIdentifier("btn_login")` | `accessibility id = "btn_login"` | `accessibility_id:btn_login` |
| `TextField("用户名", text: $val).accessibilityIdentifier("tf_user")` | `accessibility id = "tf_user"` | `accessibility_id:tf_user` |
| `SecureField("密码", text: $val).accessibilityIdentifier("tf_pwd")` | `accessibility id = "tf_pwd"` | `accessibility_id:tf_pwd` |
| `Button("登录") { }.accessibilityIdentifier("btn_login")` | `accessibility id = "btn_login"` | `accessibility_id:btn_login` |
| `Text(errMsg).accessibilityIdentifier("lbl_error")` | `accessibility id = "lbl_error"` | `accessibility_id:lbl_error` |

### 选择器优先级

1. **`accessibility_id:xxx`** — 唯一推荐方式（基于 `.accessibilityIdentifier()`）
2. **`//XCUIElementType*[@name='xxx']`** — XPath 兜底（性能差）
3. **`-ios predicate string:name == 'xxx'`** — iOS Predicate 查询（高级）

### 绝对禁止的选择器

- ❌ `#id`、`.class`（Web CSS 选择器，iOS 不支持）
- ❌ `id:xxx`（Android 格式）
- ❌ `resource-id:xxx`、`uia:xxx`（Android 格式）
- ❌ `//XCUIElementTypeCell[N]`（索引定位，UI 变化即失效）
- ❌ 不带属性约束的纯类型选择器（如 `//XCUIElementTypeButton`）

### ⚠️ SwiftUI 代码侧要求

**必须**为所有可操作元素添加 `.accessibilityIdentifier()`，否则 XCUITest 无法定位：

```swift
// ✅ 正确
TextField("用户名", text: $username).accessibilityIdentifier("tf_username")
Button("登录") { login() }.accessibilityIdentifier("btn_login")

// ❌ 错误：没有 accessibilityIdentifier
TextField("用户名", text: $username)
Button("登录") { login() }
```

**命名规范建议**：`btn_`（按钮）、`tf_`（输入框）、`lbl_`（标签）、`list_`（列表）

---

## 四、瞬态 UI 不可断言清单

| 组件 | 说明 |
|------|------|
| SwiftUI `.alert()` 自动关闭 | 如果设置了定时关闭 |
| `UIAlertController` auto-dismiss | 短暂弹窗 |
| 系统级 Toast/HUD | 第三方 Toast 库的瞬态提示 |

**`.alert()` / `.sheet()` 弹出后需要 `wait 800` 等动画完成，然后才能操作弹窗内的元素。**

### 代码稽核—持久性验证

```
✅ 可以断言：
   - NavigationTitle("记账台")      → expected: "记账台"
   - Text("欢迎回来")               → expected: "欢迎回来"
   - Label 元素 .accessibilityIdentifier("lbl_error") 持久显示

❌ 不能断言：
   - 使用定时器自动消失的 alert
   - 第三方 HUD/Toast 库的瞬态提示
```

---

## 五、等待时间计算公式

```
wait 时间 = 代码中的异步延迟 + 2000ms（预留 SwiftUI 渲染 + XCUITest 刷新）
```

| 场景 | wait 时间 |
|------|----------|
| 应用冷启动（navigate） | wait 3000 |
| `.sheet()` / `.alert()` 弹出动画 | wait 800 |
| API 异步调用 + 数据渲染 | API时间 + 2000 |
| `@Published` 属性变更 + UI 刷新 | wait 1500 |
| NavigationLink 页面跳转 | wait 1500 |

### wait 两种格式

| 格式 | 用法 | 说明 |
|------|------|------|
| 简单等待 | `{"action": "wait", "value": "3000"}` | 固定等待毫秒数 |
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 轮询等元素出现 |

---

## 六、场景自包含原则与连续流模式

### 默认模式（`flow: false`）

- `navigate` 的 `value` 填 Bundle ID，引擎自动执行 `terminateApp → launchApp` 冷启动
- `@Published` 属性在 terminateApp 后自动重置
- `@AppStorage` **不会**重置（持久化到 UserDefaults）
- 每个场景的第一步：`navigate` → `wait 3000` → 操作
- **禁止**场景间传递状态

### 连续流模式（`flow: true`）

在 `page` 级别设置 `"flow": true`，同一页面内的场景将连续执行，不冷启动：
- 仅第1个场景执行 navigate 冷启动，后续场景的 navigate **自动跳过**
- 场景间保持应用状态
- 步骤失败时AI中枢尝试跳过并继续，连续失败时冷启动恢复
- 每个场景仍需写 navigate（方便单独运行）

**适用：** Tab 切换、连续操作流程。**不适用：** 需要干净状态的独立测试。

---

## 七、完整 JSON 模板

```json
{
  "app_name": "你的应用名",
  "description": "50-200字功能描述",
  "base_url": "",
  "platform": "ios",
  "bundle_id": "com.example.app",
  "udid": "",
  "pages": [
    {
      "url": "",
      "name": "登录页",
      "scenarios": [
        {
          "name": "正确账号登录成功",
          "steps": [
            {"action": "navigate", "value": "com.example.app", "description": "冷启动应用"},
            {"action": "wait", "value": "3000", "description": "等待应用启动完成，首屏渲染需2-3秒"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "accessibility_id:btn_login", "description": "点击登录按钮，触发API验证后跳转主页"},
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

## 八、代码稽核清单

- [ ] 所有可操作元素都有 `.accessibilityIdentifier()`
- [ ] 选择器 `accessibility_id:xxx` 与代码中的 identifier 完全一致
- [ ] `expected` 文字是持久化渲染的 Text/Label，不是瞬态弹窗
- [ ] `bundle_id` 与 Xcode 项目中的 Bundle Identifier 一致
- [ ] `base_url` 为空字符串 `""`
- [ ] 每个 `navigate` 后有 `wait 3000`
- [ ] Sheet/Alert 弹出后有 `wait 800`

---

## 九、踩坑清单

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 没加 `.accessibilityIdentifier()` | 找不到元素 | 代码中必须显式添加 |
| 用 CSS 选择器 `#id` | XCUITest 不支持 | 用 `accessibility_id:xxx` |
| 用 Android 格式 `id:xxx` | XCUITest 不支持 | 用 `accessibility_id:xxx` |
| navigate 后没 wait 3000 | 元素还没渲染 | 冷启动后必须等 3 秒 |
| Sheet 弹出后立即操作 | 动画未完成 | `wait 800` 后再操作 |
| `base_url` 填了 Bundle ID | 引擎困惑 | `base_url` 必须为 `""` |
