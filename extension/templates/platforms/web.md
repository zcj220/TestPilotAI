<!-- TestPilot-Template-Version: 11 -->
# Web 平台蓝本规则（platform = "web"�?

> 本文件定�?Web 应用（React/Vue/Angular/纯HTML）蓝本的完整规则�?
> 生成蓝本�?*必须**通读本文件，不得跳过任何章节�?

---

## 零、生成蓝本前必须先通读源代码（强制执行�?

**蓝本的唯一依据是代码，不是猜测，不是常识，不是用户描述�?*

在写任何 JSON 之前，必须按顺序完成�?

0. **先读 `testpilot/CHANGELOG.md`（如果存在）** �?了解当前已覆盖的功能和尚未测试的模块，避免重复写或漏写；如果不存在则跳过
1. **读入�?路由文件** �?了解页面结构和路由配置（�?`App.js`、`router/index.js`、`index.html`�?
2. **读每个页面的模板/HTML** �?找出所有可操作元素，记录真实的 `id`、`class`、`name` 属�?
3. **记录元素的真实选择�?* �?只用代码中实际存在的 `#id` 或稳�?`.class`，禁止猜�?
4. **读业务逻辑** �?确认每个操作的真实结果（跳转哪里、显示什么文字、调用什�?API�?
5. **确认提示方式** �?成功/失败提示是短�?Toast（不可断言）还是持久化 DOM 元素（可断言�?
6. **列出已实现功�?* �?代码里有什么就测什么，未实现的功能不写蓝本

**禁止跳过代码阅读直接生成蓝本。凭想象写的选择器和断言几乎必然失败�?*

---

## 一、必填字�?

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"web"` | `"web"` |
| `base_url` | 应用访问地址 | `"http://localhost:3000"` |
| `start_command` | 启动命令（纯HTML留空�?| `"npm run dev"` |
| `start_cwd` | 启动目录�?*必须填被测项目的绝对路径** | `"D:\\projects\\my-app"` |
| `app_name` | 应用名称 | `"电商管理系统"` |
| `description` | 50-200字功能描�?| |

### 🚨 start_cwd 必须填绝对路径（最常见的致命错误）

**`start_cwd` 绝对禁止�?`"."`**，引擎用相对路径 `.` 会解析为引擎自身的工作目录，导致在错误的地方执行 `npm run dev`，进�?`exit code 1` 退出，所有测试步骤全�?`ERR_CONNECTION_REFUSED`�?

| �?错误写法（必然失败） | �?正确写法 |
|----------------------|----------|
| `"start_cwd": "."` | `"start_cwd": "D:\\projects\\account_book"` |
| `"start_cwd": "./my-app"` | `"start_cwd": "/home/user/projects/my-app"` |

**如何获取绝对路径**：在被测项目根目录运�?`pwd`（Mac/Linux）或 `Get-Location`（Windows PowerShell），复制输出结果�?

### 🚨 启动前置条件检查（蓝本生成前必做）

生成蓝本前必须确认以下条件，否则 `start_command` 会立即退出：

1. **依赖已安�?*：确认被测项目的 `node_modules` 存在；若不存在，先在项目目录运行 `npm install`
2. **端口未占�?*：确�?`base_url` 对应的端口（�?5173�?000）没有其他进程在监听
3. **环境变量就绪**：项目如�?`.env` 文件，确认必填的环境变量已配�?
4. **启动命令可独立运�?*：在被测项目目录下手动运行一�?`start_command`，确认能成功启动，再写入蓝本

> ⚠️ 若应用启动失败（`exit code != 0`），引擎会等�?`startup_timeout` 秒后继续测试，所有步骤将�?`ERR_CONNECTION_REFUSED` 全部失败�?*启动失败必须先手动排查，不要�?AI 自动修复�?*

### 反面禁止

- �?`base_url` 不能留空（Web 必须有地址�?
- �?不要�?`app_package`、`app_activity`、`bundle_id`（那是手机平台的字段�?
- �?`start_command` 不要�?`python manage.py runserver 0.0.0.0:8000`，应该填 `python manage.py runserver`（不绑外网）
- �?`start_cwd` 不能�?`"."`，必须填被测项目�?*绝对路径**

---

## 二、封闭式动作表（只允许以下动作，禁止使用不在此列表中的动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(URL), `description` | 页面跳转（场景第一步必须是 navigate�?|
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本（用�?input/textarea�?|
| `select` | `target`, `value`, `description` | 下拉框选择（用�?`<select>` 元素，不要用 fill�?|
| `wait` | `description` | 等待（`value` 指定毫秒，或 `target` 等待元素出现�?|
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动�?

- �?`reset_state`（引擎自动处理，蓝本不要写）
- �?`navigate_to`（这是小程序专用动作�?
- �?`evaluate`、`call_method`、`page_query`（这些是小程序专用动作）

---

## 三、选择器规�?

### 🚨 选择器三步验证（强制执行，每�?target 都必须做�?

写任何一�?`target` 选择器之前，必须完成以下三步�?*缺一不可**�?

1. **定位源码**：找到该元素所在的源文件，定位到具体的 JSX/HTML �?
2. **复制属�?*：从代码中复制元素的真实 `id`、`class`、`name`、`type`、`title`、`placeholder` 等属性（**禁止凭记忆或猜测**�?
3. **唯一性验�?*：在同一页面源码中搜索该选择器，确认只匹配一个元�?

**不做三步验证就写的选择�?= 必然出错。这是选择器失败的第一大原因�?*

### 优先级（从高到低�?

1. **`#id`** �?最稳定，如 `#login-btn`、`#username`
2. **`[name="xxx"]`** �?表单元素，如 `input[name="email"]`
3. **`.class`** �?稳定 class，如 `.submit-btn`、`.nav-link`
4. **组合选择�?* �?缩小范围，如 `.form-login #username`

