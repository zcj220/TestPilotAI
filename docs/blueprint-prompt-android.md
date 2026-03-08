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

### Android专属注意事项

1. **base_url用局域网IP**：手机和电脑在同一WiFi下，用电脑的局域网IP（如`192.168.1.100`），不能用`localhost`
2. **等待时间适当加长**：手机渲染比电脑慢，click后建议wait 1-2秒再断言
3. **竖屏为主**：默认竖屏布局，如需横屏测试要额外标注
4. **触摸操作**：scroll用`{"action": "scroll", "value": "down"}`模拟滑动
5. **权限弹窗**：首次启动App可能有权限弹窗，需要在步骤里处理（点"允许"）
