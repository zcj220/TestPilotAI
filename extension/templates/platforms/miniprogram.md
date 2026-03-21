# 微信小程序平台蓝本规则（platform = "miniprogram"）

> 本文件定义微信小程序蓝本的完整规则。
> 小程序 WXML **不是 HTML**，选择器规则与 Web 完全不同。
> 生成蓝本前**必须**通读本文件，不得跳过任何章节。

---

## 一、必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"miniprogram"` | `"miniprogram"` |
| `base_url` | `miniprogram://` + 项目**绝对路径** | `"miniprogram://D:/projects/my-app"` |
| `app_name` | 应用名称 | `"财务记账小程序"` |
| `description` | 50-200字功能描述 | |

### 反面禁止

- ❌ `base_url` 用相对路径 → 必须是绝对路径
- ❌ `base_url` 用 `http://` → 必须用 `miniprogram://` 前缀
- ❌ 填了 `start_command`（引擎自动处理 cli open/auto）
- ❌ 填了 `app_package` / `bundle_id`（那是移动端字段）

---

## 二、封闭式动作表

### 基础动作（与其他平台通用）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(页面路径), `description` | 页面跳转（清空页面栈，用 wx.reLaunch） |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `select` | `target`, `value`, `description` | 操作 picker 组件（**只用于 `<picker>`**） |
| `wait` | `description` | 等待（`value` 指定毫秒） |
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 小程序专用动作

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate_to` | `value`(页面路径), `description` | 不清空页面栈（用 wx.navigateTo） |
| `evaluate` | `value`(JS代码), `description` | 在小程序端执行JS（可访问 wx/getApp） |
| `page_query` | `target`(选择器), `value`(操作), `description` | 查询元素（value: text/count/texts） |
| `call_method` | `target`(方法名), `value`(JSON参数), `description` | 调用页面方法 |
| `read_text` | `target`, `expected`, `description` | 读取元素文本并可选断言 |
| `tap_multiple` | `target`, `value`(次数), `wait_ms`, `description` | 连续点击多次 |
| `scroll` | `value`(scrollTop), `description` | 滚动页面 |
| `assert_compare` | `target`, `value`(比较表达式), `description` | 数值比较（如 `">=100"`） |

### 绝对禁止的动作

- ❌ `reset_state`（一般不需要手动调用，引擎自动处理场景重置）
- ❌ `hover`（小程序没有 hover 概念）

---

## 三、选择器规则（⚠️ 与 Web 完全不同！）

### WXML 不是 HTML，以下 Web 选择器全部无效

| ❌ 无效选择器 | 原因 |
|---|---|
| `#login-btn` | WXML 不支持 id 选择器 |
| `button:contains('登录')` | 不支持 `:contains()` 伪类 |
| `input[type="text"]` | WXML 的 input 没有 type attribute |
| `div > span` | WXML 里是 view/text，不是 div/span |
| `input[name="xxx"]` | WXML 的 input 没有 name attribute |

### 正确的小程序选择器（按优先级排列）

1. **用 placeholder 区分 input**：`input[placeholder*='用户名']`、`input[placeholder*='密码']`
2. **用 class 区分按钮**：`button.btn-primary`（配合 bindtap 确认是哪个按钮）
3. **用 class 组合定位**：`.card .form-input`（结合父容器缩小范围）
4. **用 data- 属性**：`view[data-tab='profit']`（小程序常用 data-xxx 传参）
5. **用文本辅助定位**：在 description 中描述元素文字，帮助引擎 AI 定位

### ⚠️ picker 组件：用 select 不用 click

```json
✅ {"action": "select", "target": "picker.type-picker", "value": "收入"}
❌ {"action": "click", "target": "picker.type-picker"}  // picker 是原生组件，不能 click
```

### ⚠️ TabBar 页面：用 navigate 不用 click

```json
✅ {"action": "navigate", "value": "pages/reports/reports"}
❌ {"action": "click", "target": ".tab-bar-item"}  // 原生 TabBar 不在 DOM 中
```

---

## 四、瞬态 UI 不可断言清单

| 组件 | 说明 |
|------|------|
| `wx.showToast()` | 短暂显示后自动消失，不在 DOM 中 |
| `wx.showModal()` | **原生弹窗不在 DOM 中**，Automator 无法操作 |
| `wx.showLoading()` | loading 提示框 |
| `wx.showActionSheet()` | 原生操作菜单 |

