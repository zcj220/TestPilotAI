# TestPilot AI — iOS 蓝本生成提示词

> 前置条件：请先阅读 `docs/blueprint-prompt-golden-rules.md` 中的8条黄金规则。

---

## iOS 平台专属规则

### 适用范围

iOS 蓝本通过 **Appium + XCUITest** 驱动在 iPhone/iPad 真机或模拟器上执行自动化测试。**仅 macOS 环境支持**（需要 Xcode + 已签名的 WebDriverAgent）。

### 蓝本必填字段

```json
{
  "app_name": "应用名称",
  "description": "50-200字功能描述",
  "base_url": "",
  "version": "1.0",
  "platform": "ios",
  "bundle_id": "com.example.app",
  "udid": ""
}
```

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | **必须**为 `"ios"` | `"ios"` |
| `bundle_id` | 应用的 Bundle Identifier（**必填**） | `"com.testpilot.demo"` |
| `udid` | 设备 UDID（多设备时必填，单设备可留空） | `"00008020-000339A42ED8003A"` |
| `base_url` | **留空**，原生 iOS 应用不需要 URL | `""` |

> 页面的 `url` 字段也留空，原生应用没有 HTTP URL，页面区分靠 `title` 字段。

---

## SwiftUI accessibilityIdentifier → XCUITest 选择器映射（核心规则）

SwiftUI 的 `.accessibilityIdentifier()` 修饰符在 XCUITest 端映射为 `accessibility id` 属性。**蓝本选择器必须基于这些映射规则**：

| SwiftUI 代码 | XCUITest 属性 | 蓝本选择器 |
|---|---|---|
| `.accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `TextField("占位文字", text: $val).accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `SecureField("密码", text: $val).accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `Button("按钮文字").accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `Text("文字").accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `Image(systemName: "icon").accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `List { ... }.accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |
| `Toggle(isOn: $flag).accessibilityIdentifier("xxx")` | `accessibility id = "xxx"` | `accessibility_id:xxx` |

> ⚠️ **关键要求**：SwiftUI 代码中**必须**为所有可操作/可验证元素显式添加 `.accessibilityIdentifier("xxx")`，否则 XCUITest 无法通过 accessibility_id 定位！

### SwiftUI 代码侧示例

```swift
// ✅ 正确：每个可操作元素都有 accessibilityIdentifier
TextField("用户名", text: $username)
    .accessibilityIdentifier("tf_username")

SecureField("密码", text: $password)
    .accessibilityIdentifier("tf_password")

Button("登录") { login() }
    .accessibilityIdentifier("btn_login")

Text(errorMessage)
    .accessibilityIdentifier("lbl_error")

// ❌ 错误：没有 accessibilityIdentifier，蓝本无法定位
TextField("用户名", text: $username)
Button("登录") { login() }
```

---

## 选择器格式

### 选择器优先级（从高到低）

| 优先级 | 格式 | 适用场景 |
|--------|------|---------|
| 1 | `accessibility_id:xxx` | **唯一推荐方式**，基于 `.accessibilityIdentifier("xxx")` |
| 2 | `//XCUIElementType*[@name='xxx']` | XCUITest XPath，兜底方案（性能差） |
| 3 | `-ios predicate string:name == 'xxx'` | iOS Predicate 查询（高级场景） |

### ❌ 绝对禁止的选择器

- `//XCUIElementTypeCell[N]` — 索引定位，UI 变化即失效
- 不带属性约束的纯类型选择器（如 `//XCUIElementTypeButton`）
- CSS 选择器（`#id`、`.class`）— 这是 Web 选择器，不适用于原生 iOS
- Android 格式选择器（`resource-id:xxx`、`uia:xxx`）— 不适用于 iOS

### 选择器命名规范

| 前缀 | 用途 | 示例 |
|------|------|------|
| `btn_` | 按钮 | `accessibility_id:btn_login` |
| `tf_` | 输入框（TextField/SecureField） | `accessibility_id:tf_username` |
| `lbl_` | 标签/文本（Text） | `accessibility_id:lbl_error` |
| `list_` | 列表（List） | `accessibility_id:list_todos` |
| `todo_` / `item_` | 列表项 | `accessibility_id:todo_text_0` |
| `img_` | 图片（Image） | `accessibility_id:img_avatar` |
| `toggle_` | 开关/勾选 | `accessibility_id:toggle_done` |

---

## 场景设计规范

### navigate 冷启动（场景间重置）

每个场景开头用 `navigate` 冷启动应用，`value` 填 **Bundle ID**：

```json
{"action": "navigate", "value": "com.example.app", "description": "冷启动应用回初始页面"}
```

引擎会自动执行 `mobile: terminateApp` → `mobile: launchApp`，确保应用从头冷启动。

> **`@Published` 属性会被重置**：SwiftUI 中 `@Published` 变量在 App 被 terminateApp 后自动归零（回到初始值）。
> **`@AppStorage` 不会重置**：持久化到 UserDefaults 的数据在冷启动后仍然保留。

### wait 动作两种格式

| 格式 | 写法 | 说明 |
|------|------|------|
| 简单等待 | `{"action": "wait", "value": "3000"}` | 固定等待毫秒数 |
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 轮询等元素出现 |

### iOS 等待时间建议

| 操作 | 建议等待 |
|------|---------|
| App 冷启动（navigate + wait） | `wait 3000`（3 秒） |
| 登录/页面跳转 | `wait 1000` |
| Sheet/Alert 弹出动画 | `wait 800` |
| 普通按钮操作后 | `wait 500` |

> **标准流程**：每次 `navigate` 冷启动后 → 先 `wait 3000` → 再操作页面元素。

### 每个场景必须包含