### 🚨 Tailwind / 原子�?CSS 类陷阱（必读！）

Tailwind CSS 的工具类（如 `w-14`、`h-14`、`text-white`、`rounded-full`、`flex`、`bg-blue-600`�?*不是语义化标识符**，它们只描述样式，不代表元素身份�?

- `button.w-14.h-14` 可能匹配页面上多个不同功能的按钮
- `div.flex.items-center` 可能匹配几十个元�?
- 调整样式后（�?`w-14` 改成 `w-12`），选择器立刻失�?

| �?错误（用 Tailwind 类做选择器） | �?正确（用语义属性） |
|---|---|
| `button.w-14.h-14` | 读源码发�?`title="新增"` �?`button[title='新增']` |
| `button.bg-blue-600.text-white` | 读源码发�?`onClick={handleSave}` 且文字是"保存" �?用父容器组合定位 |
| `div.flex.items-center.gap-2` | 无语�?�?�?`.fixed.bottom-6 button[title='新增']` 上下文组�?|

**Tailwind 项目选择器策�?*�?
1. 优先�?`id`、`name`、`title`、`placeholder`、`data-testid`、`type` 等语义属�?
2. 找只在该元素上出现的**语义�?class**（如 `.submit-btn`、`.nav-link`，不�?`.flex`、`.mt-4`�?
3. 如果元素只有 Tailwind 类，用上下文组合：如 `.fixed.bottom-6 button[title='新增']`
4. 最后手段：建议开发者添�?`data-testid` �?`id`

### 🚨 提交按钮陷阱：不要猜 type=submit（必读！�?

React/Vue 中很多表单不用原�?`<form>` + `<button type="submit">`，而是�?`<button onClick={handleSave}>` 处理提交�?*不读源码就写 `button[type='submit']` 是最常见的选择器错误之一�?*

| �?错误（猜测） | �?正确（读源码确认�?|
|---|---|
| `button[type='submit']` | 源码�?`<button onClick={handleSave}>保存</button>`（没�?type），用包含它的容�?+ 文字组合定位 |
| `button[type='submit']:nth-of-type(2)` | 源码是两�?button�?取消" + "保存修改"），�?`.border-t button:last-child` 或其他唯一特征 |

