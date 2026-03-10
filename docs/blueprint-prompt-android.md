# TestPilot AI — Android蓝本生成提示词

> 前置条件：请先阅读 `docs/blueprint-prompt-golden-rules.md` 中的8条黄金规则。

---

## Android平台专属规则

### 两种测试模式

| 模式 | 适用场景 | 选择器格式 |
|------|---------|-----------|
| **手机浏览器测试** | 移动端网页/H5 | CSS选择器（与Web相同） |
| **原生App测试** | APK应用 | resource-id / content-desc / XPath |

### 手机浏览器模式

与Web蓝本基本一致，选择器用CSS：

```json
{
  "app_name": "移动商城H5",
  "description": "手机浏览器访问移动端网页，测试商品浏览、购物车、下单流程",
  "base_url": "http://192.168.1.100:3000",
  "version": "1.0",
  "platform": "android",
  "pages": [
    {
      "url": "/",
      "title": "首页",
      "elements": {
        "搜索框": "#search-input",
        "商品卡片": ".product-card",
        "购物车图标": "#cart-icon"
      },
      "scenarios": [
        {
          "name": "商品浏览",
          "steps": [
            {"action": "navigate", "value": "http://192.168.1.100:3000"},
            {"action": "assert_visible", "target": ".product-card", "description": "验证商品列表可见"},
            {"action": "click", "target": ".product-card:first-child"},
            {"action": "assert_text", "target": "#product-name", "expected": "商品名称"}
          ]
        }
      ]
    }
  ]
}
```

### 原生App模式

选择器使用 Android UI Automator 格式：

```json
{
  "steps": [
    {"action": "click", "target": "resource-id:com.example.app:id/btnLogin", "description": "点击登录按钮"},
    {"action": "fill", "target": "resource-id:com.example.app:id/etUsername", "value": "admin"},
    {"action": "assert_text", "target": "content-desc:欢迎标题", "expected": "欢迎回来"},
    {"action": "click", "target": "text:确定", "description": "点击文字为'确定'的按钮"}
  ]
}
```

### 原生App选择器格式

| 格式 | 说明 | 示例 |
|------|------|------|
| `resource-id:xxx` | 按resource-id查找（最稳定） | `resource-id:com.app:id/btnLogin` |
| `content-desc:xxx` | 按无障碍描述查找 | `content-desc:搜索按钮` |
| `text:xxx` | 按显示文字查找 | `text:确定` |
| `xpath:xxx` | XPath表达式（兜底） | `xpath://android.widget.Button[@text='提交']` |

### 支持的 action

```
navigate / click / fill / select / wait / screenshot
assert_text / assert_visible / hover / scroll
```

### 原生App完整选择器格式

| 格式 | 说明 | 适用场景 |
|------|------|---------|
| `accessibility_id:xxx` | 按无障碍ID查找（**推荐首选**） | Android原生Button/Text/View设置了`contentDescription` |
| `resource-id:xxx` | 按resource-id查找 | 有`android:id`的View |
| `uia:new UiSelector().xxx` | UIAutomator2原生选择器 | 无ID/contentDesc的控件（**Flutter TextField必用**） |
| `text:xxx` | 按显示文字查找 | 兜底方案 |
| `xpath:xxx` | XPath表达式 | 最后手段，性能差且脆弱 |

### Android专属注意事项

1. **base_url用局域网IP**：手机和电脑在同一WiFi下，用电脑的局域网IP（如`192.168.1.100`），不能用`localhost`
2. **等待时间适当加长**：手机渲染比电脑慢，click后建议wait 1-2秒再断言
3. **竖屏为主**：默认竖屏布局，如需横屏测试要额外标注
4. **触摸操作**：scroll用`{"action": "scroll", "value": "down"}`模拟滑动
5. **权限弹窗**：首次启动App可能有权限弹窗，需要在步骤里处理（点"允许"）

---

## Flutter 原生 App（专用规则）⚠️

