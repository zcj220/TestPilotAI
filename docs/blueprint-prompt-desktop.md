# TestPilot AI — Windows桌面应用蓝本生成提示词

> 前置条件：请先阅读 `docs/blueprint-prompt-golden-rules.md` 中的8条黄金规则。

---

## Windows桌面平台专属规则

### 选择器格式（4种）

桌面应用没有CSS选择器，使用 Windows UI Automation 的属性查找：

| 格式 | 说明 | 稳定性 | 示例 |
|------|------|:---:|------|
| `automationid:XXX` | 按AutomationId查找 | ⭐⭐⭐ 最稳定 | `automationid:btnSave` |
| `name:XXX` | 按UI元素Name属性查找 | ⭐⭐ | `name:保存` |
| `class:XXX` | 按ClassName查找 | ⭐ | `class:Button` |
| `point:X,Y` | 按屏幕坐标点击 | 兜底 | `point:500,300` |

**优先级**：automationid > name > class > point

### 支持的 action

```
click / fill / assert_text / screenshot / wait
```

### 蓝本格式

```json
{
  "app_name": "Windows计算器",
  "description": "Windows桌面计算器测试：基本运算、科学计算、历史记录",
  "base_url": "desktop://Calculator",
  "version": "1.0",
  "platform": "desktop",
  "pages": [
    {
      "url": "/",
      "title": "主窗口",
      "elements": {
        "数字1按钮": "name:1",
        "加号按钮": "name:加",
        "等号按钮": "name:等于",
        "结果显示": "automationid:CalculatorResults"
      },
      "scenarios": [
        {
          "name": "基本加法",
          "steps": [
            {"action": "click", "target": "name:1", "description": "点击数字1"},
            {"action": "click", "target": "name:加", "description": "点击加号"},
            {"action": "click", "target": "name:2", "description": "点击数字2"},
            {"action": "click", "target": "name:等于", "description": "点击等号"},
            {"action": "assert_text", "target": "automationid:CalculatorResults", "expected": "3", "description": "验证结果为3"}
          ]
        },
        {
          "name": "连续计算",
          "steps": [
            {"action": "click", "target": "name:清除", "description": "清空计算器"},
            {"action": "click", "target": "name:5"},
            {"action": "click", "target": "name:乘"},
            {"action": "click", "target": "name:6"},
            {"action": "click", "target": "name:等于"},
            {"action": "assert_text", "target": "automationid:CalculatorResults", "expected": "30", "description": "验证5×6=30"}
          ]
        }
      ]
    }
  ]
}
```

### 桌面专属注意事项

1. **应用必须已启动**：蓝本不会自动启动应用，测试前确保目标窗口已打开
2. **窗口标题匹配**：`base_url` 中 `desktop://` 后面跟的是窗口标题关键字
3. **坐标点击是兜底方案**：只在AutomationId和Name都不可用时才用`point:X,Y`
4. **等待窗口加载**：复杂应用启动后可能需要 `{"action": "wait", "value": "3000"}` 等待3秒
5. **多窗口**：如果操作会弹出新窗口（如"另存为"对话框），需要在步骤中处理
6. **查找元素工具**：用 Windows SDK 自带的 `Inspect.exe` 或 `Accessibility Insights` 查看元素的 AutomationId 和 Name