**强制要求**：对每个提交/保存按钮，必须打开 JSX/模板源码确认�?`type="submit"` 还是 `onClick`。如果没�?`type="submit"`，绝对不能写 `button[type='submit']`�?

### 🚨 React/Vue/Angular 组件名陷阱（必读！）

**JSX/模板中的自定义组件名（如 `<Select>`、`<Modal>`、`<Dropdown>`、`<DatePicker>`）不会出现在渲染后的 DOM class 中！**

AI 常犯的错误：看到代码�?`<Select>` 组件就写 `div[class*='Select'] button`，但实际渲染后根节点可能�?`<div class="relative">`，DOM 中根本没�?"Select" 这个 class，选择器必然超时失败�?

| �?错误（基于组件名猜测�?| �?正确（基于实际渲�?DOM�?|
|---|---|
| `div[class*='Select'] button` | 打开 Select.tsx 源码，发现根节点�?`<div class="relative">`，trigger �?`<button type="button">` �?�?`div.relative > button[type='button']` |
| `div[class*='Modal']` | 打开 Modal.tsx，发现渲�?`<div class="fixed inset-0">` �?�?`.fixed.inset-0` |
| `div[class*='DatePicker']` | 打开 DatePicker.tsx，发现渲�?`<div class="date-picker">` �?�?`.date-picker` |

**强制要求**：对每个 `target`，必须打开该组件的源文件，查看�?`return (...)` 中根元素实际渲染�?class/id，然后用实际�?class 写选择器�?*绝对禁止用组件名猜测 CSS class�?*

### 绝对禁止的选择�?

- �?`div[class*='ComponentName']` �?组件名不等于 CSS class，见上方陷阱说明
- �?`div:nth-child(N)` �?脆弱，DOM 结构变化即失�?
- �?`body > div > div > form > input` �?层级太深，随改随�?
- �?`accessibility_id:xxx` �?这是手机平台选择器，Web 不支�?
- �?`name:xxx` �?这是桌面平台选择器，Web 不支�?
- �?没有任何属性约束的标签选择器（如单独的 `div`、`span`、`button`�?

### 🚨 绝对禁止：`:contains()` 伪类（会导致 SyntaxError�?

**`:contains()` �?jQuery 专有语法，现代浏览器 CSS 引擎�?Playwright 均不支持�?* 凡是包含 `:contains()` 的选择器，引擎会立即抛�?`SyntaxError: Failed to execute` 并跳过步骤，整个场景连锁失败�?

| �?禁止（SyntaxError�?| �?替代方案 |
|----------------------|------------|
| `button:contains('保存')` | `button[type='submit']` �?`.save-btn` |
| `button:contains('快速记�?)` | 读源码找该按钮的真实 class |
| `span:contains('文字')` | `.specific-class` �?`[data-testid='xxx']` |
| `button:has(> span:contains('记一�?))` | 读源码，直接用按钮的 class |
| `div:has(h3:contains('生活账本'))` | 读源码，用父容器或按钮的真实 class |

**唯一正确做法**：读源码，用代码中真实存在的 `#id`、`.class`、`[attribute]` 属性定位元素。如果元素没有稳定的 id/class，查看其 `type`、`title`、`placeholder` 等属性，或建议开发者添�?`data-testid`�?
### 🚨 绝对禁止：Tailwind 小数类出现在 `target` 中（会导致 SyntaxError 崩溃）

Tailwind 的小数工具类（如 `gap-0.5`、`translate-y-0.5`、`space-x-2.5`、`inset-0.5`）在 CSS 选择器中包含 `.5`，会被 Playwright 的 CSS 解析器识别为无效语法，**立即抛出 `SyntaxError: Unexpected token ".5"` 并跳过整个场景**，导致后续所有步骤连锁失败。

