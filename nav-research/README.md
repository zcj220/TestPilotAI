# 微信小程序导航研究项目

## 研究目的

在使用 `miniprogram-automator` SDK 对微信小程序进行自动化测试时，发现**页面跳转后无法可靠返回**的问题。具体表现：

- `navigateBack()` 执行不报错，但页面没有回退
- `reLaunch()` 超时
- `redirectTo()` 超时
- `wx.navigateBack({delta:10})` 通过 `evaluate` 调用也不生效

这导致自动化测试中，**如果一个场景跳转到了其他页面，后续场景无法回到首页**，只能通过 `cli auto` 重启整个小程序（约5秒），非常低效。

**本项目的目标是：系统性测试各种导航方式，找出可靠的页面回退方案。**

## 项目结构

```
nav-research/
├── app.js                  # 全局（极简）
├── app.json                # 2个页面: home + sub
├── project.config.json     # 微信开发者工具配置
├── pages/
│   ├── home/               # 首页（起点）
│   │   ├── home.js         # 有跳转、reLaunch、redirectTo按钮
│   │   ├── home.wxml
│   │   ├── home.wxss
│   │   └── home.json
│   └── sub/                # 子页（目标页）
│       ├── sub.js          # 有各种返回方式按钮 + 显示页面栈
│       ├── sub.wxml
│       ├── sub.wxss
│       └── sub.json
├── test_nav.js             # 自动化测试脚本（核心）
└── README.md               # 本文件
```

## 环境要求

- 微信开发者工具（已安装，任意版本）
- Node.js（已安装）
- `miniprogram-automator` npm 包

## 使用方法

### 第1步：安装依赖

```bash
npm install miniprogram-automator
```

### 第2步：用微信开发者工具打开项目

把 `nav-research` 文件夹用微信开发者工具导入/打开。AppID 用测试号即可。

### 第3步：启动自动化模式

```powershell
& "C:\Program Files (x86)\Tencent\微信web开发者工具\cli.bat" auto --project "你的完整路径\nav-research" --auto-port 9420
```

注意：
- `--auto-port 9420` 是**固定**的 WebSocket 自动化端口，不是开发者工具设置里显示的 HTTP 服务端口（如32815）
- 两者完全不同，不要混淆

### 第4步：运行测试

```bash
node test_nav.js
```

可以**反复运行**，每次看结果。如果卡住了，重新执行第3步的 `cli auto` 命令。

## 测试用例说明

`test_nav.js` 包含 **8个测试**，覆盖所有已知的导航方式：

| # | 测试名 | 操作 | 验证 |
|---|--------|------|------|
| 1 | navigateBack 基本 | home→sub→`mp.navigateBack()` | 是否回到 home |
| 2 | navigateBack 2层 | home→sub→sub→`mp.navigateBack()` | 是否回到第1个 sub |
| 3 | navigateBack delta=10 | home→sub→sub→`evaluate(wx.navigateBack({delta:10}))` | 是否一次回到 home |
| 4 | reLaunch | home→sub→`evaluate(wx.reLaunch({url:'/pages/home/home'}))` | 是否清空栈回 home |
| 5 | redirectTo | home→sub→`evaluate(wx.redirectTo({url:'/pages/home/home'}))` | 是否替换当前页为 home |
| 6 | SDK navigateBack | home→sub→`mp.navigateBack()` | SDK封装方法是否可靠 |
| 7 | 重复跳转返回×10 | 循环10次 home→sub→back | 成功率（10/10?） |
| 8 | 不同等待时间 | 跳转后分别等100ms/500ms/1s/2s/3s/5s再返回 | 等待时间是否影响成功率 |

## ✅ 已解决！关键发现（2026-03-07）

**问题根因已找到：SDK 封装的导航方法全部超时，但 `evaluate` 调用 `wx` 原生API 又快又稳！**

