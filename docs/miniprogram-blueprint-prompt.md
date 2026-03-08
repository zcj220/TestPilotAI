# 微信小程序蓝本生成提示词（给编程AI用）

> 本文档是给编程AI（Cascade/Cursor/Copilot等）的系统提示词，用于生成 TestPilot AI 的小程序测试蓝本（testpilot.json）。
> 编程AI在生成蓝本时**必须严格遵守**以下所有规则，否则执行器会报错。

---

## 一、蓝本JSON结构

```json
{
  "app_name": "应用名称",
  "description": "应用功能描述",
  "base_url": "miniprogram://绝对路径/到/小程序项目目录",
  "version": "1.0",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "/pages/xxx/xxx",
      "title": "页面标题",
      "description": "页面功能描述",
      "scenarios": [
        {
          "name": "场景名称",
          "description": "场景描述",
          "steps": [
            { "action": "步骤类型", "target": "选择器", "value": "值", "expected": "预期", "description": "描述" }
          ]
        }
      ]
    }
  ]
}
```

**结构规则：**
- `pages`数组：每个元素代表一个页面，包含`url`、`title`、`description`、`scenarios`
- `scenarios`数组：每个元素代表一个测试场景，包含`name`、`description`、`steps`
- `steps`数组：每个元素是一个测试步骤
- 每个步骤必须有`action`字段，其余字段根据action类型决定是否必填

---

## 二、可用步骤类型（共15种）

### 2.1 页面导航

| action | 用途 | 必填字段 | 说明 |
|--------|------|---------|------|
| `navigate` | reLaunch跳页面（清空页面栈） | value=页面路径 | 如 `/pages/index/index` |
| `navigate_to` | navigateTo跳页面（保留页面栈） | value=页面路径 | 可以返回上一页 |
| `reset_state` | 重置全局状态+回首页 | 无（可选value自定义重置代码） | **每个场景的第一步必须是这个** |

### 2.2 元素交互

| action | 用途 | 必填字段 | 说明 |
|--------|------|---------|------|
| `click` | 点击元素 | target=CSS选择器 | 如 `#btn-add`、`.btn-primary` |
| `tap_multiple` | 连续点击N次 | target=选择器, value=次数 | 如点击加购按钮12次 |
| `fill` | 输入文本 | target=选择器, value=文本 | 用于input元素 |
| `scroll` | 滚动页面 | value=滚动距离(px) | 默认400 |

### 2.3 数据读取和查询

| action | 用途 | 必填字段 | 说明 |
|--------|------|---------|------|
| `read_text` | 读取元素文本（带3次重试） | target=选择器 | 可选expected做包含断言 |
| `page_query` | 查询元素（Node端automator API） | target=选择器, value=操作类型 | 操作类型见下方详解 |
| `evaluate` | 在小程序端执行JavaScript | value=JS代码 | ⚠️ 有严格格式要求，见铁律 |
| `call_method` | 调用页面方法 | target=方法名, value=参数JSON | 如调用 `onSearch` |

### 2.4 断言

| action | 用途 | 必填字段 | 说明 |
|--------|------|---------|------|
| `assert_text` | 文本包含断言 | target=选择器, expected=预期文本 | 验证元素文本包含expected |
| `assert_compare` | 数值比较断言 | target=选择器, value=比较表达式 | 如 `<=10`、`==0`、`>=100` |

### 2.5 辅助

| action | 用途 | 必填字段 | 说明 |
|--------|------|---------|------|
| `screenshot` | 截图 | 无 | description会作为截图标注 |
| `wait` | 等待 | value=毫秒数 | 如 `500`、`2000` |

---

## 三、page_query 详解

`page_query` 在Node.js端使用 miniprogram-automator 的 `page.$` 和 `page.$$` API查询元素。

**value字段的三种操作：**
- `"text"` — 读取单个元素的文本（默认）
- `"count"` — 统计匹配元素的数量
- `"texts"` — 读取所有匹配元素的文本数组

**示例：**
```json
{"action": "page_query", "target": ".product", "value": "count", "description": "统计商品数量"}
{"action": "page_query", "target": ".p-price", "value": "texts", "description": "读取所有价格"}
{"action": "page_query", "target": ".btn-checkout", "value": "count", "expected": "0", "description": "验证结算按钮不存在"}
```

---

## 四、⚠️ 铁律（违反必报错）

### 铁律1：evaluate的代码格式

**正确格式（两种）：**

**简单表达式（无声明语句）：**
```json
{"action": "evaluate", "value": "getApp().globalData.products.length"}
```

**复杂逻辑（有const/let/var/for）必须用IIFE包裹：**
```json
{"action": "evaluate", "value": "(() => { const app=getApp(); app.globalData.cart=[]; return 'ok'; })()"}
```

**❌ 错误格式（会报错）：**
```json
{"action": "evaluate", "value": "const g = getApp().globalData; g.cart = [];"}
{"action": "evaluate", "value": "var x = 1; return x;"}
```

**原因：** 执行器用 `new Function(代码)` 构造函数传给 `mp.evaluate()`。裸声明语句在函数体内执行时，automator的字符串序列化会出问题。IIFE或简单表达式则没问题。

### 铁律2：小程序没有document对象

**❌ 绝对不能在evaluate里用：**
- `document.querySelector()`
- `document.getElementById()`
- `document.getElementsByClassName()`
- 任何DOM API

**✅ evaluate里只能用：**
- `getApp()` — 获取App实例
- `getApp().globalData` — 读写全局数据
- `getCurrentPages()` — 获取当前页面栈
- `wx.xxx` — 微信API（如 `wx.reLaunch`、`wx.navigateTo`）