| ❌ 禁止（必定 SyntaxError） | ✅ 替代方案 |
|---|---|
| `div.gap-0.5` | 打开源码，找该元素的 `id`、语义 class 或 `title` 属性 |
| `header div.flex-col.items-end.gap-0.5 button` | 读源码找按钮自身的 `title` 属性，如 `button[title='财务报表']` |
| `div.translate-y-0.5` | 找父容器或子元素的稳定语义属性 |

> 铁律：含小数点的 Tailwind 类（数字中间有点，如 `0.5`、`1.5`、`2.5`）**永远不能出现在 `target` 里**。

### 🚨 绝对禁止：猜测子元素 HTML 标签（写 :first-child 前必须确认）

写 `> div:first-child`、`> li:last-child` 等子元素选择器前，**必须打开源码确认子元素的实际 HTML 标签**。看到父容器是 flex 布局，子元素可能是 `button`、`a`、`li` 等，**不一定是 `div`**。

| ❌ 错误（猜测标签） | ✅ 正确（读源码确认） |
|---|---|
| `div.flex > div:first-child` | 打开源码发现子元素是 `<button>` → `div.flex > button:first-child` |
| `ul.list > div:nth-child(2)` | 打开源码发现子元素是 `<li>` → `ul.list > li:nth-child(2)` |

### 🚨 绝对禁止：表单内多个 button 时用模糊选择器

当 `<form>` 内同时存在功能按钮（如密码眼睛图标 `type="button"`）和提交按钮（`type="submit"`）时，**禁止用 `form button` 这类模糊选择器**。Playwright 点击的是第一个匹配元素，可能是工具按钮而非提交按钮，导致表单从未提交，登录/注册等关键流程永远失败。

| ❌ 禁止（模糊，点到工具按钮） | ✅ 正确（精确） |
|---|---|
| `form button` | 先读源码确认提交按钮的 type，若有 `type="submit"` 则用 `form button[type='submit']` |
| `button:last-child` | 若提交按钮无 type，用文字内容组合：`.space-y-4 > button:last-of-type` 或建议开发者加 `data-testid` |
---

## 四、瞬�?UI 不可断言清单

以下组件是瞬态的（短暂显示后自动消失），Playwright **无法可靠捕获**，禁止用 `assert_text` 断言�?

| 组件 | 说明 | 替代方案 |
|------|------|---------|
| 浏览�?`alert()`/`confirm()` | 原生弹窗不在 DOM �?| 引擎自动处理 |
| Toast 通知（如 antd message�?| 几秒后自动消�?| 断言页面状态变化而非 toast 文字 |
| `<notification>` 推�?| 浏览器级通知 | 无法断言 |

**可以断言�?*：持久化渲染�?DOM 中的文字（`<span>`、`<p>`、`<h1>`、`<div>` 等）�?

### 代码稽核要求

生成蓝本前，必须检查代码，确认 `expected` 文字是怎么渲染的：
- �?`<div className="error">登录失败</div>` �?持久化，可以断言
- �?`toast.error('登录失败')` �?瞬态，不能断言
- �?`alert('操作成功')` �?原生弹窗，不能断言

---

## 五、等待时间计算公�?

```
wait 时间 = 代码中的异步延迟 + 1500ms（预�?DOM 渲染 + 网络波动�?
```

| 代码场景 | wait 时间 |
|---------|----------|
| `setTimeout(fn, 1000)` | wait 2500 |
| `fetch('/api/login')` 无明确延�?| wait 2000（默�?API 预估�?|
| �?`setState` / 响应式更�?| wait 500 |
| 页面路由跳转（SPA�?| wait 1500 |
| 页面路由跳转（SSR/MPA�?| wait 2000 |

---

## 六、场景自包含原则与连续流模式（flow 强制决策�?

### ⚠️ 生成蓝本时必须对每个 page �?flow 决策

**判断规则（按顺序检查）�?*
1. �?page 下有 �? 个场景，且都需要先登录才能操作？→ **必须 `"flow": true`**
2. �?page 下有 �? 个场景是同页�?Tab 切换或连续操作？�?**必须 `"flow": true`**
3. �?page 下场景需要互相独立的干净状态（如正确登�?vs 错误登录）？�?不写 flow（默�?false�?

