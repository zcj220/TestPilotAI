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

## 已知现象（待验证）

以下是之前在 FreshMart 项目中观察到的现象，**需要本项目验证是否可复现**：

1. **`mp.navigateBack()` 不生效**：SDK 方法执行耗时约3秒，不报错，但 `currentPage()` 仍在子页
2. **`reLaunch` 超时**：通过 `evaluate` 调用 `wx.reLaunch()` 直接超时
3. **`redirectTo` 超时**：同上
4. **`evaluate(() => wx.navigateBack())` 不生效**：在 AppService 层直接调用也不行
5. **页面栈显示正确但页面不变**：`getCurrentPages()` 返回的栈是对的，但渲染的页面没变

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
