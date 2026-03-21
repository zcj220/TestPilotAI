# Windows 桌面应用平台蓝本规则（platform = "desktop"）

> 本文件定义 Windows 桌面应用（WPF/WinForms/Electron/Qt 等）蓝本的完整规则。
> 桌面测试通过 pywinauto / UI Automation 驱动。
> 生成蓝本前**必须**通读本文件，不得跳过任何章节。

---

## 一、必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"desktop"` | `"desktop"` |
| `window_title` | 主窗口标题（精确匹配） | `"财务管理系统"` |
| `base_url` | **留空** `""` | `""` |
| `app_name` | 应用名称 | `"财务管理系统"` |
| `description` | 50-200字功能描述 | |
| `start_command` | 启动命令（可选） | `"MyApp.exe"` |
| `start_cwd` | 启动目录（可选） | `"./dist"` |

### 反面禁止

- ❌ `base_url` 填了 HTTP URL → 桌面应用不是 Web，留空
- ❌ 填了 `app_package` / `bundle_id`（移动端字段）
- ❌ `window_title` 填错（必须与应用标题栏完全一致）

---

## 二、封闭式动作表（只允许以下动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(窗口标题或命令), `description` | 启动/重启应用 |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `wait` | `description` | 等待（`value` 指定毫秒） |
| `assert_text` | `expected`, `description` | 断言窗口内包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动作

- ❌ `select`、`navigate_to`、`evaluate`、`call_method`（非桌面动作）
- ❌ `reset_state`、`page_query`、`scroll`（非桌面动作）

---

## 三、选择器规则

### 桌面应用选择器格式

桌面应用元素通过 **屏幕上可见的原文** 定位：

```
name:屏幕上可见的原文
```

| 界面元素 | 蓝本选择器 |
|---------|-----------|
| 按钮文字 "Login" | `name:Login` |
| 按钮文字 "确定" | `name:确定` |
| 输入框旁标签 "用户名" | `name:用户名` |
| 菜单项 "文件" | `name:文件` |
| 标签页 "设置" | `name:设置` |

### ⚠️ 绝对禁止的写法

- ❌ `name:Login按钮`（禁止在原文后加中文后缀）
- ❌ `name:确定按钮`（屏幕上只显示"确定"，不是"确定按钮"）
- ❌ `name:用户名输入框`（屏幕上只显示"用户名"，不是"用户名输入框"）
- ❌ `#id`、`.class`（Web CSS 选择器，桌面不支持）
- ❌ `accessibility_id:xxx`（移动端选择器，桌面不支持）

**核心原则：`name:` 后面跟的必须是屏幕上肉眼可见的原文，不多不少。**

---

## 四、瞬态 UI 不可断言清单

| 组件 | 说明 |
|------|------|
| 系统托盘通知 | 气泡提示，短暂显示 |
| Splash Screen | 启动画面，几秒后消失 |
| 状态栏瞬态提示 | 短暂显示后恢复原文 |
| ToolTip | 鼠标悬停提示，移开消失 |

### 代码稽核—持久性验证

```
✅ 可以断言：
   - 窗口标题栏文字
   - 按钮/标签持久显示的文字
   - 列表项、表格单元格文字
   - 状态栏持久化文字

❌ 不能断言：
   - 气泡通知
   - 启动画面
   - 工具提示（ToolTip）
```

---

## 五、等待时间计算公式

```
wait 时间 = 操作耗时 + 1500ms（预留窗口刷新 + UI Automation 响应）
```

| 场景 | wait 时间 |
|------|----------|
| 应用冷启动 | wait 3000-5000（视应用大小） |
| 弹出子窗口/对话框 | wait 1500 |
| 文件读写操作 | wait 2000 |
| 网络请求 | API时间 + 1500 |
| 纯 UI 控件操作 | wait 1000 |

---

## 六、场景自包含原则

- 引擎在每个场景间可能重启应用
- 每个场景的第一步应是 `navigate`（启动应用）+ `wait`（等启动完成）
- **禁止**场景间传递状态
- 如果场景需要特定前置状态（如已登录），必须在该场景内重新执行操作

---

## 七、完整 JSON 模板

```json
{
  "app_name": "你的应用名",
  "description": "50-200字功能描述",
  "base_url": "",
  "platform": "desktop",
  "window_title": "应用窗口标题",
  "start_command": "MyApp.exe",
  "start_cwd": ".",
  "pages": [
    {
      "url": "",
      "name": "主窗口",
      "scenarios": [
        {
          "name": "正确登录",
          "steps": [
            {"action": "navigate", "value": "应用窗口标题", "description": "启动应用"},
            {"action": "wait", "value": "3000", "description": "等待应用窗口完全加载"},
            {"action": "fill", "target": "name:用户名", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "name:密码", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "name:登录", "description": "点击登录按钮，验证账号后进入主界面"},
            {"action": "wait", "value": "2000", "description": "等待登录验证和界面切换"},
            {"action": "assert_text", "expected": "欢迎", "description": "验证主界面显示欢迎信息"},
            {"action": "screenshot", "description": "登录成功后的主界面"}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清单

- [ ] 查看应用界面，确认 `name:` 后的文字与屏幕显示完全一致
- [ ] `name:` 后没有添加"按钮"/"输入框"等中文后缀
- [ ] `window_title` 与应用标题栏完全匹配
- [ ] `base_url` 为空字符串 `""`
- [ ] `expected` 文字在界面上持久显示
- [ ] 启动后有足够的 wait 时间

---

## 九、踩坑清单

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| `name:登录按钮` | 找不到（屏幕只显示"登录"） | `name:登录` |
| `name:用户名输入框` | 找不到 | `name:用户名` |
| 用 CSS 选择器 `#id` | 桌面不支持 | 用 `name:原文` |
| 用 `accessibility_id:` | 桌面不支持 | 用 `name:原文` |
| 应用启动后没 wait | 窗口未就绪 | wait 3000-5000 |
| `window_title` 拼错 | 引擎找不到窗口 | 与标题栏完全一致 |