1. **navigate 冷启动**：确保从初始状态开始
2. **wait 3000**：等待 App 渲染完成
3. **操作→断言配对**：每个 `click` / `fill` 后必须有 `assert_text` 或 `screenshot` 验证
4. **screenshot 留证**：关键步骤末尾截图

---

## 完整蓝本示例

```json
{
  "app_name": "TestPilot Demo (iOS)",
  "description": "iOS 原生 SwiftUI 待办应用的自动化测试蓝本，覆盖登录（正常/错误）、待办增删改查、退出登录等核心功能。",
  "base_url": "",
  "version": "1.0",
  "platform": "ios",
  "bundle_id": "com.testpilot.demo",
  "udid": "",
  "pages": [
    {
      "url": "",
      "title": "登录 & 首页",
      "description": "应用主流程：登录验证 → 待办管理 → 退出",
      "elements": {
        "标题": "accessibility_id:lbl_title",
        "用户名输入框": "accessibility_id:tf_username",
        "密码输入框": "accessibility_id:tf_password",
        "登录按钮": "accessibility_id:btn_login",
        "错误提示": "accessibility_id:lbl_error",
        "欢迎语": "accessibility_id:lbl_welcome",
        "进度计数": "accessibility_id:lbl_progress",
        "新增按钮": "accessibility_id:btn_add",
        "退出按钮": "accessibility_id:btn_logout"
      },
      "scenarios": [
        {
          "name": "错误密码显示错误提示",
          "steps": [
            {"action": "navigate", "value": "com.testpilot.demo", "description": "重启应用到初始状态"},
            {"action": "wait", "value": "3000", "description": "等待应用启动完成"},
            {"action": "assert_text", "target": "accessibility_id:lbl_title", "expected": "TestPilot Demo", "description": "验证登录页标题"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "wronguser", "description": "输入错误用户名"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "wrongpass", "description": "输入错误密码"},
            {"action": "click", "target": "accessibility_id:btn_login", "description": "点击登录"},
            {"action": "wait", "value": "500"},
            {"action": "assert_text", "target": "accessibility_id:lbl_error", "expected": "用户名或密码错误", "description": "验证显示错误提示"},
            {"action": "screenshot", "value": "错误密码提示截图"}
          ]
        },
        {
          "name": "正常登录进入首页",
          "steps": [
            {"action": "navigate", "value": "com.testpilot.demo", "description": "重启应用"},
            {"action": "wait", "value": "3000"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "admin"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "123456"},
            {"action": "click", "target": "accessibility_id:btn_login"},
            {"action": "wait", "value": "1000"},
            {"action": "assert_text", "target": "accessibility_id:lbl_welcome", "expected": "你好，admin", "description": "验证欢迎语包含用户名"},
            {"action": "screenshot", "value": "登录成功首页截图"}
          ]
        },
        {
          "name": "添加新待办事项",
          "steps": [
            {"action": "navigate", "value": "com.testpilot.demo", "description": "重启应用"},
            {"action": "wait", "value": "3000"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "admin"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "123456"},
            {"action": "click", "target": "accessibility_id:btn_login"},
            {"action": "wait", "value": "1000"},
            {"action": "click", "target": "accessibility_id:btn_add", "description": "点击新增按钮"},
            {"action": "wait", "value": "800", "description": "等待 Sheet 弹出动画"},
            {"action": "fill", "target": "accessibility_id:tf_new_item", "value": "学习XCUITest自动化"},
            {"action": "click", "target": "accessibility_id:btn_save", "description": "点击保存"},
            {"action": "wait", "value": "800", "description": "等待 Sheet 收起动画"},
            {"action": "assert_text", "target": "accessibility_id:todo_text_2", "expected": "学习XCUITest自动化", "description": "验证新增的第三条待办"},
            {"action": "screenshot", "value": "新增待办截图"}
          ]
        },
        {
          "name": "退出登录返回登录页",
          "steps": [
            {"action": "navigate", "value": "com.testpilot.demo", "description": "重启应用"},
            {"action": "wait", "value": "3000"},
            {"action": "fill", "target": "accessibility_id:tf_username", "value": "admin"},
            {"action": "fill", "target": "accessibility_id:tf_password", "value": "123456"},
            {"action": "click", "target": "accessibility_id:btn_login"},
            {"action": "wait", "value": "1000"},
            {"action": "click", "target": "accessibility_id:btn_logout", "description": "点击退出登录"},
            {"action": "wait", "value": "500"},
            {"action": "assert_text", "target": "accessibility_id:lbl_title", "expected": "TestPilot Demo", "description": "验证回到登录页"},
            {"action": "screenshot", "value": "退出登录截图"}
          ]
        }
      ]
    }
  ]
}
```

---

## iOS 蓝本核心注意事项

1. **场景间重置**：`navigate` 的 `value` 填 Bundle ID，引擎自动 `mobile: terminateApp` → `mobile: launchApp`
2. **`@Published` 状态重置**：`@Published` 变量在 terminateApp 后自动重置；`@AppStorage` 不会重置
3. **等待应用启动**：每次 `navigate` 冷启动后**必须** `wait 3000`
4. **Sheet/Alert 动画**：SwiftUI `.sheet()` / `.alert()` 弹出后需 `wait 800` 等动画完成
5. **每个操作必须验证**：`click` 后必须有 `assert_text` 或 `screenshot`
6. **Bug 标记**：已知 Bug 的断言加 `description: "【预期失败-Bug-N】原因说明"`
7. **仅 macOS 可用**：iOS 测试需要 Xcode + 已签名的 WDA，Windows/Linux 不可运行
8. **选择器只用 `accessibility_id:`**：不要用 CSS 选择器、resource-id 或 XPath

---

## 支持的 action

```
navigate / click / fill / select / wait / screenshot
assert_text / assert_visible / hover / scroll
```
