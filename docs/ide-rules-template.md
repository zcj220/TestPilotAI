# TestPilot AI — 编程AI蓝本自动生成规则

> 本文件由 TestPilot AI 插件自动注入，指导编程AI在开发过程中自动生成和维护测试蓝本。
> 你可以根据项目需求自由修改本文件内容。

---

## ⚠️ 最重要：每个项目必须有自己的蓝本

- **每个项目目录**下必须有独立的 `testpilot.json`（或 `testpilot/` 目录）
- 不同项目绝对不能共用蓝本——即使功能相似，选择器和路由也不同
- 不同平台（Web/小程序/Android/桌面）必须各自独立蓝本，`platform` 字段不同
- 当项目中**不存在** `testpilot.json` 或 `testpilot/` 目录时，你在完成功能开发后**必须**自动生成蓝本文件

---

## 一、蓝本自动生成（最重要）

### 生成时机

| 时机 | 动作 |
|------|------|
| 新项目创建完成 | 生成完整蓝本，覆盖所有已实现功能 |
| 新增一个完整功能模块 | 在蓝本中追加对应场景 |
| 项目初始蓝本不存在 | 扫描现有代码，生成功能全覆盖的蓝本 |

### 生成规则

1. 蓝本文件固定命名 `testpilot.json`，放在**当前项目根目录**或 `testpilot/` 子目录下
2. 必须覆盖项目的**所有用户可交互功能**，不允许遗漏
3. 每个功能模块对应一个 `page`，每个用户场景对应一个 `scenario`
4. 如果项目功能较多，按功能模块拆分为多个蓝本文件放在 `testpilot/` 目录下：
   - 命名格式：`testpilot/功能模块名.testpilot.json`（用英文）
   - 拆分判断：页面≤3个用一个 testpilot.json；页面>3个按功能模块拆分
   - 由你根据项目实际代码结构自主决定如何拆分和命名
5. 每个蓝本必须包含 `app_name`、`description`、`platform`、`base_url` 字段

### 蓝本管理规则（极其重要！）

- **每个被测应用目录下只允许一个 `testpilot.json`**（或 `testpilot/` 目录下按模块拆分）
- **若已存在 `testpilot.json`，直接覆盖更新，禁止创建 `_v2`/`_new`/`_backup` 等变体**
- 功能较多时，按功能模块拆分到 `testpilot/` 目录下：
  - 如 `testpilot/auth.testpilot.json`、`testpilot/dashboard.testpilot.json`
  - 更新某模块时**只替换该模块文件**，不影响其他模块
  - 不要在 `testpilot/` 目录下堆积多个版本（如 auth_v1、auth_v2）
- 拆分判断标准：页面≤3个用单个 `testpilot.json`；页面>3个按功能模块拆分到 `testpilot/`
- 蓝本文件必须放在被测应用的根目录，不要放到其他项目目录下

---

## 二、测试设计黄金规则（必须严格遵守）

### 核心哲学：绝对正向验证
- 蓝本 = 假设一切功能完全正确的测试路线图
- 写出"正确时应该是什么样"的断言，Bug由引擎自动发现（实际≠预期）
- ❌ 绝对禁止：看到代码有Bug就针对性写用例确认
- ✅ 正确做法：按功能正常逻辑写断言，Bug自然会暴露出来

### 核心哲学：穷举每条路径
- 代码是唯一真相：代码里实现了什么就测什么，没实现的不测
- 穷举 = 每条路径的每种合理输入变体都要试：
  - 搜索 → 精确匹配、部分匹配、大写、小写、空搜索
  - 登录 → 正确账号、错误密码、空账号、空密码
  - 数值输入 → 正常值、边界值、零、负数

### 场景自包含原则（极其重要）
- 每个 scenario 必须能独立运行，不依赖前一个场景的状态
- 每个场景的第一步必须是 `navigate` 到起始页面
- 引擎会在每个场景开始前自动清除 cookie/storage，确保干净状态
- 禁止场景间传递状态（如场景1登录后场景2直接操作已登录页面）
- 正确写法：
  ```
  场景1： navigate→填用户名→填密码→点登录→断言成功
  场景2： navigate→填用户名→填错密码→点登录→断言失败
  ```
- 错误写法（禁止）：
  ```
  场景1： navigate→登录成功
  场景2： 点退出→填错密码→登录  ← 依赖场景1已登录，禁止！
  ```

### 操作→断言配对
- 每一个操作后面必须跟断言验证结果
- 错误：click登录按钮 → 结束（没验证是否登录成功）
- 正确：click登录按钮 → assert_text验证"欢迎回来"
- 没有断言的操作等于没测