**简单总结：如果多个场景都要先登录再操作同一个页面，那这�?page 必须�?`"flow": true`。不�?flow 导致每个场景都重新打开页面+重复登录 = 严重浪费�?*

### ⚠️ flow 第一场景�?localStorage 登录态陷阱（必读！）

Web 应用通常把登�?token 存在 localStorage/sessionStorage�?*即使刷新页面也保持登�?*。这�?flow 第一场景会造成以下问题�?

**问题复现过程**�?
1. flow 第一场景执行 `navigate` 到登录页
2. 应用检测到 localStorage 中有 token �?自动跳转到已登录主页
3. 页面不是登录表单 �?填写用户�?密码的步骤全部超时失�?
4. 整个 flow 页面所有场景连锁失�?

**如何判断应用是否有此问题**：代码中搜索 `localStorage.getItem`、`localStorage.setItem`，如果存储了 `token`、`user`、`auth` 等字段，说明登录状态持久化，必须处理此陷阱�?

**正确写法**：flow 第一场景先点退出登录，再重新登录：

```json
{
  "name": "登录进入功能页（先确保退出登录）",
  "steps": [
    {"action": "navigate", "value": "http://localhost:3000", "description": "打开应用"},
    {"action": "wait", "value": "1500", "description": "等待页面加载"},
    {"action": "click", "target": "退出登录按钮的选择�?, "description": "先点退出，确保未登录状态（按钮不存在则超时skip，不影响后续�?},
    {"action": "wait", "value": "1000"},
    {"action": "fill", "target": "#username", "value": "admin"},
    {"action": "fill", "target": "#password", "value": "123456"},
    {"action": "click", "target": "#login-btn"}
  ]
}
```

**如果应用没有退出按�?*：不使用 `flow: true`，改�?`flow: false`（默认），引擎在每个场景前自动清�?localStorage，保证从未登录状态开始�?

---

### 默认模式（`flow: false`�?

- 每个场景的第一�?*必须**�?`navigate`
- 引擎在每个场景开始前会自动清�?cookie/localStorage
- **禁止**场景间传递状态（如场�?登录后场�?直接操作�?
- 如果场景需要登录状态，必须在该场景内重新执行登录步�?

### 连续流模式（`flow: true`�?

�?`page` 级别设置 `"flow": true`，同一页面内的场景将连续执行，不清除状态：

```json
{
  "url": "/dashboard",
  "title": "仪表�?,
  "flow": true,
  "scenarios": [
    {
      "name": "登录进入仪表�?,
      "steps": [
        {"action": "navigate", "value": "/login", "description": "打开登录�?},
        {"action": "fill", "target": "#username", "value": "admin"},
        {"action": "fill", "target": "#password", "value": "123456"},
        {"action": "click", "target": "#loginBtn"},
        {"action": "wait", "value": "2000"},
        {"action": "assert_text", "expected": "仪表�?}
      ]
    },
    {
      "name": "切换时间范围",
      "steps": [
        {"action": "navigate", "value": "/dashboard", "description": "（flow下自动跳过）"},
        {"action": "click", "target": ".date-range-btn"},
        {"action": "assert_text", "expected": "本月"}
      ]
    },
    {
      "name": "导出报表",
      "steps": [
        {"action": "navigate", "value": "/dashboard", "description": "（flow下自动跳过）"},
        {"action": "click", "target": "#exportBtn"},
        {"action": "assert_text", "expected": "导出成功"}
      ]
    }
  ]
}
```

**flow 模式行为�?*
- 仅第1个场景执�?navigate，后续场景的 navigate **自动跳过**
- 场景间不清除 cookie/localStorage，保持页面状�?
- 连续3个场景失�?�?尝试刷新恢复后继�?

**重要�?* flow 场景仍需�?navigate（方便单独运行），引擎在 flow 模式下自动跳过�?

### 🚨 flow 非首场景写法（极其重要，必须遵守！）

**flow 模式下，�?个及之后的场景只�?navigate + 该场景自己的操作步骤，绝对禁止重复写登录步骤�?*

