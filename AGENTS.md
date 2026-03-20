# TestPilot AI — 编程AI蓝本自动生成规则

> 本文件由 TestPilot AI 插件自动注入，指导编程AI在开发过程中自动生成和维护测试蓝本。
> 你可以根据项目需求自由修改本文件内容。

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
- [ ] 场景间状态连贯（后一个场景基于前一个的结束状态）
- [ ] `platform` 字段正确
- [ ] `base_url` 和 `start_command` 填写正确
