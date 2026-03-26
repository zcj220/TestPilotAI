<!-- TestPilot-Template-Version: 9 -->
# 微信小程序平台蓝本规则（platform = "miniprogram"�?

> 本文件定义微信小程序蓝本的完整规则�?
> 小程�?WXML **不是 HTML**，选择器规则与 Web 完全不同�?
> 生成蓝本�?*必须**通读本文件，不得跳过任何章节�?

---

## 零、生成蓝本前必须先通读源代码（强制执行�?

**蓝本的唯一依据是代码，不是猜测，不是常识，不是用户描述�?*

在写任何 JSON 之前，必须按顺序完成�?

0. **先读 `testpilot/CHANGELOG.md`（如果存在）** �?了解当前已覆盖的功能和尚未测试的模块，避免重复写或漏写；如果不存在则跳过
1. **�?`app.json`** �?了解所有页面路由和 TabBar 配置
2. **读每个页面的 `.wxml` 文件** �?找出所有可操作元素，记录真实的 `class`、`placeholder`、`bindtap` 属�?
3. **读对应的 `.js` 文件** �?确认每个操作的真实结果（跳转哪里、显示什么文字）
4. **确认提示方式** �?成功/失败提示�?`wx.showToast()`（瞬态，**不可断言**）还是页面内文字节点（可断言�?
5. **列出已实现功�?* �?代码里有什么就测什么，未实现的功能不写蓝本

**禁止跳过代码阅读直接生成蓝本。凭想象写的选择器和断言几乎必然失败�?*

---

## 一、必填字�?

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"miniprogram"` | `"miniprogram"` |
| `base_url` | `miniprogram://` + 项目**绝对路径** | `"miniprogram://D:/projects/my-app"` |
| `app_name` | 应用名称 | `"财务记账小程�?` |
| `description` | 50-200字功能描�?| |

### 反面禁止

- �?`base_url` 用相对路�?�?必须是绝对路�?
- �?`base_url` �?`http://` �?必须�?`miniprogram://` 前缀
- �?填了 `start_command`（引擎自动处�?cli open/auto�?
- �?填了 `app_package` / `bundle_id`（那是移动端字段�?

---

## 二、封闭式动作�?

### 基础动作（与其他平台通用�?

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(页面路径), `description` | 页面跳转（清空页面栈，用 wx.reLaunch�?|
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `select` | `target`, `value`, `description` | 操作 picker 组件�?*只用�?`<picker>`**�?|
| `wait` | `description` | 等待（`value` 指定毫秒�?|
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 小程序专用动�?

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate_to` | `value`(页面路径), `description` | 不清空页面栈（用 wx.navigateTo�?|
| `evaluate` | `value`(JS代码), `description` | 在小程序端执行JS（可访问 wx/getApp�?|
| `page_query` | `target`(选择�?, `value`(操作), `description` | 查询元素（value: text/count/texts�?|
| `call_method` | `target`(方法�?, `value`(JSON参数), `description` | 调用页面方法 |
| `read_text` | `target`, `expected`, `description` | 读取元素文本并可选断言 |
| `tap_multiple` | `target`, `value`(次数), `wait_ms`, `description` | 连续点击多次 |
| `scroll` | `value`(scrollTop), `description` | 滚动页面 |
| `assert_compare` | `target`, `value`(比较表达�?, `description` | 数值比较（�?`">=100"`�?|

### 绝对禁止的动�?

- �?`reset_state`（一般不需要手动调用，引擎自动处理场景重置�?
- �?`hover`（小程序没有 hover 概念�?

---

## 三、选择器规则（⚠️ �?Web 完全不同！）

### WXML 不是 HTML，以�?Web 选择器全部无�?

| �?无效选择�?| 原因 |
|---|---|
| `#login-btn` | WXML 不支�?id 选择�?|
| `button:contains('登录')` | 不支�?`:contains()` 伪类 |
| `input[type="text"]` | WXML �?input 没有 type attribute |
| `div > span` | WXML 里是 view/text，不�?div/span |
| `input[name="xxx"]` | WXML �?input 没有 name attribute |

### 🚨 选择器三步验证（强制执行，每�?target 都必须做�?

写任何一�?`target` 选择器之前，必须完成以下三步�?*缺一不可**�?

1. **定位源码**：找到该元素所在的 `.wxml` 文件，定位到具体�?
2. **复制属�?*：从 WXML 代码中复制元素的真实 `class`、`placeholder`、`data-xxx` 属性（**禁止凭记忆或猜测**�?
3. **唯一性验�?*：在同一页面 WXML 中搜索该选择器，确认只匹配一个元�?