引擎会跳过非首场景的 navigate，直接从�?步开始执行。如果第2步是 `fill 用户名`，但页面此时已经登录在功能页�?�?找不到输入框 �?超时失败 �?连续3步失�?�?整个场景被熔断跳�?�?后续场景全部同样失败�?

| �?错误写法（非首场景重复登录） | �?正确写法（非首场景直接操作） |
|---|---|
| 场景2: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?click选择生活账本 | 场景2: navigate �?click选择生活账本 �?wait �?assert_text |
| 场景3: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?click选择公司账本 | 场景3: navigate �?click选择公司账本 �?wait �?assert_text |

**正确�?flow 蓝本示例�?*
```json
{
  "flow": true,
  "scenarios": [
    {
      "name": "登录进入功能�?,
      "steps": [
        {"action": "navigate", "value": "http://localhost:5173"},
        {"action": "wait", "value": "2000"},
        {"action": "fill", "target": "#username", "value": "admin"},
        {"action": "fill", "target": "#password", "value": "123456"},
        {"action": "click", "target": "#loginBtn"},
        {"action": "wait", "value": "2000"},
        {"action": "assert_text", "expected": "功能页标�?}
      ]
    },
    {
      "name": "操作A",
      "steps": [
        {"action": "navigate", "value": "http://localhost:5173", "description": "flow模式下自动跳�?},
        {"action": "click", "target": ".action-a-btn"},
        {"action": "assert_text", "expected": "操作A结果"}
      ]
    },
    {
      "name": "操作B",
      "steps": [
        {"action": "navigate", "value": "http://localhost:5173", "description": "flow模式下自动跳�?},
        {"action": "click", "target": ".action-b-btn"},
        {"action": "assert_text", "expected": "操作B结果"}
      ]
    }
  ]
}
```

**核心原则：flow 模式下，只有�?个场景做完整的导�?登录流程，后续场景的 navigate 后面直接写该场景自己的操作�?*

---

## 七、完�?JSON 模板

