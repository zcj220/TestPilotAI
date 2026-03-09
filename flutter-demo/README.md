# Flutter Demo — TestPilot Android 原生测试示例

一个简单的 Flutter Task Manager 应用，**预埋了 4 个 Bug**，用于演示 TestPilot AI 对原生 Android APP 的自动化测试能力。

---

## 预埋 Bug 清单

| Bug   | 位置         | 描述                                     | 蓝本可检测 |
|-------|------------|------------------------------------------|---------|
| Bug-1 | 登录页       | 空用户名+密码可以直接登录（无输入验证）          | ✅ auth  |
| Bug-2 | 登录页       | 密码框未开启 `obscureText`，密码明文可见     | ✅ auth  |
| Bug-3 | 任务列表页   | "待办"计数显示总任务数，非未完成数             | ✅ tasks |
| Bug-4 | 任务列表页   | 删完所有任务后触发数组越界（_selected 未重置） | ✅ tasks |

---

## 环境准备（一次性）

### 1. 安装 Flutter SDK

```powershell
# 方式1：官方安装包
# https://docs.flutter.dev/get-started/install/windows

# 方式2：使用 winget
winget install Google.Flutter
```

验证安装：
```powershell
flutter doctor
```
确保 "Android toolchain" 和 "Connected device" 都是绿色 ✓

### 2. 开启手机开发者模式 + USB 调试

1. 设置 → 关于手机 → 连续点击"版本号" 7 次
2. 设置 → 开发者选项 → 打开 USB 调试
3. 用 USB 连接电脑，选择"文件传输"模式
4. 验证连接：`adb devices`（应显示你的设备）

### 3. 安装 Appium + UiAutomator2 驱动

```powershell
npm install -g appium
appium driver install uiautomator2
```

验证：`appium driver list --installed`

---

## 构建并安装 APK

### 第一次初始化（只需一次）

```powershell
cd D:\Projects\TestPilotAI

# 用 flutter create 生成 Android 样板（org 必须是 com.testpilot）
flutter create flutter_demo --org com.testpilot --project-name flutter_demo
cd flutter_demo

# 把我们的代码文件覆盖进去
# （flutter create 生成了 android/ 框架，我们的 lib/ 是实际代码）
```

或者直接在 `flutter-demo` 目录里初始化：
```powershell
cd D:\Projects\TestPilotAI\flutter-demo
flutter create . --org com.testpilot --project-name flutter_demo
flutter pub get
```

### 构建 Debug APK

```powershell
cd D:\Projects\TestPilotAI\flutter-demo
flutter build apk --debug
```

输出路径：`build/app/outputs/flutter-apk/app-debug.apk`

### 安装到手机

```powershell
adb install build/app/outputs/flutter-apk/app-debug.apk
```

---

## 运行 TestPilot 测试

### 步骤 1：启动 TestPilot 引擎

```powershell
cd D:\Projects\TestPilotAI
poetry run python main.py
```

### 步骤 2：启动 Appium Server

新开一个终端：
```powershell
appium server --port 4723
```

### 步骤 3：通过 TestPilot 插件或 API 测试

**方式 A：VS Code 插件（推荐）**
1. 打开 TestPilot 侧边栏
2. 切换到 Android 平台
3. 点击"创建设备会话"，填入：
   - App Package: `com.testpilot.flutter_demo`
   - App Activity: `.MainActivity`
4. 在蓝本列表中选 `flutter-demo/testpilot/auth.testpilot.json`
5. 点击"运行测试"

**方式 B：直接调用 API**
```powershell
# 1. 创建 Android 会话（会自动启动手机上的 APP）
$session = Invoke-RestMethod -Method Post -Uri "http://localhost:8900/api/v1/mobile/session/create" `
  -ContentType "application/json" `
  -Body '{"app_package":"com.testpilot.flutter_demo","app_activity":".MainActivity"}'
$sid = $session.session_id
Write-Host "Session ID: $sid"

# 2. 运行登录蓝本
Invoke-RestMethod -Method Post -Uri "http://localhost:8900/api/v1/test/mobile-blueprint" `
  -ContentType "application/json" `
  -Body "{`"mobile_session_id`":`"$sid`",`"blueprint_path`":`"D:/Projects/TestPilotAI/flutter-demo/testpilot/auth.testpilot.json`"}"

# 3. 运行任务蓝本
Invoke-RestMethod -Method Post -Uri "http://localhost:8900/api/v1/test/mobile-blueprint" `
  -ContentType "application/json" `
  -Body "{`"mobile_session_id`":`"$sid`",`"blueprint_path`":`"D:/Projects/TestPilotAI/flutter-demo/testpilot/tasks.testpilot.json`"}"
```

---

## Appium 元素选择器速查

Flutter + UiAutomator2 选择器规则：

| 元素类型           | 选择器示例                                              |
|------------------|---------------------------------------------------------|
| 文本输入框（第1个） | `//android.widget.EditText[@index='0']`                |
| 文本输入框（hint）  | `//android.widget.EditText[@hint='tf_username']`       |
| 带语义标签的按钮    | `accessibility_id:btn_login`                            |
| 带语义标签的文本    | `accessibility_id:txt_pending`                          |
| 带语义标签的按钮    | `//android.widget.Button[@content-desc='btn_login']`   |
| 复选框             | `accessibility_id:chk_task_0`                           |
| 删除按钮（第N个）  | `accessibility_id:btn_delete_0`                         |

### 调试选择器

如果某个元素找不到，可以用 Appium Inspector 查看布局树：
1. 下载 [Appium Inspector](https://github.com/appium/appium-inspector/releases)
2. 连接 Appium Server
3. 点击"Start Session"查看 UI 层级树
4. 找到目标元素的 `resource-id` 或 `content-desc`

---

## 目录结构

```
flutter-demo/
  lib/
    main.dart           # 应用入口 + 路由
    login_screen.dart   # 登录页（Bug-1, Bug-2）
    tasks_screen.dart   # 任务列表（Bug-3, Bug-4）
  pubspec.yaml
  testpilot/
    auth.testpilot.json   # 登录模块测试蓝本（4个场景）
    tasks.testpilot.json  # 任务模块测试蓝本（5个场景）
  README.md
```