**不做三步验证就写的选择�?= 必然出错。这是选择器失败的第一大原因�?*

### 正确的小程序选择器（按优先级排列�?

1. **�?placeholder 区分 input**：`input[placeholder*='用户�?]`、`input[placeholder*='密码']`
2. **�?class 区分按钮**：`button.btn-primary`（配�?bindtap 确认是哪个按钮）
3. **�?class 组合定位**：`.card .form-input`（结合父容器缩小范围�?
4. **�?data- 属�?*：`view[data-tab='profit']`（小程序常用 data-xxx 传参�?
5. **用文本辅助定�?*：在 description 中描述元素文字，帮助引擎 AI 定位

### ⚠️ picker 组件：用 select 不用 click

```json
�?{"action": "select", "target": "picker.type-picker", "value": "收入"}
�?{"action": "click", "target": "picker.type-picker"}  // picker 是原生组件，不能 click
```

### ⚠️ TabBar 页面：用 navigate 不用 click

```json
�?{"action": "navigate", "value": "pages/reports/reports"}
�?{"action": "click", "target": ".tab-bar-item"}  // 原生 TabBar 不在 DOM �?
```

---

## 四、瞬�?UI 不可断言清单

| 组件 | 说明 |
|------|------|
| `wx.showToast()` | 短暂显示后自动消失，不在 DOM �?|
| `wx.showModal()` | **原生弹窗不在 DOM �?*，Automator 无法操作 |
| `wx.showLoading()` | loading 提示�?|
| `wx.showActionSheet()` | 原生操作菜单 |

**不能�?click 操作 wx.showModal 的确�?取消按钮�?*
如果业务依赖 Modal 确认，应建议开发者改用页面内自定义弹窗�?

### 代码稽核—持久性验�?

```
�?可以断言�?
   - <text class="title">记账�?/text>     �?expected: "记账�?
   - <view class="amount">¥100</view>       �?expected: "¥100"
   - 页面中持久存在的 WXML 元素

�?不能断言�?
   - wx.showToast({ title: '保存成功' })    �?瞬态，消失后断言失败
   - wx.showModal({ title: '确认删除�? })  �?原生弹窗，不�?DOM �?
```

---

## 五、等待时间计算公�?

```
wait 时间 = 代码中的异步延迟 + 1500ms（预留小程序渲染 + Automator 刷新�?
```

| 场景 | wait 时间 |
|------|----------|
| `wx.request()` API 调用 + 数据渲染 | API时间 + 1500 |
| `wx.navigateTo()` 页面跳转 | wait 1500 |
| `wx.reLaunch()` 重载页面�?| wait 2000 |
| `setData()` 纯数据更�?| wait 1000 |
| picker 选择后数据更�?| wait 1000 |

---

## 六、场景自包含原则与连续流模式（flow 强制决策�?

### ⚠️ 生成蓝本时必须对每个 page �?flow 决策

**判断规则（按顺序检查）�?*
1. �?page 下有 �? 个场景，且都需要先登录才能操作？→ **必须 `"flow": true`**
2. �?page 下有 �? 个场景是 TabBar 切换或连续操作？�?**必须 `"flow": true`**
3. �?page 下场景需要互相独立的干净状态（如正确登�?vs 错误登录）？�?不写 flow（默�?false�?

**简单总结：如果多个场景都要先登录再操作同一个页面，那这�?page 必须�?`"flow": true`。不�?flow 导致每个场景�?reLaunch+重复登录 = 严重浪费�?*

### 默认模式（`flow: false`�?

- 引擎在每个场景前自动�?`wx.reLaunch` 回首页并清理状�?
- 每个场景的第一步必须是 `navigate`
- 不需要手动写重启小程序的步骤（引擎自动处�?cli close/open/auto�?
- **禁止**场景间传递状态（如场�?登录后场�?直接访问已登录页面）

### 连续流模式（`flow: true`�?

�?`page` 级别设置 `"flow": true`，同一页面内的场景将连续执行：
- 仅第1个场景执�?navigate，后续场景的 navigate **自动跳过**
- 场景间不重置页面栈，保持当前状�?
- 连续3个场景失�?�?尝试 reLaunch 恢复后继�?
- 每个场景仍需�?navigate（方便单独运行）

**重要�?* flow 场景仍需�?navigate（方便单独运行），引擎在 flow 模式下自动跳过�?

### 🚨 flow 非首场景写法（极其重要，必须遵守！）

**flow 模式下，�?个及之后的场景只�?navigate + 该场景自己的操作步骤，绝对禁止重复写登录步骤�?*