```json
{
  "app_name": "你的应用�?,
  "description": "50-200字功能描�?,
  "base_url": "http://localhost:3000",
  "platform": "web",
  "start_command": "npm run dev",
  "start_cwd": "C:\\projects\\your-app",
  "pages": [
    {
      "url": "/login",
      "name": "登录�?,
      "scenarios": [
        {
          "name": "正确账号登录成功",
          "description": "使用正确的用户名密码登录",
          "steps": [
            {"action": "navigate", "value": "/login", "description": "打开登录页面"},
            {"action": "fill", "target": "#username", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "#password", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "#login-btn", "description": "点击登录按钮，提交表单触发API请求"},
            {"action": "wait", "value": "2000", "description": "等待API响应和页面跳�?},
            {"action": "assert_text", "expected": "控制�?, "description": "验证登录成功后跳转到控制台页�?},
            {"action": "screenshot", "description": "登录成功后的控制台页�?}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清单（生成蓝本前必须逐项验证�?

- [ ] 在源码中搜索每个 `target` 选择器，确认元素确实存在
- [ ] 确认 `expected` 文字在源码中是持久化渲染的（不是 toast/alert�?
- [ ] 检查操作触发的代码路径是否包含异步调用（fetch/setTimeout），如有则按公式计算 wait
- [ ] 确认 `navigate` 的路径与代码中的路由定义一�?
- [ ] 确认 `<select>` 元素�?`select` 动作，不�?`fill`
- [ ] 确认每个操作后有 `assert_text` �?`screenshot` 验证结果
### 🚨 输出前强制回检（3项必检，不通过必须修正）

**回检1 — flow 决策**：扫描每个 page，该 page 下是否有 ≥2 个场景都需要先登录再操作？
- 是 → 该 page **必须**有 `"flow": true`，且非首场景**禁止**写登录步骤
- 否 → 不设 flow（场景各自独立登录）

**回检2 — 断言覆盖**：扫描每个 scenario，是否至少有一个 `assert_text` 步骤？
- **只有 screenshot 没有 assert_text = 不合格**，必须补充文本断言
- `expected` 必须是页面上实际渲染的持久化文字（不是 toast/alert 的瞬态文字）
- 典型断言：登录成功后断言"选择应用"或用户名；错误登录断言"密码错误"；页面跳转断言新页面标题

**回检3 — 重复登录检查**：扫描整个蓝本，是否存在 ≥3 个场景都有完全相同的登录步骤序列？
- 是 → 必须把这些场景合并到同一个 page 并启用 `"flow": true`，只在首场景登录一次
---

## 九、踩坑清�?

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| **`start_cwd` �?`"."`** | 引擎在错误目录启动，`exit code 1`，所有步�?`ERR_CONNECTION_REFUSED` | 填被测项目绝对路径，�?`"D:\\projects\\my-app"` || **修复Bug时擅自改 `platform` 字段** | Web应用被改成 `desktop` 后走桌面引擎，CSS选择器全部失效，问题更多 | **`platform` 字段一旦确定禁止修改**；修Bug只改选择器和断言，不改platform/base_url/start_command |
| **用 `electron:start` 启动未构建的Electron应用** | Electron加载 `http://localhost:5173` 但vite未启动→白屏→窗口无内容 | 桌面模式必须用 `electron:dev`（同时启动vite+electron），或先 `npm run build` 再用 `electron:start` || **依赖未安装就跑测�?* | `npm run dev` 失败退出，30秒超时后继续跑，全部失败 | 先手�?`npm install`，确认项目能启动再测�?|
| **端口已被占用** | 新进程启动失败，引擎等超时后继续，全部失�?| 手动确认端口空闲，或修改 `base_url` 端口 |
| �?`<select>` �?`fill` | 引擎报错 | �?`select` 动作 |
| `expected` 写了 toast 文字 | 断言失败（文字已消失�?| 断言页面持久化状�?|
| 场景间依赖登录状�?| 后续场景全部失败 | 每个场景独立登录 |
| 没有 wait 就断言异步结果 | 断言时数据还没到 | 按公式计�?wait |
| 选择器用�?`div:nth-child(3)` | 页面改版就断 | �?id 或稳�?class |
| **flow 非首场景重复写登录步�?* | navigate 被跳过后�?步是 fill 用户名，但页面已登录，找不到输入框，连续失败熔断 | flow 非首场景只写 navigate + 自己的操�?|
| **用组件名�?CSS class** | `div[class*='Select']` 永远不匹配，组件实际渲染 `<div class="relative">` | 打开组件源码看实际渲染的 class |
| **flow 场景混用不同入口的表单字�?* | 点了「快速记账」弹窗，却填「记账凭证」的字段，连续超�?| 一个场景进了哪个弹�?表单就只操作该表单的元素 |

---

## 十、不同入�?弹窗的字段隔离规则（必须遵守�?

同一个页面可能有多个入口（如"快速记�?按钮�?记账凭证"按钮），每个入口打开的弹�?表单内的元素完全不同�?

### 强制规则

1. **一个场景只操作一个入口打开的表�?*。点击了A入口，就只能操作A弹窗里的元素，不得跨弹窗引用B入口的字段�?
2. **生成蓝本前，必须确认每个字段属于哪个入口**。方法：在代码中找到入口按钮的点击事�?�?追踪打开的组�?弹窗 �?列出该弹窗内的所有字段�?
3. **禁止猜测弹窗内有什么字�?*。两个看起来相似的弹窗（�?快速记�?�?记账凭证"）可能字段完全不同�?
4. **flow 模式下尤其危�?*：前一场景停留在弹窗A，下一场景的步骤却操作弹窗B的字�?�?必然超时�?

### 错误示例

```
�?场景"创建记账凭证"步骤�?
  click "快速记�? �?fill "凭证�?（❌ 快速记账弹窗里没有"凭证�?字段！）

�?修正�?
  click "记账凭证" �?fill "凭证�?（✅ 记账凭证弹窗里才有这个字段）
```
