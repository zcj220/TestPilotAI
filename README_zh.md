# TestPilot AI

<div align="center">

**🤖 AI 驱动的 UI 自动化测试**

*像人类一样测试 Web、移动端、桌面应用，结合 AI 视觉分析*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![Playwright](https://img.shields.io/badge/Playwright-1.40+-blue.svg)](https://playwright.dev/)

[English](README.md) | [简体中文](#)

</div>

---

## 📖 项目简介

**TestPilot AI** 是一个智能测试自动化平台，专为验证 AI 编程工具（Cursor、Windsurf 等）生成的应用代码而设计。它将**蓝本驱动测试**与**多模态 AI 视觉分析**相结合，像人类测试员一样测试应用。

### 🎯 核心特性

- 🎯 **蓝本驱动测试** - AI 编程工具生成测试蓝本（`testpilot.json`），TestPilot 精确执行
- 👁️ **AI 视觉分析** - 多模态 AI 分析截图，检测 UI Bug、布局问题、异常行为
- 🔧 **自动修复闭环** - 自动修复 Bug、重新测试、迭代直到 100% 通过率（fix-test-fix 循环）
- 🌐 **多平台支持** - Web、Android、iOS、Windows 桌面、macOS、微信小程序
- 🧠 **记忆系统** - 从测试历史中学习，在本地 SQLite 数据库中积累测试经验
- 🔌 **IDE 集成** - VSCode/Windsurf 插件，无缝工作流
- 📊 **实时监控** - WebSocket 实时日志、VNC/截图流、逐步进度跟踪

---

## 🎨 支持的平台

| 平台 | 状态 | 技术栈 | 通过率 |
|------|------|--------|--------|
| 🌐 **Web 应用** | ✅ 生产就绪 | Playwright + Docker 沙箱 | 98% |
| 📱 **Android 原生** | ✅ 生产就绪 | Appium + ADB + AI 视觉 | 95% |
| 🦋 **Flutter (Android)** | ✅ 生产就绪 | 纯 ADB + UI树/AI 双保险 | 95% |
| 💬 **微信小程序** | ✅ 生产就绪 | Playwright + 开发者工具 | 98% |
| 🖥️ **Windows 桌面** | 🔄 进行中 | pywinauto + AI 视觉 | 97% |
| 🍎 **iOS** | 📋 计划中 | Appium + WebDriverAgent | - |
| 🐧 **macOS 桌面** | 📋 计划中 | pyautogui + AI 视觉 | - |

---

## 🚀 快速开始

### 前置要求

- **Python 3.10+**
- **Poetry**（依赖管理）
- **Docker Desktop**（用于 Web 测试沙箱，移动端/桌面测试可选）

### 安装

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/TestPilotAI.git
cd TestPilotAI

# 安装依赖（自动创建虚拟环境）
poetry install

# 安装 Playwright 浏览器（用于 Web 测试）
poetry run playwright install chromium

# 配置环境变量
cp .env.example .env
# 编辑 .env 并添加你的 AI API 密钥
```

### 配置 AI 模型

TestPilot AI 使用多模态 AI 进行视觉分析。支持的提供商：

- **豆包（Doubao）** - 推荐，针对中文 UI 优化（默认）
- **OpenAI GPT-4 Vision** - 通过 OpenAI SDK 兼容
- **其他 OpenAI 兼容 API** - 任何支持视觉模型的提供商

编辑 `.env`：

```bash
TP_AI_API_KEY=your_api_key_here
TP_AI_API_BASE_URL=https://ark.cn-beijing.volces.com/api/v3  # 或 OpenAI 端点
TP_AI_MODEL=doubao-seed-1-8-251228  # 或 gpt-4-vision-preview
```

### 启动引擎

```bash
# 启动核心引擎
poetry run python main.py

# 或使用热重载模式（开发时）
poetry run uvicorn src.app:app --reload --port 8900
```

访问 **http://127.0.0.1:8900/docs** 查看交互式 API 文档。

---

## 📚 工作原理

### 1️⃣ 蓝本生成

AI 编程工具（Cursor/Windsurf）在编码时自动生成测试蓝本：

```json
{
  "app_name": "商城 Demo",
  "platform": "web",
  "base_url": "http://localhost:8080",
  "pages": [
    {
      "url": "/",
      "name": "首页",
      "scenarios": [
        {
          "name": "用户登录成功",
          "steps": [
            {"action": "navigate", "value": "/", "description": "打开首页"},
            {"action": "fill", "target": "#username", "value": "testuser"},
            {"action": "fill", "target": "#password", "value": "password123"},
            {"action": "click", "target": "#loginBtn"},
            {"action": "assert_text", "expected": "欢迎", "description": "验证登录成功"}
          ]
        }
      ]
    }
  ]
}
```

### 2️⃣ 测试执行

TestPilot 使用 **UI 树 + AI 视觉双保险**执行蓝本：

- **UI 树优先** - 快速、像素级精确的元素定位（CSS 选择器、XPath、accessibility ID）
- **AI 视觉降级** - 当 UI 树失败时，AI 分析截图通过视觉外观查找元素
- **自动滚动搜索** - 自动滚动查找屏幕外的元素

### 3️⃣ Bug 检测

多模态 AI 在每一步分析截图：

- ✅ **视觉对比** - 预期 vs 实际 UI 状态
- ✅ **文本识别** - OCR 识别错误消息、标签、按钮
- ✅ **布局分析** - 检测错位元素、重叠内容
- ✅ **异常检测** - 崩溃对话框、空白屏幕、加载动画

### 4️⃣ 自动修复闭环（可选）

发现 Bug 时，TestPilot 可以自动修复：

1. **Bug 分类** - 分类 Bug（选择器错误、逻辑 Bug、时序问题等）
2. **AI 代码修复** - 使用 AI 生成代码补丁
3. **应用补丁** - 自动将修复应用到源代码
4. **重新测试** - 再次运行测试以验证修复
5. **迭代** - 重复直到 100% 通过率

---

## 🛠️ 项目结构

```
TestPilotAI/
├── src/                          # 源代码
│   ├── core/                     # 核心基础设施
│   │   ├── config.py             # 配置管理（pydantic-settings）
│   │   ├── ai_client.py          # AI 客户端（OpenAI SDK 兼容）
│   │   └── prompts.py            # AI 提示词系统
│   ├── testing/                  # 测试执行引擎
│   │   ├── blueprint_runner.py   # Web 蓝本运行器
│   │   ├── mobile_blueprint_runner.py  # 移动端蓝本运行器
│   │   ├── desktop_blueprint_runner.py # 桌面蓝本运行器
│   │   └── ai_hub.py             # AI 视觉分析中枢
│   ├── controller/               # 平台控制器
│   │   ├── android.py            # Android 控制器（Appium + ADB）
│   │   ├── desktop.py            # 桌面控制器（pywinauto）
│   │   └── window_manager.py     # Windows 窗口管理
│   ├── memory/                   # 记忆系统
│   │   ├── store.py              # SQLite 记忆存储
│   │   └── debug_memory.py       # 调试快照存储
│   ├── repair/                   # 自动修复系统
│   │   ├── fixer.py              # AI 代码修复器
│   │   └── loop.py               # 修复-测试-修复循环编排器
│   ├── community/                # 社区经验共享
│   │   ├── store.py              # 社区经验数据库
│   │   └── anonymizer.py         # Bug 报告匿名化器
│   └── api/                      # API 层
│       ├── routes.py             # REST API 路由
│       └── websocket.py          # WebSocket 实时日志
├── extension/                    # VSCode/Windsurf 插件
│   ├── src/extension.ts          # 插件入口
│   └── src/sidebarProvider.ts    # 侧边栏 webview 面板
├── desktop/                      # 桌面应用（React + Tauri）
│   └── src/                      # React 前端
├── tests/                        # 单元测试（166 个测试）
├── main.py                       # 启动入口
├── pyproject.toml                # 项目配置和依赖
└── .env.example                  # 环境变量模板
```

---

## 📡 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| POST | `/api/v1/test/run` | **运行蓝本测试**（支持 `auto_repair` 参数） |
| POST | `/api/v1/test/mobile-blueprint` | 运行移动端蓝本测试（Android/iOS） |
| POST | `/api/v1/test/desktop-blueprint` | 运行桌面蓝本测试（Windows/macOS） |
| POST | `/api/v1/test/quick` | 快速探索测试（无需蓝本） |
| GET | `/api/v1/memory/history` | 查询测试历史 |
| GET | `/api/v1/memory/stats` | 记忆系统统计 |
| POST | `/api/v1/community/share` | 分享测试经验到社区 |
| GET | `/api/v1/community/suggest` | 获取相似 Bug 修复建议 |

完整 API 文档：**http://127.0.0.1:8900/docs**

---

## 🧪 运行测试

```bash
# 运行所有单元测试
poetry run pytest

# 运行并生成覆盖率报告
poetry run pytest --cov=src --cov-report=html

# 运行特定测试文件
poetry run pytest tests/test_blueprint_runner.py
```

---

## 🎮 IDE 插件（VSCode/Windsurf）

### 安装

1. 打开 VSCode/Windsurf
2. 从 `extension/testpilot-ai-1.0.0.vsix` 安装插件
3. 打开侧边栏面板（TestPilot 图标）

### 功能

- ✅ 一键测试执行
- ✅ 实时测试进度监控
- ✅ Bug 列表（带严重度标签）
- ✅ "发送给 AI 修复"按钮（剪贴板集成）
- ✅ 测试历史浏览
- ✅ 自动闭环模式（测试 → 修复 → 重测直到 100% 通过）

---

## 🌍 国际化

- **English** - 完全支持
- **简体中文** - 完全支持（针对中文 UI 测试优化）

---

## 🤝 贡献

欢迎贡献！请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 了解指南。

### 开发环境设置

```bash
# 安装开发依赖
poetry install --with dev

# 运行 linter
poetry run ruff check src/

# 格式化代码
poetry run black src/

# 类型检查
poetry run mypy src/
```

---

## 📜 许可证

本项目采用 **MIT 许可证** - 详见 [LICENSE](LICENSE) 文件。

---

## 🙏 致谢

- **Playwright** - Web 自动化框架
- **Appium** - 移动端自动化框架
- **FastAPI** - 现代 Python Web 框架
- **豆包（Doubao）** - 多模态 AI 模型用于视觉分析
- **OpenAI** - GPT-4 Vision API 兼容性

---

## 📧 联系方式

- **GitHub Issues** - 用于 Bug 报告和功能请求
- **Discussions** - 用于问题和社区支持

---

<div align="center">

**⭐ 如果觉得有用，请给个 Star！**

由 TestPilot AI 团队用 ❤️ 制作

</div>
