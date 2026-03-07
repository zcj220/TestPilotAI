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
| `mp.navigateTo()` | **10秒超时** | ❌ SDK方法不可用！ |
| `mp.navigateBack()` | **10秒超时** | ❌ SDK方法不可用！ |
| `mp.reLaunch()` | **10秒超时** | ❌ SDK方法不可用！ |
| `evaluate(()=>wx.navigateTo())` | **快** (~64ms) | ✅ 用这个代替！ |
| `evaluate(()=>wx.navigateBack())` | **快** (~25ms) | ✅ 用这个代替！ |
| `evaluate(()=>wx.reLaunch())` | **快** (~41ms) | ✅ 用这个代替！ |

## 三、页面跳转的坑（重要！）

### 问题（已解决）
- SDK 的 `mp.navigateTo()`/`mp.navigateBack()`/`mp.reLaunch()` 全部**10秒超时**
- 根因：SDK 封装方法内部等待页面切换完成的机制有问题

### 解决方案（已验证）
**用 `evaluate(() => wx.xxx())` 调用原生API，完全替代 SDK 导航方法：**

```javascript
// 跳转页面
await mp.evaluate(() => { wx.navigateTo({ url: '/pages/cart/cart' }); });
await sleep(1500); // 等页面渲染

// 返回上一页
await mp.evaluate(() => { wx.navigateBack(); });
await sleep(1500);

// 清空栈回首页（最可靠）
await mp.evaluate(() => { wx.reLaunch({ url: '/pages/index/index' }); });
await sleep(1500);
```

### 示例：场景间重置（resetForNextScenario）
```javascript
async function resetForNextScenario(mp) {
  // 1. 清全局状态
  await mp.evaluate(() => {
    const g = getApp().globalData;
    g.cart = []; g.coupon = null; g.isVip = true;
  });
  // 2. reLaunch 回首页（清空页面栈，<50ms）
  const page = await mp.currentPage();
  if (page.path !== 'pages/index/index') {
    await mp.evaluate(() => { wx.reLaunch({ url: '/pages/index/index' }); });
    await sleep(1500);
  }
  // 3. 刷新首页数据
  const home = await mp.currentPage();
  await home.callMethod('onShow');
  await sleep(200);
  return home;
}
```

## 四、测试脚本结构

### 推荐结构
```javascript
// 1. 开头 close+open+auto 重启1次
execSync('cli close --project <path>');
execSync('cli open --project <path>');
execSync('cli auto --project <path> --auto-port 9420');
const mp = await automator.connect({ wsEndpoint: 'ws://localhost:9420' });

// 2. 对每个场景：
//    a. resetForNextScenario() - evaluate(wx.reLaunch)回首页+清状态
//    b. 执行测试步骤（首页操作用tap/callMethod，跳页面用evaluate(wx.navigateTo)）
//    c. 验证结果
//    d. 记录通过/失败，继续下一个场景

// 3. 场景任意顺序，靠 reLaunch 回首页，不需要调顺序

// 4. 输出 JSON 报告
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

## 六、截图功能

### 用法
```javascript
// 截取当前页面保存为PNG
await mp.screenshot({ path: 'screenshots/场景名.png' });
```

### 最佳实践
- **每个场景末尾截一张图**：留证，方便复查
- **Bug场景截图特别重要**：截图能直观看到页面状态
- 截图目录在脚本启动时自动创建
- 文件名带序号方便排序：`01_会员价格.png`, `02_库存限制.png`

### 注意
- `mp.screenshot()` 截的是**模拟器渲染的页面**，和真机一样
- 截图分辨率取决于开发者工具设置的模拟器尺寸
- 截图不会影响测试性能（<100ms）

## 七、TestPilotAI 软件针对小程序的完整流程

### 整体架构
```
用户 → VSCode插件 → Python引擎 → Node.js桥接服务器 → miniprogram-automator → 微信开发者工具
```

### 流程步骤

#### 1. 准备阶段
- 用户在VSCode中选择"小程序测试"
- 指定小程序项目路径和蓝本（testpilot.json）
- 系统自动执行 `cli close` + `cli open` + `cli auto --auto-port 9420`

#### 2. 连接阶段
- Node.js桥接服务器（`miniprogram_bridge_server.js`）启动在端口9421
- 桥接服务器连接 `ws://localhost:9420` 建立automator会话
- Python引擎通过HTTP请求与桥接服务器通信

#### 3. 蓝本解析
- 读取 `testpilot.json` 中的功能需求和测试场景
- LLM根据蓝本生成测试脚本（不知道Bug在哪）
- 测试场景包括：功能验证、边界值、溢出、异常输入等

#### 4. 执行阶段
- 每个场景前调用 `resetForNextScenario()` 重置状态
- 首页操作用 `tap()`/`callMethod()`
- 跳页面用 `evaluate(() => wx.navigateTo())`
- 回首页用 `evaluate(() => wx.reLaunch())`
- 每个场景末尾截图留证

#### 5. 报告阶段
- 输出JSON格式报告（Bug/通过/跳过）
- 截图保存到 `screenshots/` 目录
- LLM分析报告，给出Bug严重级别和修复建议

### 关键规则（必须遵守）
1. **绝不使用SDK导航方法**：`mp.navigateTo()`等全部超时，用`evaluate(wx.xxx())`
2. **开头重启1次，中途不重启**：靠`reLaunch`回首页
3. **场景独立**：每个场景开头重置全局状态
4. **截图留证**：每个场景截图
5. **失败不阻塞**：一个场景失败不影响后续场景

## 八、常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 连接超时 | 未启动 `cli auto` | `cli close` + `cli open` + `cli auto --auto-port 9420` |
| 端口连不上 | HTTP端口≠自动化端口 | 确认用 `--auto-port` 指定的端口（9420） |
| SDK导航超时 | SDK封装方法有bug | 用 `evaluate(() => wx.navigateTo())` 代替 |
| 页面残留 | 上次测试未清理 | `cli close` + `cli open` 重启 |
| 选择器找不到 | WXML结构不同 | 用 `page.$$('.class')` 获取数组再索引 |
| 购物车残留 | globalData未重置 | `evaluate(() => { getApp().globalData.cart = [] })` |
| 跳页面后操作报错 | 需等页面渲染 | `evaluate(wx.navigateTo)` 后 `await sleep(1500)` |
