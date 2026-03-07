# TestPilot AI - 项目编码规范

## 蓝本文件（testpilot.json）管理规则

当你需要为某个被测应用生成或修改测试蓝本时，**必须遵守以下规则**：

1. **只允许存在一个蓝本文件**：每个被测应用目录下只保留一个 `testpilot.json`。
2. **更新而非新建**：若该目录已存在 `testpilot.json`，直接覆盖更新，**不得**创建 `testpilot_v2.json`、`testpilot_new.json`、`testpilot_backup.json` 等任何变体文件。
3. **文件放置位置**：蓝本文件必须放在被测应用的**根目录**，固定命名为 `testpilot.json`。
   - ✅ 正确：`shop-demo/testpilot.json`
   - ❌ 错误：`shop-demo/testpilot_v2.json`、`shop-demo/blueprints/test.json`

这样 TestPilot AI 插件才能自动扫描并选中正确的蓝本。

## 编程完成后必须生成/更新蓝本

**每次完成编程任务后，你必须同时生成或更新被测应用的 `testpilot.json`**。

这是因为你是最了解自己代码的人——你知道每个元素的 ID、class、功能逻辑，你生成的蓝本最精准、覆盖最全面。

### 蓝本生成时机

- ✅ **新建应用**：代码写完后，立即生成完整 `testpilot.json`
- ✅ **修改功能**：新增/修改/删除任何 UI 元素或业务逻辑后，同步更新蓝本对应场景和选择器
- ✅ **修复 Bug 后**：确认代码修复正确，更新蓝本中对应的 expected 断言
- ❌ **不允许跳过**：不得以"稍后再写"为由跳过蓝本生成

### 蓝本质量要求

生成蓝本时，遵守以下规则：

1. **功能全覆盖**：每个可操作的功能（按钮/表单/导航/弹窗）必须有对应场景
2. **使用精确选择器**：直接使用代码中的 `id`（`#login-btn`）或稳定 `class`，不要用 `div:nth-child(3)` 这类脆弱选择器
3. **逐字段断言**：`fill` 之后要有 `assert_text` 或 `screenshot` 验证，不能只操作不验证
4. **边界场景**：包含空表单提交、错误输入、权限不足等异常场景
5. **页面跳转显式化**：每次 `navigate` 必须有对应的 `assert_text` 或 `screenshot` 验证页面已正确加载

### 快速生成模板

```json
{
  "app_name": "你的应用名",
  "base_url": "http://localhost:你的端口",
  "version": "1.0",
  "pages": [
    {
      "url": "/",
      "title": "页面标题",
      "elements": {
        "元素描述": "#实际CSS选择器"
      },
      "scenarios": [
        {
          "name": "功能场景名",
          "steps": [
            {"action": "navigate", "value": "http://localhost:端口"},
            {"action": "fill", "target": "#input-id", "value": "测试值"},
            {"action": "click", "target": "#submit-btn"},
            {"action": "assert_text", "target": "#result", "expected": "预期文本"}
          ]
        }
      ]
    }
  ]
}
```

支持的 action：`navigate` / `click` / `fill` / `select` / `wait` / `screenshot` / `assert_text` / `assert_visible` / `hover` / `scroll`

