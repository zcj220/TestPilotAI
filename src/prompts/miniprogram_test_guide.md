# 微信小程序自动化测试 - 提示词指南

> 本文档是给大模型生成小程序测试脚本时的提示词参考，包含所有经验总结。

## 一、环境启动

### 1. 启动自动化模式（必须）
```powershell
& "C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat" auto --project "<小程序项目路径>" --auto-port 9420
```
- **固定端口 9420**，脚本中硬编码此端口，用户无需手动输入
- 如果 9420 被占用，备选自动扫描：找到 `wechatdevtools.exe` 进程的 PID → 扫描其监听端口 → 逐个尝试 `ws://localhost:<port>` 连接

### 2. 连接方式
```javascript
const automator = require('miniprogram-automator');
const mp = await automator.connect({ wsEndpoint: 'ws://localhost:9420' });
```

### 3. 端口说明
- **HTTP 服务端口**（如 32815）：开发者工具设置里显示的，仅用于 CLI 命令，**不是**自动化端口
- **WebSocket 自动化端口**（如 9420）：通过 `--auto-port` 指定，用于 `miniprogram-automator` 连接
- 两者是**完全不同的端口**，不要混淆

## 二、操作速度分级（关键！）

| 操作 | 速度 | 说明 |
|------|------|------|
| `page.setData()` | **瞬间** (<10ms) | 直接修改页面数据 |
| `mp.evaluate()` | **瞬间** (<10ms) | 在 AppService 层执行 JS |
| `page.callMethod()` | **瞬间** (<10ms) | 调用页面方法 |
| `page.$()` / `page.$$()` | **快** (~50ms) | 查询元素 |
| `element.tap()` | **快** (~100ms) | 点击元素 |
| `element.text()` | **快** (~50ms) | 读取文本 |
| `mp.navigateTo()` | **慢** (~3秒) | 页面跳转 |
| `mp.navigateBack()` | **慢且不可靠** | 可能不生效！ |
| `mp.reLaunch()` | **超时** | 在自动化模式下经常超时 |
| `mp.redirectTo()` | **超时** | 同上 |

## 三、页面跳转的坑（重要！）

### 问题
- `navigateBack()` 在自动化模式下**执行但不生效**（耗时3秒，页面不变）
- `reLaunch()` 和 `redirectTo()` 在自动化模式下**超时**
- `evaluate(() => wx.navigateBack())` 也**不生效**
- 这不是微信的 Bug，是 miniprogram-automator SDK 的限制

### 解决方案
1. **尽量避免页面跳转**：用 `callMethod()` 替代跳转到其他页面再操作
   - 例：不需要跳到购物车页面再结算，直接 `page.callMethod('checkout')` 在当前页面调用
2. **用 `setData` + `evaluate` 重置状态**：代替 `reLaunch` 重新加载页面
   ```javascript
   await mp.evaluate(() => { getApp().globalData.cart = []; });
   await page.setData({ cartCount: 0, cartTotal: '0', message: '' });
   ```
3. **会跳转页面的场景放最后执行**
4. **跳转失败则跳过记录原因**，不阻塞后续场景

### 示例：ensureHomePage
```javascript
async function ensureHomePage(mp) {
  let page = await mp.currentPage();
  if (page.path === 'pages/index/index') return page;
  // 尝试 navigateBack（最多2次，每次等3秒）
  for (let i = 0; i < 2; i++) {
    try {
      await mp.navigateBack();
      await sleep(3000);
      page = await mp.currentPage();
      if (page.path === 'pages/index/index') return page;
    } catch (e) { break; }
  }
  throw new Error(`无法回到首页，当前在 ${page.path}`);
}
```

## 四、测试脚本结构

### 推荐结构
```javascript
// 1. 连接（固定端口9420）
const mp = await automator.connect({ wsEndpoint: 'ws://localhost:9420' });

// 2. 对每个场景：
//    a. ensureHomePage() - 确保在首页
//    b. resetState() - 用 setData+evaluate 重置数据
//    c. 执行测试步骤
//    d. 验证结果
//    e. 如果失败，记录原因，继续下一个场景

// 3. 场景排序策略：
//    - 不跳转页面的场景先执行
//    - 会跳转页面的场景放最后
//    - 每个场景独立，不依赖前一个场景的状态

// 4. 输出 JSON 报告（给大模型分析）
```

### 元素选择器
- 小程序 WXML 中，`wx:for` 生成的元素用 `.class:nth-child(n)` 选择
- `.btn-primary` 获取所有按钮后用数组索引区分：`btns[0]`=第1个, `btns[1]`=第2个...
- ID 选择器直接用：`#price-1`, `#cartTotal`, `#message`
- 兄弟选择器 `#id ~ .class` 在小程序中**不可靠**

## 五、失败处理策略

### 原则
1. **走不通就跳过，记录原因，继续下一个**
2. **所有结果（成功/失败/跳过）汇总成 JSON 反馈**
3. **大模型收到反馈后可以：**
   - 调整蓝本步骤（比如改用 callMethod 替代页面跳转）
   - 修改选择器（页面结构变了）
   - 调整场景顺序（避免跳转影响）

### JSON 报告格式
```json
{
  "summary": { "total": 4, "bugs": 4, "passed": 0, "skipped": 0 },
  "bugs": [{
    "scenario": "Bug名称",
    "type": "数据不一致|计算错误|缺少输入验证|业务逻辑错误",
    "message": "具体描述",
    "severity": "high|medium|low",
    "steps": [{ "action": "做了什么", "result": "结果" }]
  }],
  "skipped": [{
    "scenario": "跳过的场景",
    "reason": "跳过原因（如：无法回到首页）"
  }]
}
```

## 六、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 连接超时 | 未启动 `cli auto` | 运行 `cli auto --auto-port 9420` |
| 端口连不上 | HTTP端口≠自动化端口 | 确认用 `--auto-port` 指定的端口 |
| navigateBack 不生效 | SDK 限制 | 用 setData/evaluate 重置，或跳过 |
| 选择器找不到元素 | WXML 结构不同 | 用 `page.$$('.class')` 获取数组再索引 |
| 页面空白 | 之前测试把页面搞坏 | 在开发者工具中点编译，或 `cli auto` 重启 |
| 购物车数据残留 | globalData 未重置 | `mp.evaluate(() => { getApp().globalData.cart = [] })` |
