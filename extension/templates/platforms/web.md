# Web 平台蓝本规则（platform = "web"）

> 本文件定义 Web 应用（React/Vue/Angular/纯HTML）蓝本的完整规则。
> 生成蓝本前**必须**通读本文件，不得跳过任何章节。

---

## 一、必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"web"` | `"web"` |
| `base_url` | 应用访问地址 | `"http://localhost:3000"` |
| `start_command` | 启动命令（纯HTML留空） | `"npm start"` |
| `start_cwd` | 启动目录（默认 `.`） | `"."` |
| `app_name` | 应用名称 | `"电商管理系统"` |
| `description` | 50-200字功能描述 | |

### 反面禁止

- ❌ `base_url` 不能留空（Web 必须有地址）
- ❌ 不要填 `app_package`、`app_activity`、`bundle_id`（那是手机平台的字段）
- ❌ `start_command` 不要填 `python manage.py runserver 0.0.0.0:8000`，应该填 `python manage.py runserver`（不绑外网）

---

## 二、封闭式动作表（只允许以下动作，禁止使用不在此列表中的动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(URL), `description` | 页面跳转（场景第一步必须是 navigate） |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本（用于 input/textarea） |
| `select` | `target`, `value`, `description` | 下拉框选择（用于 `<select>` 元素，不要用 fill） |
| `wait` | `description` | 等待（`value` 指定毫秒，或 `target` 等待元素出现） |
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动作

- ❌ `reset_state`（引擎自动处理，蓝本不要写）
- ❌ `navigate_to`（这是小程序专用动作）
- ❌ `evaluate`、`call_method`、`page_query`（这些是小程序专用动作）

---

## 三、选择器规则

### 优先级（从高到低）

1. **`#id`** — 最稳定，如 `#login-btn`、`#username`
2. **`[name="xxx"]`** — 表单元素，如 `input[name="email"]`
3. **`.class`** — 稳定 class，如 `.submit-btn`、`.nav-link`
4. **组合选择器** — 缩小范围，如 `.form-login #username`

### 绝对禁止的选择器

- ❌ `div:nth-child(N)` — 脆弱，DOM 结构变化即失效
- ❌ `body > div > div > form > input` — 层级太深，随改随断
- ❌ `accessibility_id:xxx` — 这是手机平台选择器，Web 不支持
- ❌ `name:xxx` — 这是桌面平台选择器，Web 不支持
- ❌ 没有任何属性约束的标签选择器（如单独的 `div`、`span`、`button`）

---

## 四、瞬态 UI 不可断言清单

以下组件是瞬态的（短暂显示后自动消失），Playwright **无法可靠捕获**，禁止用 `assert_text` 断言：

| 组件 | 说明 | 替代方案 |
|------|------|---------|
| 浏览器 `alert()`/`confirm()` | 原生弹窗不在 DOM 中 | 引擎自动处理 |
| Toast 通知（如 antd message） | 几秒后自动消失 | 断言页面状态变化而非 toast 文字 |
| `<notification>` 推送 | 浏览器级通知 | 无法断言 |

**可以断言的**：持久化渲染在 DOM 中的文字（`<span>`、`<p>`、`<h1>`、`<div>` 等）。

### 代码稽核要求

生成蓝本前，必须检查代码，确认 `expected` 文字是怎么渲染的：
- ✅ `<div className="error">登录失败</div>` → 持久化，可以断言
- ❌ `toast.error('登录失败')` → 瞬态，不能断言
- ❌ `alert('操作成功')` → 原生弹窗，不能断言

---

## 五、等待时间计算公式

```
wait 时间 = 代码中的异步延迟 + 1500ms（预留 DOM 渲染 + 网络波动）
```

| 代码场景 | wait 时间 |
|---------|----------|
| `setTimeout(fn, 1000)` | wait 2500 |
| `fetch('/api/login')` 无明确延迟 | wait 2000（默认 API 预估） |
| 纯 `setState` / 响应式更新 | wait 500 |
| 页面路由跳转（SPA） | wait 1500 |
| 页面路由跳转（SSR/MPA） | wait 2000 |

---

## 六、场景自包含原则

- 每个场景的第一步**必须**是 `navigate`
- 引擎在每个场景开始前会自动清除 cookie/localStorage
- **禁止**场景间传递状态（如场景1登录后场景2直接操作）
- 如果场景需要登录状态，必须在该场景内重新执行登录步骤

---

## 七、完整 JSON 模板

```json
{
  "app_name": "你的应用名",
  "description": "50-200字功能描述",
  "base_url": "http://localhost:3000",
  "platform": "web",
  "start_command": "npm start",
  "start_cwd": ".",
  "pages": [
    {
      "url": "/login",
      "name": "登录页",
      "scenarios": [
        {
          "name": "正确账号登录成功",
          "description": "使用正确的用户名密码登录",
          "steps": [
            {"action": "navigate", "value": "/login", "description": "打开登录页面"},
            {"action": "fill", "target": "#username", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "#password", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "#login-btn", "description": "点击登录按钮，提交表单触发API请求"},
            {"action": "wait", "value": "2000", "description": "等待API响应和页面跳转"},
            {"action": "assert_text", "expected": "控制台", "description": "验证登录成功后跳转到控制台页面"},
            {"action": "screenshot", "description": "登录成功后的控制台页面"}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清单（生成蓝本前必须逐项验证）

- [ ] 在源码中搜索每个 `target` 选择器，确认元素确实存在
- [ ] 确认 `expected` 文字在源码中是持久化渲染的（不是 toast/alert）
- [ ] 检查操作触发的代码路径是否包含异步调用（fetch/setTimeout），如有则按公式计算 wait
- [ ] 确认 `navigate` 的路径与代码中的路由定义一致
- [ ] 确认 `<select>` 元素用 `select` 动作，不用 `fill`
- [ ] 确认每个操作后有 `assert_text` 或 `screenshot` 验证结果

---

## 九、踩坑清单

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 对 `<select>` 用 `fill` | 引擎报错 | 用 `select` 动作 |
| `expected` 写了 toast 文字 | 断言失败（文字已消失） | 断言页面持久化状态 |
| 场景间依赖登录状态 | 后续场景全部失败 | 每个场景独立登录 |
| 没有 wait 就断言异步结果 | 断言时数据还没到 | 按公式计算 wait |
| 选择器用了 `div:nth-child(3)` | 页面改版就断 | 用 id 或稳定 class |