### 功能全覆盖
- 先通读全部源代码，列出所有功能点
- 每个按钮、表单、Tab、弹窗、下拉框必须至少有一个测试场景
- 自检：数一数代码里有多少个可操作元素，蓝本是否每个都覆盖到了

### 选择器规范
- 使用代码中的真实 id（如 #login-btn）或稳定 class
- 禁止用 div:nth-child(3) 这类脆弱选择器
- 必须先阅读源代码确认选择器存在

### 截图策略（省钱省时）
- 每个蓝本模块的第1个场景末尾加1张 screenshot，其余场景不加
- 断言失败时引擎会自动截图留证，蓝本不用额外写
- ❌ 禁止每个场景末尾都加 screenshot

---

## 三、蓝本基本结构

```json
{
  "app_name": "应用名称",
  "description": "应用功能的完整描述（50-200字）",
  "base_url": "http://localhost:3000",
  "platform": "web",
  "start_command": "npm start",
  "start_cwd": ".",
  "pages": [
    {
      "url": "/",
      "name": "首页",
      "scenarios": [
        {
          "name": "场景名称",
          "description": "测试目标",
          "steps": [
            {"action": "navigate", "value": "/", "description": "打开首页"},
            {"action": "fill", "target": "#username", "value": "testuser", "description": "在用户名输入框输入"},
            {"action": "click", "target": "#loginBtn", "description": "点击登录按钮"},
            {"action": "assert_text", "expected": "欢迎", "description": "验证登录成功显示欢迎信息"},
            {"action": "screenshot", "description": "登录成功后的页面"}
          ]
        }
      ]
    }
  ]
}
```

### platform 取值

| 值 | 适用场景 |
|----|---------|
| `web` | 网页应用（React/Vue/Angular/纯HTML） |
| `desktop` | Windows桌面应用（需额外填 `window_title`） |
| `android` | Android应用（需额外填 `app_package`、`app_activity`） |
| `ios` | iOS应用（需额外填 `bundle_id`） |
| `miniprogram` | 微信小程序（`base_url` 格式为 `miniprogram://项目路径`） |

### 步骤动作

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `select` | `target`, `value`, `description` | 下拉框选择（`<select>`元素用select不用fill） |
| `screenshot` | `description` | 截图 |
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `wait` | `description` | 等待（可用 `value` 指定毫秒） |
| `navigate` | `value`(URL), `description` | 页面跳转 |

### target 写法

- **Web/小程序**：CSS选择器，如 `#loginBtn`、`.submit-btn`、`input[name="email"]`
- **桌面应用**：`name:屏幕上可见的原文`，如 `name:Login`、`name:确定`
  - ⚠️ **禁止**在 `name:` 后加中文后缀（按钮/输入框/列表项等）
- **Android/iOS**：`accessibility_id:xxx` 或 `id:xxx`

### description 最佳实践

每个步骤的 `description` 应包含：
1. **位置**：上方/下方/左侧/右侧
2. **预期变化**：点击后页面会发生什么

```
✅ "点击提交按钮，点击后表单数据提交到后端，页面显示'提交成功'提示"
❌ "点击按钮"
```

---

## 四、蓝本增量维护（日常开发）

当项目已有蓝本文件时，以下代码变更**必须**同步更新蓝本：

| # | 触发条件 | 蓝本更新动作 |
|---|---------|------------|
| 1 | 新增/删除 UI 元素 | 添加/删除对应场景和步骤 |
| 2 | 修改元素 id/class/选择器 | 更新蓝本中所有用到该选择器的 `target` |
| 3 | 修改文本内容（按钮文字/提示/错误信息） | 更新 `assert_text` 的 `expected` |
| 4 | 修改业务逻辑（表单验证/跳转/计算） | 更新断言和预期结果 |
| 5 | 修复 Bug | 更新蓝本中对应断言 |
| 6 | 修改应用配置（URL/端口/路由） | 更新 `base_url` / `start_command` |

**已有蓝本时，只修改/新增变更涉及的场景，不要重写整个文件。**

---

## 五、蓝本自检清单

生成或修改蓝本后，逐项检查：

- [ ] 所有用户可交互功能都有对应场景
- [ ] `target` 选择器与实际代码中的 id/class 一致
- [ ] `expected` 是界面上实际会显示的文字（不是描述性文字）
- [ ] 页面切换后有 `wait` 步骤
- [ ] 每个场景自包含（第一步是navigate，不依赖前一个场景的状态）
- [ ] `<select>` 下拉框用 `select` 动作，不用 `fill`
- [ ] `platform` 字段正确
- [ ] `base_url` 和 `start_command` 填写正确

