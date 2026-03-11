# TestPilot AI

> AI驱动的自动化测试机器人 — 像人类一样操作UI、发现Bug、自动修复。

## 项目简介

TestPilot AI 是一个智能测试自动化平台，专为验证 AI 编程工具生成的应用代码而设计。它能够：

- 🤖 **模拟人类操作** — 在隔离的 Docker 沙箱中自动点击、输入、滚动
- 🔍 **智能发现Bug** — 通过多模态AI分析截图，对比预期结果与实际结果
- 🔧 **自动修复** — 将Bug报告交给编程AI自动修复，修复后自动重测
- 🧠 **记忆系统** — 压缩存储测试历史，持续积累测试经验

## 技术栈

| 层级 | 技术 |
|------|------|
| 核心引擎 | Python 3.10+ / FastAPI / Uvicorn |
| 浏览器自动化 | Playwright |
| 沙箱隔离 | Docker / AIO Sandbox |
| AI分析 | Doubao-Seed-1.8（方舟平台 / OpenAI SDK 兼容） |
| 记忆系统 | SQLite（轻量级本地存储，零外部依赖） |
| IDE插件 | TypeScript / VSCode Extension API (计划中) |
| 桌面应用 | Tauri / React / TypeScript (计划中) |

## 快速开始

### 前置要求

- Python 3.10+
- Poetry (包管理)
- Docker Desktop (沙箱运行)

### 安装

```bash
# 克隆项目
git clone <repo-url>
cd TestPilotAI

# 安装依赖（自动创建虚拟环境）
poetry install

# 安装 Playwright 浏览器
poetry run playwright install chromium

# 复制环境变量配置
cp .env.example .env
# 编辑 .env 填入你的 API 密钥
```

### 启动服务

```bash
# 启动核心引擎
poetry run python main.py

# 或使用热重载模式（开发时）
poetry run uvicorn src.app:app --reload --port 8900
```

### 访问 API 文档

启动后访问 http://127.0.0.1:8900/docs 查看交互式 API 文档。

### 运行测试

```bash
poetry run pytest
```

## 项目结构

```
TestPilot AI/
├── src/                    # 源代码
│   ├── __init__.py         # 包定义和版本号
│   ├── app.py              # FastAPI 应用工厂
│   ├── core/               # 核心基础设施
│   │   ├── config.py       # 配置管理（pydantic-settings）
│   │   ├── logger.py       # 日志系统（loguru）
│   │   ├── exceptions.py   # 异常体系
│   │   ├── ai_client.py    # AI 客户端（OpenAI SDK → 方舟平台）
│   │   └── prompts.py      # AI 提示词系统
│   ├── testing/            # 测试执行引擎（v0.2）
│   │   ├── models.py       # 测试数据模型（步骤/结果/报告/Bug）
│   │   ├── parser.py       # AI输出解析器（JSON提取+校验）
│   │   ├── orchestrator.py # 测试编排引擎（核心大脑）
│   │   └── cross_validator.py # 交叉验证引擎（多轮分析+置信度聚合）
│   ├── memory/             # 记忆系统（v0.3）
│   │   └── store.py        # SQLite 记忆存储（历史/经验/指纹）
│   ├── repair/             # 自动修复闭环（v0.4）
│   │   ├── models.py       # 修复数据模型（补丁/方案/报告）
│   │   ├── fixer.py        # AI 代码修复引擎（Bug分类+方案生成）
│   │   ├── patcher.py      # 补丁应用与回滚器
│   │   └── loop.py         # 修复闭环编排（修复→应用→重测→验证）
│   ├── sandbox/            # Docker 沙箱管理
│   │   └── manager.py      # 沙箱生命周期管理器
│   ├── browser/            # 浏览器自动化
│   │   └── automator.py    # Playwright 自动化引擎
│   └── api/                # API 层
│       ├── models.py       # 请求/响应数据模型
│       ├── routes.py       # 路由定义
│       ├── websocket.py    # WebSocket 连接管理器（实时推送测试进度）
│       └── vnc.py          # VNC实时观看+截图流降级方案（v0.7）
├── billing/                # 积分计量系统（v0.7+v1.0）
│   ├── models.py           # 积分模型（操作类型/费用表/账单）
│   ├── tracker.py          # 积分追踪器
│   ├── plans.py            # 订阅方案（免费/基础/专业/团队）+ 用户账户模型
│   └── auth.py             # 用户认证（注册/登录/API Key/积分管理）
├── extension/              # VSCode/Windsurf 插件（v0.5）
│   ├── src/
│   │   ├── extension.ts    # 插件入口（命令注册/激活）
│   │   ├── engineClient.ts # HTTP+WebSocket 通信客户端
│   │   └── sidebarProvider.ts # 侧边栏 Webview 面板
│   ├── resources/          # 图标资源
│   ├── package.json        # 插件清单（命令/菜单/配置项）
│   └── tsconfig.json       # TypeScript 配置
├── desktop/                # 桌面应用前端（v0.6）
│   ├── src/
│   │   ├── lib/engineClient.ts  # HTTP+WebSocket 通信层
│   │   ├── components/AppLayout.tsx # 主布局（侧边栏导航）
│   │   └── pages/              # 页面组件
│   │       ├── TestPage.tsx    # 测试配置页（首页）
│   │       ├── RunningPage.tsx # 实时测试面板
│   │       ├── HistoryPage.tsx # 历史记录页
│   │       └── SettingsPage.tsx # 设置页
│   ├── package.json        # 依赖配置
│   └── vite.config.ts      # Vite 配置（含代理转发）
├── tests/                  # 单元测试（166个）
├── data/                   # 运行时数据（截图、录屏）
├── logs/                   # 日志文件
├── main.py                 # 启动入口
├── pyproject.toml          # 项目配置和依赖
├── poetry.lock             # 依赖锁定文件
├── .env.example            # 环境变量模板
└── .gitignore              # Git 忽略规则
```

