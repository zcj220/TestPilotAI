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

### 关键差异：Flutter TextField 无法用 accessibility_id 定位

Flutter 的 `Semantics(label: 'xxx')` **不会**在 UIAutomator2 中创建 `content-desc='xxx'`。  
用 `adb uiautomator dump` 查看 UI 树，所有 EditText 的 `content-desc` 均为空字符串。

| 控件类型 | 能否用 accessibility_id | 解决方案 |
|---------|------------------------|---------|
| Button（Semantics label已设置）| ✅ 可以 | `accessibility_id:btn_login` |
| Text/Title | ✅ 可以 | `accessibility_id:txt_title` |
| **TextField/TextFormField** | ❌ 不行 | **必须用 `uia:` UiSelector** |

### Flutter TextField 正确选择器

```json
{"action": "fill", "target": "uia:new UiSelector().className(\"android.widget.EditText\").instance(0)", "value": "admin"}
{"action": "fill", "target": "uia:new UiSelector().className(\"android.widget.EditText\").instance(1)", "value": "password"}
```

- `instance(0)` = 页面第1个输入框，`instance(1)` = 第2个，以此类推
- **不要用 XPath index**，Flutter 的节点树层级复杂，XPath 极不稳定

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

`navigate` 值格式为 `包名/Activity路径`，引擎会自动调用 `start_activity` 重启应用。

### Flutter 等待时间建议

| 操作 | 建议等待 |
|------|---------|
| App 首次冷启动 | `wait 3000`（3秒） |
| 场景间 navigate 重启 | `wait 2500` |
| 点击登录等待跳转 | `wait 2000` |
| 普通按钮操作后 | `wait 1000` |