---

## 六、常见错误（经验教训）

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 对 `<select>` 元素用 `fill` | 引擎报错"Element is not an input" | 用 `select` 动作 |
| 场景依赖前一个场景的登录状态 | 引擎每场景清cookie，后续场景全部失败 | 每个场景独立登录 |
| 两个项目共用一个蓝本 | 选择器/路由不同导致全部失败 | 每个项目独立蓝本 |
| 蓝本里写死了注册的用户名 | 第二次测试时"用户已存在" | 用带时间戳的用户名或每次清数据 |
| 没有断言就结束场景 | 什么Bug都检测不到 | 每个操作后跟assert验证 |
| 小程序用 `#id` 选择器 | WXML不支持id选择器，全部找不到 | 用 `input.form-input[placeholder*='用户名']` |
| 小程序用 `button:contains('登录')` | 小程序不支持:contains伪类 | 用 `button.btn-primary` 或带bindtap的class |
| 小程序picker用click操作 | picker是原生组件，不能直接click | 用 `select` 动作操作picker |
| 小程序wx.showModal用click确认 | Modal是原生弹窗，不在DOM中 | 蓝本无法操作原生弹窗，需改用页面内确认 |

---

## 七、微信小程序蓝本专属规则（platform=miniprogram时必读）

### 选择器铁律（最重要！与Web完全不同！）

小程序WXML**不是HTML**，以下Web选择器在小程序中全部无效：
- ❌ `#login-btn`（WXML不支持id选择器）
- ❌ `button:contains('登录')`（不支持:contains伪类）
- ❌ `input[type="text"]`（WXML的input没有type attribute）
- ❌ `div > span`（WXML里是view/text，不是div/span）

**正确的小程序选择器写法**（按优先级排列）：
1. **用placeholder区分input**：`input[placeholder*='用户名']`、`input[placeholder*='密码']`
2. **用class区分按钮**：`button.btn-primary`（配合bindtap确认是哪个按钮）
3. **用class组合定位**：`.card .form-input`（结合父容器缩小范围）
4. **用data-属性**：`view[data-tab='profit']`（小程序常用data-xxx传参）
5. **用文本内容辅助**：在description中描述元素文字，帮助引擎AI定位

### 小程序特有组件的操作方式

| 组件 | 错误写法 | 正确写法 |
|------|---------|---------|
| `<picker>` | click然后选选项 | `{"action": "select", "target": "picker.type-picker", "value": "收入"}` |
| `<switch>` | click | `{"action": "click", "target": "switch.my-switch"}` |
| `wx.showModal` | 无法操作（原生弹窗不在DOM中） | 蓝本里跳过modal确认步骤，或建议开发者改用页面内弹窗 |
| `wx.showToast` | assert_text | 短暂显示后消失，用wait等待后再断言页面变化 |
| TabBar | click底部tab | `{"action": "navigate", "value": "/pages/reports/reports"}` 直接导航 |

### 小程序蓝本结构模板

```json
{
  "app_name": "小程序名称",
  "description": "功能说明",
  "base_url": "miniprogram://D:/projects/项目绝对路径",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "pages/login/login",
      "name": "登录页",
      "scenarios": [
        {
          "name": "正确登录",
          "steps": [
            {"action": "navigate", "value": "pages/login/login", "description": "打开登录页"},
            {"action": "fill", "target": "input[placeholder*='用户名']", "value": "admin", "description": "输入用户名"},
            {"action": "fill", "target": "input[placeholder*='密码']", "value": "admin123", "description": "输入密码"},
            {"action": "click", "target": "button.btn-primary", "description": "点击登录按钮，按钮文字为'登录'"},
            {"action": "wait", "value": "2000", "description": "等待登录跳转"},
            {"action": "assert_text", "expected": "记账台", "description": "验证跳转到记账台页面"}
          ]
        }
      ]
    }
  ]
}
```

### 小程序蓝本自检追加项

- [ ] 所有选择器都不含 `#id`（WXML不支持）
- [ ] 所有选择器都不含 `:contains()`（不支持）
- [ ] input用 `placeholder` 属性区分，不用 `id` 或 `name`
- [ ] picker用 `select` 动作，不用 `click`
- [ ] `base_url` 是 `miniprogram://绝对路径`（不是相对路径）
- [ ] TabBar页面跳转用 `navigate` 动作（不能click TabBar）
- [ ] 没有操作 `wx.showModal` / `wx.showToast` 等原生弹窗