## API 端点概览

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v1/health` | 健康检查 |
| POST | `/api/v1/sandbox/create` | 创建测试沙箱 |
| GET | `/api/v1/sandbox/{id}/status` | 获取沙箱状态 |
| POST | `/api/v1/sandbox/{id}/exec` | 在沙箱内执行命令 |
| GET | `/api/v1/sandbox/{id}/logs` | 获取沙箱日志 |
| DELETE | `/api/v1/sandbox/{id}` | 销毁沙箱 |
| GET | `/api/v1/sandbox` | 列出所有沙箱 |
| POST | `/api/v1/browser/launch` | 启动浏览器 |
| POST | `/api/v1/browser/navigate` | 页面导航 |
| POST | `/api/v1/browser/click` | 点击元素 |
| POST | `/api/v1/browser/fill` | 输入文本 |
| POST | `/api/v1/browser/screenshot` | 截图 |
| POST | `/api/v1/browser/close` | 关闭浏览器 |
| POST | `/api/v1/test/run` | **启动AI自动化测试任务（支持auto_repair参数）** |
| GET | `/api/v1/memory/history` | 查询测试历史记录 |
| GET | `/api/v1/memory/stats` | 记忆系统统计信息 |
| GET | `/api/v1/memory/page/{url}` | 查询页面历史测试信息 |

## 支持的测试平台

| 平台 | 状态 | 方案 |
|------|------|------|
| **Web 应用** | ✅ 已验证 | Playwright + Docker 沙箱 |
| **微信小程序** | ✅ 已验证 | Playwright + 小程序开发者工具 |
| **Android 原生** | ✅ 已验证 | Appium + adb + AI视觉 |
| **Flutter Android** | ✅ 已验证（95%通过率） | 纯adb方案 + UI树/AI双保险 |
| **Windows 桌面** | 🔄 进行中 | pywinauto + AI视觉 |
| **iOS** | 📋 计划中 | Appium + WebDriverAgent |
| **macOS 桌面** | 📋 计划中 | pyautogui + AI视觉 |

## 开发路线图

- [x] **v0.1** — 基础骨架（FastAPI + Docker沙箱 + Playwright）
- [x] **v0.2** — 测试执行能力（AI生成脚本 + 截图视觉分析 + Bug检测 + 报告生成）
- [x] **v0.3** — 交叉验证 + SQLite 记忆系统（测试历史/经验/页面指纹）
- [x] **v0.4** — 自动修复闭环（Bug分类+AI代码修复+补丁应用/回滚+重测验证）
- [x] **v0.5** — IDE 插件（VSCode/Windsurf Extension + 侧边栏 + 命令面板 + 右键菜单 + WebSocket实时通信）
- [x] **v0.6** — 桌面应用（React+TailwindCSS+Vite 前端，待套Tauri壳打包）
- [x] **v0.7** — 可视化与体验优化（实时日志推送+VNC/截图流实时观看+积分计量系统）
- [x] **v1.0** — 正式发布（商业化积分系统+用户认证+帮助文档+完整功能闭环）
- [x] **v1.1** — 移动端测试（Android原生+Flutter | Appium+adb+AI视觉双保险 | 输入法兼容）
- [ ] **v1.2** — 原生Android验证 + Web/小程序UI树兜底增强
- [ ] **v1.3** — Windows桌面测试验证 + macOS支持
- [ ] **v1.4** — 社区经验库（用户授权上传测试经验，众包测试知识共享）
- [ ] **v1.5** — 自动闭环增强（插件一键启动引擎 + 自动测试→修复→重测循环）
- [ ] **v2.0** — iOS支持 + 云端部署 + 团队协作

## 社区经验库（v1.4 规划）

TestPilot AI 计划建立众包测试知识库：
- **用户授权上传**：测试100%通过后，经用户同意自动上传蓝本和测试经验
- **智能匹配**：新用户遇到相似问题时，自动推荐已验证的解决方案
- **按平台/框架分类**：Android/iOS/Web × Flutter/Native/React Native
- **隐私保护**：仅上传脱敏后的测试模式，不上传业务数据

## 许可证

本项目为闭源商业软件。所有权利保留。
