# TestPilot AI — 编程AI蓝本自动生成规则

> 本文件由 TestPilot AI 插件自动注入，指导编程AI在开发过程中自动生成和维护测试蓝本。
> 你可以根据项目需求自由修改本文件内容。

---

## 零、平台识别规则（写蓝本前必须先确定 platform）

**在 platform 确定之前，禁止生成任何蓝本内容。** 错误的 platform 会导致规则、选择器、动作全部用错，整个蓝本无法运行。

### 识别顺序（按优先级从高到低）

1. **检查已有蓝本** — 读 `testpilot/*.json`，看 `platform` 字段；**但必须与代码特征核对（见下表）**，若明显矛盾则以代码为准并纠正
2. **检查代码文件特征**（唯一客观依据）：

| 文件/特征 | platform |
|-----------|----------|
| `pubspec.yaml` / `AndroidManifest.xml` / `*.kt` / `*.java` | `android` |
| `*.xcodeproj` / `*.swift` / `Info.plist` | `ios` |
| `app.json` + `pages/` 目录（小程序结构） | `miniprogram` |
| `*.xaml` / `*.wxs` / `tkinter` / `pywinauto` / Electron + `BrowserWindow` | `desktop` |
| `package.json` + `*.html` / React / Vue / Angular / 纯HTML | `web` |

3. **读 `testpilot/CHANGELOG.md`**（如存在）— 里面可能已注明平台
4. **以上都无法确定 → 停下来，明确问用户**：「这个项目是 Web / Android / iOS / 小程序 / 桌面应用 中的哪一种？」

### 发现平台写错了，如何纠正

- 发现已有蓝本的 `platform` 与代码特征矛盾 → **立即停止**，告知用户「检测到蓝本 platform 字段为 xxx，但项目代码特征显示应为 yyy，已自动修正」
- 修正步骤：① 更新所有蓝本的 `platform` 字段 ② 重读正确平台规则文件 ③ 检查选择器/动作是否需要同步修改
- **不要沉默地继续写错误的蓝本**

### 空项目或无法判断时的处理规则

1. **项目完全为空**（无任何源码文件）→ **不写蓝本，静默等待**。空项目没有可测功能，无需操作，也不要打扰用户。
2. **代码特征模糊**（如只有 README、配置文件，看不出平台）→ 同上，继续等待直到出现明确的代码文件。
3. **用户描述与代码矛盾** → 以代码为准。用户说"这是 Android 项目"但目录里只有 `index.html` → 判断为 web，告知用户。

**已生成错误蓝本后如何纠正：**
1. 你发现代码特征与蓝本 `platform` 矛盾（如蓝本写 `"platform": "web"` 但项目有 `AndroidManifest.xml`）
2. **主动告知用户**：「检测到蓝本 platform=web，但项目代码显示应为 android，正在自动修正」
3. 自动执行：修改所有蓝本的 `platform` 字段 → 重读 `.testpilot/platforms/android.md` → 检查所有选择器和动作是否符合 android 规范 → 修正不符规范的部分
4. **不需要等用户确认，直接修正并告知结果**

---

## 一、蓝本自动生成（最重要）

当项目中**不存在** `testpilot.json` 或 `testpilot/` 目录时，你在完成功能开发后**必须**自动生成蓝本文件。

### 生成时机

| 时机 | 动作 |
|------|------|
| 新项目创建完成 | 生成完整蓝本，覆盖所有已实现功能 |
| 新增一个完整功能模块 | 在蓝本中追加对应场景 |
| 项目初始蓝本不存在 | 扫描现有代码，生成功能全覆盖的蓝本 |

### 生成规则

1. 蓝本文件固定命名 `testpilot.json`，放在项目根目录或 `testpilot/` 子目录下
2. 必须覆盖项目的**所有用户可交互功能**，不允许遗漏
3. 每个功能模块对应一个 `page`，每个用户场景对应一个 `scenario`
4. 如果项目功能较多，按功能模块拆分为多个蓝本文件放在 `testpilot/` 目录下：
   - 命名格式：`testpilot/功能模块名.testpilot.json`（用英文）
   - 拆分原则：每个独立功能模块一个文件（如：登录注册、核心业务、设置管理等）
   - 由你根据项目实际代码结构自主决定如何拆分和命名
5. 每个蓝本必须包含 `app_name`、`description`、`platform`、`base_url` 字段
6. **场景自包含原则（极其重要）**：每个 scenario 必须能独立运行，不依赖前一个场景的状态
   - 开启 `"flow": true` 的页面除外（场景间连续执行，不重启应用）
   - 每个场景的第一步必须是 `navigate` 到起始页面
   - 引擎会在每个场景开始前自动清除 cookie/storage，确保干净状态
   - 禁止场景间传递状态（如场景1登录后场景2直接操作已登录页面）
   - 正确写法示例：
     ```
     场景1： navigate→填用户名→填密码→点登录→断言成功
     场景2： navigate→填用户名→填错密码→点登录→断言失败
     场景3： navigate→点注册链接→填注册信息→点注册→断言成功
     ```
   - 错误写法（禁止）：
     ```
     场景1： navigate→登录成功
     场景2： 点退出→填错密码→登录  ← 依赖场景1已登录，禁止！
     ```