**不能用 click 操作 wx.showModal 的确认/取消按钮！**
如果业务依赖 Modal 确认，应建议开发者改用页面内自定义弹窗。

### 代码稽核—持久性验证

```
✅ 可以断言：
   - <text class="title">记账台</text>     → expected: "记账台"
   - <view class="amount">¥100</view>       → expected: "¥100"
   - 页面中持久存在的 WXML 元素

❌ 不能断言：
   - wx.showToast({ title: '保存成功' })    → 瞬态，消失后断言失败
   - wx.showModal({ title: '确认删除？' })  → 原生弹窗，不在 DOM 中
```

---

## 五、等待时间计算公式

```
wait 时间 = 代码中的异步延迟 + 1500ms（预留小程序渲染 + Automator 刷新）
```

| 场景 | wait 时间 |
|------|----------|
| `wx.request()` API 调用 + 数据渲染 | API时间 + 1500 |
| `wx.navigateTo()` 页面跳转 | wait 1500 |
| `wx.reLaunch()` 重载页面栈 | wait 2000 |
| `setData()` 纯数据更新 | wait 1000 |
| picker 选择后数据更新 | wait 1000 |

---

## 六、场景自包含原则

- 引擎在每个场景前自动用 `wx.reLaunch` 回首页并清理状态
- 每个场景的第一步必须是 `navigate`
- 不需要手动写重启小程序的步骤（引擎自动处理 cli close/open/auto）
- **禁止**场景间传递状态（如场景1登录后场景2直接访问已登录页面）

---

## 七、完整 JSON 模板

```json
{
  "app_name": "你的小程序名",
  "description": "50-200字功能描述",
  "base_url": "miniprogram://D:/projects/你的小程序路径",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "pages/index/index",
      "name": "首页",
      "scenarios": [
        {
          "name": "正确登录跳转记账台",
          "steps": [
            {"action": "navigate", "value": "pages/login/login", "description": "打开登录页"},
            {"action": "fill", "target": "input[placeholder*='用户名']", "value": "admin", "description": "输入用户名admin"},
            {"action": "fill", "target": "input[placeholder*='密码']", "value": "admin123", "description": "输入密码admin123"},
            {"action": "click", "target": "button.btn-primary", "description": "点击登录按钮，按钮文字为'登录'"},
            {"action": "wait", "value": "2000", "description": "等待API验证+页面跳转"},
            {"action": "assert_text", "expected": "记账台", "description": "验证跳转到记账台页面，标题显示'记账台'"},
            {"action": "screenshot", "description": "登录成功后的记账台页面"}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清单

- [ ] 通读所有 WXML 文件，确认选择器中的 class/placeholder 在代码中存在
- [ ] **没有使用任何 `#id` 选择器**
- [ ] **没有使用 `:contains()` 伪类**
- [ ] input 用 `placeholder` 属性区分，不用 `id` 或 `name`
- [ ] `<picker>` 用 `select` 动作，不用 `click`
- [ ] 没有操作 `wx.showModal`/`wx.showToast` 等原生弹窗
- [ ] TabBar 页面跳转用 `navigate`，不用 `click`
- [ ] `base_url` 是 `miniprogram://绝对路径`
- [ ] `expected` 文本来自 WXML 中持久渲染的元素，不是 Toast/Modal

---

## 九、踩坑清单

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 用 `#login-btn` | WXML 不支持 id 选择器，找不到 | 用 `button.btn-primary` |
| 用 `button:contains('登录')` | 不支持 :contains 伪类 | 用 class + description 描述文字 |
| 对 `<picker>` 用 `click` | picker 是原生组件 | 用 `select` 动作 |
| 对 wx.showModal 用 `click` | 原生弹窗不在 DOM 中 | 跳过或建议改用页面内弹窗 |
| 断言 wx.showToast 文字 | 瞬态消失 | 断言页面持久化状态变化 |
| `base_url` 用相对路径 | 引擎找不到项目 | 必须用绝对路径 |
| TabBar 用 click | 原生 TabBar 不可点击 | 用 `navigate` 直接跳转 |
| 用 `div`/`span` 标签名 | WXML 里是 `view`/`text` | 用正确的 WXML 标签名 |
| 用 `input[type="text"]` | WXML input 没有 type | 用 `input[placeholder*='xxx']` |
| 写死注册用户名 | 第二次运行"用户已存在" | 用时间戳用户名或清数据 |
| 场景2依赖场景1登录 | 引擎每场景清状态 | 每个场景独立登录 |
