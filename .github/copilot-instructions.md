# TestPilot AI - 项目编码规范

## 蓝本文件（testpilot.json）管理规则

当你需要为某个被测应用生成或修改测试蓝本时，**必须遵守以下规则**：

1. **蓝本统一存放在 `testpilot/` 文件夹**：每个被测应用目录下创建 `testpilot/` 子目录，蓝本放在里面。
2. **按功能模块拆分蓝本**：不要创建单一的 `testpilot.json`，而是按功能模块拆分成多个蓝本文件。
3. **命名规范**：`模块名.testpilot.json`（如 `login.testpilot.json`、`cart.testpilot.json`）
4. **更新而非新建**：若已存在同名蓝本，直接覆盖更新，**不得**创建 `_v2`、`_new`、`_backup` 等变体。
5. **每个蓝本必须包含 `description` 字段**：50-200字描述本蓝本覆盖的功能范围。
6. **每个蓝本必须包含 `start_command` 字段**：如果应用需要命令行启动（如 `npm start`、`python app.py`），必须填写；纯HTML静态应用留空。

**示例结构：**
```
shop-demo/
  testpilot/
    auth.testpilot.json       ← 登录/注册/权限模块
    dashboard.testpilot.json  ← 仪表盘统计模块
    product.testpilot.json    ← 商品管理CRUD模块
    order.testpilot.json      ← 订单管理模块
```

**优点：**
- 每个模块独立，互不干扰
- 代码变化时只需更新对应模块的蓝本
- 用户可以选择测试全部模块或单个模块

这样 TestPilot AI 插件能自动扫描 `testpilot/` 目录下的所有蓝本并以多选框列表展示。

## 代码变化时自动审视并更新蓝本

**只在以下情况下检查并更新蓝本：**

1. **新增/删除UI元素**：新增或删除按钮/表单/导航/弹窗 → 更新对应模块蓝本，添加/删除场景
2. **修改元素ID/class**：修改了 `id` 或 `class` → 更新蓝本中的选择器
3. **修改文本内容**：修改了按钮文字、提示信息、错误提示等 → 更新蓝本中的 `assert_text` 断言
4. **修改业务逻辑**：修改表单验证/计算逻辑/跳转流程 → 更新蓝本中的断言和预期结果
5. **修复Bug**：修复了Bug → 更新蓝本中的 `expected` 断言，确保能检测到该Bug
6. **修改URL/路由/端口**：修改了应用端口或路由 → 更新蓝本中的 `base_url` 和 `start_command`

### 更新流程

```
修改代码 → 判断：是否属于上述6种情况？
         → 是 → 找到对应的 xxx.testpilot.json → 更新
         → 否 → 跳过
```

**示例：**
- 修改了登录页的密码输入框 `id` 从 `#pwd` 改为 `#password` 
  → 立即打开 `auth.testpilot.json`
  → 找到所有使用 `#pwd` 的步骤
  → 改为 `#password`
  → 保存

### 蓝本生成时机

- ✅ **新建应用**：代码写完后，按功能模块生成多个蓝本文件
- ✅ **修改功能**：新增/修改/删除任何 UI 元素或业务逻辑后，**立即**更新对应模块的蓝本
- ✅ **修复 Bug 后**：确认代码修复正确，**立即**更新蓝本中对应的 expected 断言
- ❌ **不允许跳过**：不得以"稍后再写"为由跳过蓝本更新

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

