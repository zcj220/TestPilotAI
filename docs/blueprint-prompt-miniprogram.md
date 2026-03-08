# TestPilot AI — 微信小程序蓝本生成提示词

> 前置条件：请先阅读 `docs/blueprint-prompt-golden-rules.md` 中的8条黄金规则。

---

## ⚠️ 小程序蓝本与Web蓝本完全不同！

小程序运行在微信开发者工具的模拟器里，没有浏览器DOM，没有document对象，导航方式、元素查找、代码执行全部不同。

---

## 小程序7条铁律（违反任何一条都会导致测试失败）

### 铁律1：evaluate 必须用 IIFE 格式

evaluate 的 value 会被 `new Function(code)` 包裹执行，所以必须是可直接执行的表达式。

```
✅ 正确：
"value": "(() => { const app = getApp(); return app.globalData.cart.length; })()"

❌ 错误：
"value": "() => getApp().globalData.cart.length"
原因：箭头函数定义不是可执行表达式，new Function包裹后不会执行
```

### 铁律2：小程序没有 document 对象

evaluate 里只能使用小程序API：

| ✅ 可用 | ❌ 不可用 |
|---------|----------|
| `getApp()` | `document.querySelector()` |
| `getCurrentPages()` | `window.location` |
| `wx.navigateTo()` | `document.getElementById()` |
| `wx.reLaunch()` | `window.alert()` |
| Page实例方法 | DOM操作 |

查找DOM元素用 `page_query` 或 `read_text`，不要在evaluate里查DOM。

### 铁律3：每个场景第一步必须是 reset_state

清空全局状态（购物车等）+ reLaunch回首页，确保场景独立：

```json
{"action": "reset_state", "description": "重置状态回首页"}
```

### 铁律4：跨页面导航用 navigate_to，不能用 navigate

```json
✅ {"action": "navigate_to", "value": "/pages/cart/cart", "description": "跳转购物车"}
❌ {"action": "navigate", "value": "http://xxx"}  ← 这是Web的写法，小程序不能用
```

### 铁律5：call_method 参数用 JSON 格式

```json
{"action": "call_method", "target": "onCategoryTap", "value": "{\"detail\": {\"dataset\": {\"cat\": \"水果\"}}}"}
```

### 铁律6：assert_compare 的 value 格式为 "操作符 期望值"

```json
{"action": "assert_compare", "target": "#cartCount", "value": "> 0"}
{"action": "assert_compare", "target": "#total", "value": "== 100"}
{"action": "assert_compare", "target": "#stock", "value": "<= 10"}
```

### 铁律7：page_query 用 value 指定返回类型

```json
{"action": "page_query", "target": ".product", "value": "count"}   → 返回元素数量
{"action": "page_query", "target": "#price", "value": "text"}      → 返回文本内容
```

---

## 支持的 action（15种）

| action | 说明 | 示例 |
|--------|------|------|
| `reset_state` | 清空全局状态+reLaunch回首页 | 每个场景第1步 |
| `navigate_to` | 跨页面导航 | `"value": "/pages/cart/cart"` |
| `click` | 点击元素 | `"target": "#addBtn"` |
| `fill` | 填写输入框 | `"target": "#searchInput", "value": "苹果"` |
| `call_method` | 调用页面方法 | `"target": "onSearch"` |
| `evaluate` | 执行JS代码 | `"value": "(() => getApp().globalData.isVip)()"` |
| `read_text` | 读取元素文本 | `"target": "#price"` |
| `assert_text` | 断言文本包含 | `"target": "#title", "expected": "首页"` |
| `assert_compare` | 数值比较断言 | `"target": "#count", "value": "> 0"` |
| `page_query` | 查询元素数量/文本 | `"target": ".item", "value": "count"` |
| `tap_multiple` | 连续点击多次 | `"target": "#addBtn", "value": "3"` |
| `screenshot` | 截图 | 无需参数 |
| `wait` | 等待毫秒 | `"value": "1000"` |
| `select` | 选择下拉项 | `"target": "#picker", "value": "选项1"` |
| `scroll` | 滚动页面 | `"value": "bottom"` |

---

## 蓝本格式

```json
{
  "app_name": "FreshMart 生鲜超市",
  "description": "小程序完整功能测试：商品浏览、分类搜索、购物车、结算、优惠券、配送方式",
  "base_url": "miniprogram://D:/projects/my-miniprogram",
  "version": "1.0",
  "platform": "miniprogram",
  "pages": [
    {
      "url": "/pages/index/index",
      "title": "首页",
      "elements": {
        "搜索框": "#searchInput",
        "商品列表": ".product",
        "加入购物车按钮": ".btn-primary",
        "购物车数量": "#cartCount"
      },
      "scenarios": [
        {
          "name": "商品列表加载验证",
          "steps": [
            {"action": "reset_state", "description": "重置状态回首页"},
            {"action": "page_query", "target": ".product", "value": "count", "expected": "4", "description": "验证商品数量"},
            {"action": "evaluate", "value": "(() => getApp().globalData.products.length)()", "expected": "4", "description": "验证数据源商品数"}
          ]
        },
        {
          "name": "加入购物车（状态变化验证）",
          "steps": [
            {"action": "reset_state", "description": "重置状态回首页"},
            {"action": "read_text", "target": "#cartCount", "expected": "0", "description": "初始购物车为空"},
            {"action": "click", "target": "#product-1 .btn-primary", "description": "点击第一个商品加入购物车"},
            {"action": "assert_compare", "target": "#cartCount", "value": "> 0", "description": "购物车数量增加"}
          ]
        }
      ]
    }
  ]
}
```

---

## 生成步骤

1. **阅读所有 `.wxml` 文件**：提取CSS选择器（id、class）
2. **阅读所有 `.js` 文件**：提取页面方法、全局数据、业务逻辑
3. **阅读 `app.js`**：提取 globalData 结构
4. **列出所有功能点**：每个按钮、每个表单、每个页面跳转
5. **按黄金规则生成蓝本**：功能全覆盖 + 操作→断言 + 流程串联 + 异常边界
6. **自检**：逐项核对黄金规则自检清单

---

## 踩坑记录（前车之鉴）

| 错误 | 原因 | 正确做法 |
|------|------|---------|
| `evaluate("字符串代码")` 报错 | mp.evaluate内部用new Function，字符串会被二次解析 | 用IIFE格式 |
| evaluate里用`document.querySelector` | 小程序没有document | 用page_query或read_text |
| `callMethod('onShow')` 超时100秒 | onShow是生命周期方法，不能直接call | 用reLaunch+sleep代替 |
| navigate到`http://xxx` | 小程序不是浏览器 | 用navigate_to + 小程序路径 |
| 场景之间数据污染 | 上一个场景的购物车数据残留 | reset_state清空globalData |
| 模拟器连不上 | cli quit在模拟器崩溃时也会失败 | taskkill强杀进程后重启 |