| 方式 | 耗时 | 结果 |
|------|------|------|
| `mp.navigateTo('/pages/xxx')` SDK方法 | 10秒超时 | ❌ |
| `mp.navigateBack()` SDK方法 | 10秒超时 | ❌ |
| `mp.reLaunch('/pages/xxx')` SDK方法 | 10秒超时 | ❌ |
| `mp.evaluate(() => wx.navigateTo({url:'/pages/xxx'}))` | **64ms** | ✅ |
| `mp.evaluate(() => wx.navigateBack())` | **25ms** | ✅ |
| `mp.evaluate(() => wx.reLaunch({url:'/pages/xxx'}))` | **41ms** | ✅ |

### 正确用法

```javascript
// ❌ 错误：SDK 方法会超时
await mp.navigateTo('/pages/sub/sub');
await mp.navigateBack();
await mp.reLaunch('/pages/home/home');

// ✅ 正确：evaluate 调用原生 API
await mp.evaluate(() => { wx.navigateTo({ url: '/pages/sub/sub' }); });
await sleep(1500); // 等页面渲染
await mp.evaluate(() => { wx.navigateBack(); });
await sleep(1500);
await mp.evaluate(() => { wx.reLaunch({ url: '/pages/home/home' }); });
await sleep(1500);
```

### 场景间重置的最佳方案

```javascript
async function resetToHome() {
  // 1. 清全局状态
  await mp.evaluate(() => {
    const g = getApp().globalData;
    g.cart = []; g.xxx = null; // 按需清理
  });
  // 2. reLaunch 回首页（清空页面栈）
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

### 实测结果

使用上述方案，FreshMart 盲测 7 个场景（含多次跳转购物车、结算页并回退）全部跑通，**开头只重启1次，中途0次重启**，总耗时31.8秒，发现5/6个Bug。

## 原始现象（已解释）

以下现象的根因都是 **SDK 封装方法内部等待页面切换完成的机制有问题**，导致超时：

1. **`mp.navigateBack()` 不生效**：SDK 方法10秒超时，实际页面可能已回退但SDK没检测到
2. **`mp.reLaunch()` 超时**：同上
3. **`mp.redirectTo()` 超时**：同上
4. **`evaluate(() => wx.xxx())` 有效**：绕过SDK的等待机制，直接调用原生API

## 研究方向

如果以上问题确认存在，请尝试以下方向：

### 方向A：时间相关
- 跳转后等更长时间再返回（比如等5秒、10秒）
- 返回后等更长时间再检查页面

### 方向B：调用方式
- 对比 `mp.navigateBack()` 和 `evaluate(() => wx.navigateBack())`
- 尝试 `page.callMethod('goBack')` 调用页面自己的方法
- 尝试在 `evaluate` 中用 Promise/callback 方式

### 方向C：页面栈状态
- 在不同栈深度（1层、2层、5层）测试
- 在跳转过程中（navigateTo 还没完成时）就尝试返回
- 检查 `getCurrentPages()` 的返回值是否准确

### 方向D：automator SDK 版本/配置
- 检查 `miniprogram-automator` 版本
- 尝试不同的 `wsEndpoint` 配置
- 尝试 `connect` 时传入不同参数

### 方向E：开发者工具设置
- 代理设置：改为"不使用任何代理"
- 安全设置：确认服务端口已开启
- 自动化端口：尝试不同端口号

## 期望输出

运行 `test_nav.js` 后会输出：

1. **每个测试的结果**：✅成功 / ❌失败 + 详细信息 + 耗时
2. **汇总报告**：成功/失败数量
3. **JSON格式数据**：方便程序化分析

示例输出：
```
  ✅ navigateBack基本: 回到pages/home/home (1523ms)
  ❌ reLaunch: 回到pages/sub/sub (3012ms)
  ✅ 重复跳转返回x10: 10/10成功 (0ms)
  ...
  ✅ 12/16 成功 | ❌ 4/16 失败
```

## 最终目标

找到一种**可靠、快速（<1秒）的方式**让自动化脚本从任意页面回到首页，替代目前的 `cli auto` 重启方案（5秒）。