引擎会跳过非首场景的 navigate，直接从�?步开始执行。如果第2步是 `fill 用户名`，但页面此时已经登录在功能页�?�?找不到输入框 �?超时失败 �?连续3步失�?�?整个场景被熔断跳�?�?后续场景全部同样失败�?

| �?错误写法（非首场景重复登录） | �?正确写法（非首场景直接操作） |
|---|---|
| 场景2: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?实际操作 | 场景2: navigate �?实际操作 �?assert_text |
| 场景3: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?实际操作 | 场景3: navigate �?实际操作 �?assert_text |

**核心原则：flow 模式下，只有�?个场景做完整的导�?登录流程，后续场景的 navigate 后面直接写该场景自己的操作�?*

---

## 七、完�?JSON 模板

```json
{
  "app_name": "你的小程序名",
  "description": "50-200字功能描�?,
  "base_url": "miniprogram://D:/projects/你的小程序路�?,
  "platform": "miniprogram",
  "pages": [
    {
      "url": "pages/index/index",
      "name": "首页",
      "scenarios": [
        {
          "name": "正确登录跳转记账�?,
          "steps": [
            {"action": "navigate", "value": "pages/login/login", "description": "打开登录�?},
            {"action": "fill", "target": "input[placeholder*='用户�?]", "value": "admin", "description": "输入用户名admin"},
            {"action": "fill", "target": "input[placeholder*='密码']", "value": "admin123", "description": "输入密码admin123"},
            {"action": "click", "target": "button.btn-primary", "description": "点击登录按钮，按钮文字为'登录'"},
            {"action": "wait", "value": "2000", "description": "等待API验证+页面跳转"},
            {"action": "assert_text", "expected": "记账�?, "description": "验证跳转到记账台页面，标题显�?记账�?"},
            {"action": "screenshot", "description": "登录成功后的记账台页�?}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清�?

- [ ] 通读所�?WXML 文件，确认选择器中�?class/placeholder 在代码中存在
- [ ] **没有使用任何 `#id` 选择�?*
- [ ] **没有使用 `:contains()` 伪类**
- [ ] input �?`placeholder` 属性区分，不用 `id` �?`name`
- [ ] `<picker>` �?`select` 动作，不�?`click`
- [ ] 没有操作 `wx.showModal`/`wx.showToast` 等原生弹�?
- [ ] TabBar 页面跳转�?`navigate`，不�?`click`
- [ ] `base_url` �?`miniprogram://绝对路径`
- [ ] `expected` 文本来自 WXML 中持久渲染的元素，不�?Toast/Modal- [ ] 确认每个操作后有 `assert_text` 或 `screenshot` 验证结果

### 🚨 输出前强制回检（3项必检，不通过必须修正）

**回检1 — flow 决策**：扫描每个 page，该 page 下是否有 ≥2 个场景都需要先登录再操作？
- 是 → 该 page **必须**有 `"flow": true`，且非首场景**禁止**写登录步骤
- 否 → 不设 flow（场景各自独立登录）

**回检2 — 断言覆盖**：扫描每个 scenario，是否至少有一个 `assert_text` 步骤？
- **只有 screenshot 没有 assert_text = 不合格**，必须补充文本断言
- `expected` 必须来自 WXML 中持久渲染的元素文字，不是 wx.showToast/wx.showModal

**回检3 — 重复登录检查**：扫描整个蓝本，是否存在 ≥3 个场景都有完全相同的登录步骤序列？
- 是 → 必须把这些场景合并到同一个 page 并启用 `"flow": true`，只在首场景登录一次
---

## 九、踩坑清�?

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| �?`#login-btn` | WXML 不支�?id 选择器，找不�?| �?`button.btn-primary` |
| �?`button:contains('登录')` | 不支�?:contains 伪类 | �?class + description 描述文字 |
| �?`<picker>` �?`click` | picker 是原生组�?| �?`select` 动作 |
| �?wx.showModal �?`click` | 原生弹窗不在 DOM �?| 跳过或建议改用页面内弹窗 |
| 断言 wx.showToast 文字 | 瞬态消�?| 断言页面持久化状态变�?|
| `base_url` 用相对路�?| 引擎找不到项�?| 必须用绝对路�?|
| TabBar �?click | 原生 TabBar 不可点击 | �?`navigate` 直接跳转 |
| �?`div`/`span` 标签�?| WXML 里是 `view`/`text` | 用正确的 WXML 标签�?|
| �?`input[type="text"]` | WXML input 没有 type | �?`input[placeholder*='xxx']` |
| 写死注册用户�?| 第二次运�?用户已存�? | 用时间戳用户名或清数�?|
| 场景2依赖场景1登录 | 引擎每场景清状�?| 每个场景独立登录 |
