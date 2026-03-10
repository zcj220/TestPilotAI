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

**只在以下6种情况下检查并更新蓝本（适用于所有平台：Web/小程序/手机/桌面）：**

1. **新增/删除UI元素**：新增或删除按钮/表单/导航/弹窗/菜单 → 更新对应模块蓝本，添加/删除场景
2. **修改元素ID/class/选择器**：修改了 `id`、`class`、组件名等定位标识 → 更新蓝本中的选择器
3. **修改文本内容**：修改了按钮文字、提示信息、错误提示、标签文字等 → 更新蓝本中的 `assert_text` 断言
4. **修改业务逻辑**：修改表单验证/计算逻辑/跳转流程/数据绑定 → 更新蓝本中的断言和预期结果
5. **修复Bug**：修复了Bug → 更新蓝本中的 `expected` 断言，确保能检测到该Bug
6. **修改应用配置**：修改了URL/端口/路由/页面路径/窗口标题/权限声明/启动入口/启动命令 → 更新蓝本中的 `base_url`、`start_command`、`app_package`、`app_activity` 等字段

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

## 小程序蓝本编写规范

小程序蓝本与Web蓝本的关键区别：

1. **`platform` 字段必须设为 `"miniprogram"`**
2. **`base_url` 格式**：`miniprogram://绝对路径`（如 `miniprogram://D:/projects/my-app`）
3. **引擎会自动处理环境准备**：蓝本不需要写"重启小程序"步骤，引擎会自动执行 `cli close → cli open → cli auto --auto-port 9420`
4. **页面URL使用小程序路径格式**：`/pages/index/index`（不是HTTP URL）
5. **选择器与小程序一致**：`.class-name`、`#id`、`view`、`.parent .child`

### 小程序蓝本模板

```json
{
  "app_name": "你的小程序名",
  "description": "功能描述",
  "base_url": "miniprogram://D:/projects/你的小程序路径",
  "version": "1.0",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "/pages/index/index",
      "title": "首页",
      "description": "首页功能描述",
      "scenarios": [
        {
          "title": "场景名",
          "steps": [
            {"action": "navigate", "value": "/pages/index/index"},
            {"action": "click", "target": ".product-item"},
            {"action": "assert_text", "target": ".price", "expected": "¥"},
            {"action": "screenshot", "value": "场景截图"}
          ]
        }
      ]
    }
  ]
}
```

### 小程序蓝本注意事项

- **不需要写启动/重启步骤**：引擎自动处理（cli close/open/auto）
- **不需要指定端口**：引擎固定使用9420端口
- **导航用页面路径**：`/pages/detail/detail?id=1`，不是HTTP URL
- **场景间重置**：引擎会自动用 `wx.reLaunch` 回首页，蓝本无需关心
- **截图**：每个关键场景末尾加 `screenshot` 步骤留证

## Android/Flutter 蓝本编写规范

### 基本字段

1. **`platform` 字段必须设为 `"android"`**（Flutter 应用也是 `"android"`，不是 `"flutter"`）
2. **必须包含 `app_package` 和 `app_activity`**：如 `"com.testpilot.flutter_demo"` / `".MainActivity"`
3. **`base_url` 留空**：原生应用不需要 URL
4. **页面 `url` 留空**：原生应用没有 HTTP URL，页面区分靠 `title`
5. **引擎会自动检测设备连接**：未连接会提示用户
6. **Windows下不支持iOS**（需macOS环境）

### Flutter Semantics → Android 无障碍属性映射（核心规则）

Flutter 的 `Semantics` 组件在 Android 端映射为无障碍属性。**选择器必须基于这些映射规则**：

| Flutter Semantics 用法 | Android 无障碍属性 | 蓝本选择器格式 |
|---|---|---|
| `Semantics(label: 'xxx', button: true)` | `content-desc="xxx"` | `accessibility_id:xxx` |
| `Semantics(label: 'xxx', textField: true)` 包裹 TextField | `hint="xxx"` | `//android.widget.EditText[@hint='xxx']` |
| `Semantics(label: 'xxx')` 普通标签（无 button/textField） + child 有文本 | `content-desc="xxx\n子文本"` | `accessibility_id:xxx`（部分匹配） |
| `IconButton(tooltip: 'xxx')` | `content-desc="xxx"` | `accessibility_id:xxx` |
| `TextField(decoration: InputDecoration(hintText: 'xxx'))` | `hint="xxx"` | `//android.widget.EditText[@hint='xxx']` |

### 选择器优先级（从高到低）

1. **`accessibility_id:xxx`** — 用于 `button:true` 的按钮、普通 label 元素、tooltip 的 IconButton
2. **`//android.widget.EditText[@hint='xxx']`** — 用于文本输入框（textField 标记或 hintText）
3. **`//ClassName[@attribute='value']`** — 用于其他精确 XPath 定位

### 绝对禁止的选择器

- ❌ `UiSelector().className("xxx").instance(N)` — 依赖元素出现顺序，极其脆弱
- ❌ `//xxx[@index='N']` — 同上，索引会因 UI 变化而错位
- ❌ `div:nth-child(N)` — 这是 Web CSS 选择器，不适用于原生 Android
- ❌ 不带任何属性约束的纯 ClassName 选择器

### Android 蓝本模板

```json
{
  "app_name": "你的应用名",
  "description": "50-200字功能描述",
  "base_url": "",
  "version": "1.0",
  "platform": "android",
  "app_package": "com.example.app",
  "app_activity": ".MainActivity",
  "pages": [
    {
      "url": "",
      "title": "页面标题",
      "elements": {
        "用户名输入框": "//android.widget.EditText[@hint='tf_username']",
        "登录按钮": "accessibility_id:btn_login",
        "错误提示": "accessibility_id:txt_error"
      },
      "scenarios": [
        {
          "name": "场景名",
          "steps": [
            {"action": "wait", "value": "3000", "description": "等待应用启动"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='tf_username']", "value": "admin"},
            {"action": "click", "target": "accessibility_id:btn_login"},
            {"action": "wait", "value": "1000"},
            {"action": "assert_text", "target": "accessibility_id:txt_result", "expected": "预期文本"},
            {"action": "screenshot", "value": "场景截图名"}
          ]
        }
      ]
    }
  ]
}
```

### Android/Flutter 蓝本注意事项

- **场景间重置**：用 `navigate` + Activity 路径重启应用（如 `com.testpilot.flutter_demo/.MainActivity`），引擎会 force-stop → 重建 Session → 重启 app
- **Flutter 动画等待**：Flutter 页面跳转后需要 `wait` 2-3秒（setState/pushReplacementNamed 会导致 U2 短暂不响应）
- **等待元素就绪**：跳转后用 `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` 等待关键元素出现
- **每个操作必须验证**：`click` 后必须有 `assert_text` 或 `screenshot`
- **Bug 标记**：已知 Bug 的断言加 `description: "【预期失败-Bug-N】原因说明"`
- **Semantics 优先级**：`Semantics(label: 'tf_user', textField: true)` 包裹 `TextField(hintText: '请输入')` 时，hint 是 `tf_user`（Semantics label 覆盖 hintText）

### wait 动作两种格式

| 格式 | 用法 | 说明 |
|------|------|------|
| 简单等待 | `{"action": "wait", "value": "3000"}` | 固定等待毫秒数 |
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 轮询等元素出现 |

> Flutter 每次 `navigate` 重启后的标准流程：先 `wait 3000`，再 `wait target` 等关键元素就绪。