---

## 二、蓝本增量维护（日常开发）

当项目已有蓝本文件时，以下6种代码变更**必须**同步更新蓝本：

| # | 触发条件 | 蓝本更新动作 |
|---|---------|------------|
| 1 | 新增/删除 UI 元素 | 添加/删除对应场景和步骤 |
| 2 | 修改元素 id/class/选择器 | 更新蓝本中所有用到该选择器的 `target` |
| 3 | 修改文本内容（按钮文字/提示/错误信息） | 更新 `assert_text` 的 `expected` |
| 4 | 修改业务逻辑（表单验证/跳转/计算） | 更新断言和预期结果 |
| 5 | 修复 Bug | 更新蓝本中对应断言，确保能检测到该Bug |
| 6 | 修改应用配置（URL/端口/路由/启动命令） | 更新 `base_url` / `start_command` |

**不触发更新的情况**：纯CSS样式调整、代码注释修改、内部重构（不影响用户可见行为）、测试文件修改。

---

## 三、蓝本基本结构

```json
{
  "app_name": "应用名称",
  "description": "应用功能的完整描述（50-200字）",
  "base_url": "http://localhost:3000",
  "platform": "web",
  "start_command": "npm start",
  "start_cwd": ".",
  "pages": [
    {
      "url": "/",
      "name": "首页",
      "scenarios": [
        {
          "name": "场景名称",
          "description": "测试目标",
          "steps": [
            {"action": "navigate", "value": "/", "description": "打开首页"},
            {"action": "fill", "target": "#username", "value": "testuser", "description": "在用户名输入框输入"},
            {"action": "click", "target": "#loginBtn", "description": "点击登录按钮"},
            {"action": "assert_text", "expected": "欢迎", "description": "验证登录成功显示欢迎信息"},
            {"action": "screenshot", "description": "登录成功后的页面"}
          ]
        }
      ]
    }
  ]
}
```

### platform 取值

| 值 | 适用场景 |
|----|---------|
| `web` | 网页应用（React/Vue/Angular/纯HTML） |
| `desktop` | Windows桌面应用（需额外填 `window_title`） |
| `android` | Android应用（需额外填 `app_package`、`app_activity`） |
| `ios` | iOS应用（需额外填 `bundle_id`） |
| `miniprogram` | 微信小程序（`base_url` 格式为 `miniprogram://项目路径`） |

### 步骤动作

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `screenshot` | `description` | 截图 |
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `wait` | `description` | 等待（可用 `value` 指定毫秒） |
| `navigate` | `value`(URL), `description` | 页面跳转 |

### target 写法

- **Web/小程序**：CSS选择器，如 `#loginBtn`、`.submit-btn`、`input[name="email"]`
- **桌面应用**：`name:屏幕上可见的原文`，如 `name:Login`、`name:确定`
  - ⚠️ **禁止**在 `name:` 后加中文后缀（按钮/输入框/列表项等）
- **Android/iOS**：`accessibility_id:xxx` 或 `id:xxx`

### description 最佳实践

每个步骤的 `description` 应包含：
1. **位置**：上方/下方/左侧/右侧
2. **预期变化**：点击后页面会发生什么（编程AI已读过源码，应预测页面变化）

```
✅ "点击提交按钮，点击后表单数据提交到后端，页面显示'提交成功'提示"
❌ "点击按钮"
```

---

## 四、边写代码边维护蓝本（推荐工作流）

**最佳实践**：不要等项目全部写完才生成蓝本，而是**每实现一个功能就追加一个场景**。

```
实现登录功能 → 立即在蓝本中添加"登录成功"和"登录失败"两个场景
实现商品列表 → 立即添加"商品展示"和"搜索过滤"场景
实现购物车   → 立即添加"加入购物车"和"修改数量"和"删除商品"场景
```

这样做的好处：
- 功能不会遗漏（写一个测一个）
- 蓝本的选择器和预期值一定是准确的（刚写完代码，记忆最清晰）
- 用户随时可以跑测试验证

---

## 五、蓝本自检清单

生成或修改蓝本后，逐项检查：

- [ ] 所有用户可交互功能都有对应场景
- [ ] `target` 选择器与实际代码中的 id/class 一致
- [ ] `expected` 是界面上实际会显示的文字（不是描述性文字）
- [ ] 页面切换后有 `wait` 步骤
- [ ] 每个场景自包含（第一步是navigate），或页面启用了 `flow: true` 连续流模式
- [ ] `platform` 字段正确
- [ ] `base_url` 和 `start_command` 填写正确