Flutter App 与普通 Android 原生 App 的元素树结构完全不同，**必须单独处理**。

### Flutter Semantics → Android 无障碍属性映射（核心）

| Flutter 代码 | Android 属性 | 蓝本选择器 |
|---|---|---|
| `Semantics(label: 'xxx', button: true)` | `content-desc="xxx"` | `accessibility_id:xxx` |
| `Semantics(label: 'xxx', textField: true)` 包裹 TextField | `hint="xxx"` | `//android.widget.EditText[@hint='xxx']` |
| `Semantics(label: 'xxx')` + child `Text(yyy)` | `content-desc="xxx\nyyy"` | `accessibility_id:xxx`（部分匹配） |
| `IconButton(tooltip: 'xxx')` | `content-desc="xxx"` | `accessibility_id:xxx` |
| `TextField(hintText: 'xxx')`（无 Semantics 包裹） | `hint="xxx"` | `//android.widget.EditText[@hint='xxx']` |

> ⚠️ **Semantics label 覆盖 hintText**：当 `Semantics(label: 'tf_user', textField: true)` 包裹 `TextField(hintText: '请输入用户名')` 时，Android 端的 `hint="tf_user"`（不是 `请输入用户名`）。

### 选择器优先级（从高到低）

| 优先级 | 格式 | 适用场景 |
|--------|------|---------|
| 1 | `accessibility_id:xxx` | Button（`button: true`）、Text 标签、IconButton tooltip |
| 2 | `//android.widget.EditText[@hint='xxx']` | TextField（`textField: true` 或 hintText） |
| 3 | `//ClassName[@attribute='value']` | 其他精确 XPath 定位 |

### ❌ 绝对禁止的选择器

- `UiSelector().className("xxx").instance(N)` — 依赖元素出现顺序，极其脆弱
- `//xxx[@index='N']` — 同上，索引会因 UI 变化而错位
- 不带任何属性约束的纯 ClassName 选择器

### Flutter 原生 App 蓝本必填字段

```json
{
  "platform": "android",
  "app_package": "com.example.yourapp",
  "app_activity": ".MainActivity",
  "base_url": ""
}
```

### Flutter 蓝本场景设计规范

每个蓝本**必须包含**：
1. **正常流程场景**：完整走通主功能（登录→进首页→关键操作）
2. **Bug 验证场景**：针对已知/预期 Bug，用 `description` 标注 `【预期失败-BugX】`
3. **异常场景**：表单空提交、错误输入等边界情况

```json
{
  "name": "空账号应被拒绝（Bug-1）",
  "steps": [
    {"action": "navigate", "value": "com.example.app/.MainActivity"},
    {"action": "wait", "value": "2500"},
    {"action": "click", "target": "accessibility_id:btn_login"},
    {"action": "assert_text", "target": "accessibility_id:txt_error", "expected": "请输入用户名",
     "description": "【预期失败-Bug-1】空账号应该提示错误，但实际上可以直接登录"}
  ]
}
```

### Flutter 应用启动/重置场景

```json
{"action": "navigate", "value": "com.testpilot.flutter_demo/.MainActivity", "description": "重启 App 回初始页"}
```

`navigate` 值格式为 `包名/.Activity路径`，引擎会 force-stop → 重建 Session → 重启 app。

### wait 动作两种格式

| 格式 | 用法 | 说明 |
|------|------|------|
| 简单等待 | `{"action": "wait", "value": "3000"}` | 固定等待 3 秒 |
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 等元素出现，最多 15 秒 |

> Flutter 每次 `navigate` 重启后的标准流程：先 `wait 3000`，再 `wait target` 等关键元素就绪。

### Flutter 等待时间建议

| 操作 | 建议等待 |
|------|---------|
| App 首次冷启动 | `wait 3000`（3秒） |
| 场景间 navigate 重启 | `wait 3000` + `wait target`（等关键元素） |
| 点击登录等待跳转 | `wait 2000` |
| 普通按钮操作后 | `wait 1000` |