**✅ 查询页面元素用 `page_query` 或 `read_text`：**
```json
{"action": "page_query", "target": ".product", "value": "count"}
{"action": "read_text", "target": "#price-1"}
```

### 铁律3：每个场景必须以reset_state开头

```json
{
  "name": "场景N：xxx验证",
  "steps": [
    {"action": "reset_state", "description": "重置状态回首页"},
    ... 后续步骤
  ]
}
```

`reset_state` 做了三件事：
1. 清空全局状态（购物车、优惠券、地址等）
2. `wx.reLaunch` 回首页
3. 等待2秒让页面渲染完成

**不加reset_state会导致：** 上一个场景的残留数据影响当前场景。

### 铁律4：跨页面测试必须用navigate_to

不能在首页场景里直接读取购物车页的元素。需要：
```json
{"action": "navigate_to", "value": "/pages/cart/cart", "description": "跳转购物车"},
{"action": "read_text", "target": "#subtotal", "description": "读取总计"}
```

### 铁律5：call_method的参数必须是JSON字符串

```json
{"action": "call_method", "target": "onSearch", "value": "{\"detail\":{\"value\":\"苹果\"}}"}
{"action": "call_method", "target": "onDeliveryChange", "value": "{\"detail\":{\"value\":0}}"}
```

注意value是**字符串**，里面是合法JSON，双引号需要转义为`\"`。

### 铁律6：assert_compare的格式

`value` 字段格式为 `运算符+数字`（中间无空格）：
```json
{"action": "assert_compare", "target": "#cartCount", "value": "<=10"}
{"action": "assert_compare", "target": "#deliveryFee", "value": "==0"}
{"action": "assert_compare", "target": "#total", "value": ">=100"}
```

支持的运算符：`==`、`!=`、`<`、`<=`、`>`、`>=`

### 铁律7：选择器必须是小程序wxml中实际存在的

小程序用的是CSS选择器语法，但针对的是wxml中的class和id：
- `#price-1` — id选择器
- `.btn-primary` — class选择器
- `.product .p-name` — 后代选择器
- `#product-7 .btn-primary` — 组合选择器

**生成蓝本前必须先阅读wxml文件**，确认选择器存在。

---

## 五、踩坑记录（曾经导致失败的错误）

### 踩坑1：evaluate用字符串传声明语句
```
错误：mp.evaluate("var g = getApp()...")
报错：Unexpected token 'var'
原因：automator字符串evaluate不支持声明语句
修复：用IIFE包裹 (() => { ... })()
```

### 踩坑2：evaluate用字符串传URL路径
```
错误：mp.evaluate(`wx.reLaunch({ url: "${url}" })`)
报错：Arg string terminates parameters early
原因：URL中的/字符导致automator字符串解析中断
修复：执行器已改用new Function，蓝本里的evaluate不需要写wx.reLaunch
```

### 踩坑3：evaluate里用document.querySelector
```
错误：evaluate里写 document.querySelector('.price')
报错：document is not defined
原因：小程序环境没有DOM，不是浏览器
修复：改用page_query步骤读取元素
```

### 踩坑4：callMethod('onShow')超时
```
错误：reset_state里调用 homePage.callMethod('onShow')
现象：后续步骤卡死100秒
原因：SDK方法会超时
修复：去掉callMethod，reLaunch+sleep(2000)足够
```

### 踩坑5：空购物车点不存在的按钮
```
错误：空购物车时点击 .btn-checkout
报错：元素未找到: .btn-checkout
原因：空购物车时wx:if条件为false，按钮不渲染
修复：用page_query检查count==0验证按钮不存在
```

### 踩坑6：场景间状态污染
```
错误：场景2没有reset_state，上一场景的购物车数据还在
现象：断言失败，数据不符合预期
修复：每个场景第一步必须reset_state
```

---

## 六、蓝本生成示例任务

### 任务描述给AI的格式

```
请为以下微信小程序生成测试蓝本（testpilot.json）：

项目路径：D:/projects/TestPilotAI/miniprogram-demo
页面文件：
- pages/index/index.wxml（首页）
- pages/cart/cart.wxml（购物车）
- pages/checkout/checkout.wxml（结算页）

[这里粘贴wxml和js文件的完整内容]

请严格按照 TestPilot AI 小程序蓝本格式生成，遵守所有铁律。
要求：
1. 每个场景以reset_state开头
2. evaluate用IIFE格式
3. 不使用document对象
4. 选择器来自wxml中实际的id和class
5. 覆盖尽可能多的业务逻辑和边界情况
```

---

## 七、附：执行器步骤类型与执行环境对照

| 步骤类型 | 执行环境 | 能访问什么 |
|---------|---------|-----------|
| `evaluate` | 小程序端（微信JS沙箱） | `getApp()`、`wx.xxx`、`getCurrentPages()` |
| `page_query` | Node.js端（automator） | `page.$`、`page.$$`、元素的`.text()` |
| `read_text` | Node.js端（automator） | `page.$` → `.text()`，带3次重试 |
| `call_method` | automator桥接 | 调用页面实例方法 |
| `click`/`tap_multiple` | automator桥接 | `page.$` → `.tap()` |
| `navigate`/`navigate_to` | 小程序端（通过new Function） | `wx.reLaunch`/`wx.navigateTo` |
| `reset_state` | 小程序端+automator | 清全局数据+reLaunch回首页 |
| `assert_text`/`assert_compare` | Node.js端 | 读元素文本做断言 |
| `screenshot` | automator | 截图保存到screenshots目录 |

