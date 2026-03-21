# Android/Flutter 平台蓝本规则（platform = "android"）

> 本文件定义 Android 原生应用和 Flutter 应用蓝本的完整规则。
> Flutter 应用的 platform 也是 `"android"`，不是 `"flutter"`。
> 生成蓝本前**必须**通读本文件，不得跳过任何章节。

---

## 一、必填字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"android"` | `"android"` |
| `app_package` | 应用包名 | `"com.example.myapp"` |
| `app_activity` | 启动 Activity | `".MainActivity"` |
| `base_url` | **必须留空** `""` | `""` |
| `app_name` | 应用名称 | `"财务记账系统"` |
| `description` | 50-200字功能描述 | |

### 反面禁止

- ❌ **绝对禁止**把 `app_package` 的值填入 `base_url`。`base_url` 必须是空字符串 `""`
- ❌ 不要填 `start_command`（Android 不需要命令行启动）
- ❌ 不要填 `bundle_id`（那是 iOS 的字段）
- ❌ 页面的 `url` 也留空 `""`（原生应用没有 HTTP URL）

---

## 二、封闭式动作表（只允许以下动作，禁止使用不在此列表中的动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(Activity路径), `description` | 重启应用到指定 Activity |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `wait` | `description` | 等待（`value` 指定毫秒，或 `target`+`timeout_ms` 等待元素） |
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动作

- ❌ `reset_state`（这是小程序专用动作，Android 不支持）
- ❌ `select`（Android 原生下拉框用 click 选择，不用 select）
- ❌ `navigate_to`、`evaluate`、`call_method`、`page_query`（小程序专用）
- ❌ `hover`、`scroll`（Web 专用）

---

## 三、选择器规则

### Flutter Semantics → Android 无障碍属性映射

Flutter 代码中的 Widget 在 Android 端通过 Appium UiAutomator2 呈现为无障碍属性：

| Flutter/Android 代码 | Appium 看到的属性 | 蓝本选择器 |
|---|---|---|
| `ElevatedButton(child: Text('登录'))` | `content-desc="登录"` | `accessibility_id:登录` |
| `IconButton(tooltip: '删除')` | `content-desc="删除"` | `accessibility_id:删除` |
| `Text('欢迎回来')` | `text="欢迎回来"` | `accessibility_id:欢迎回来` |
| `TextField(decoration: InputDecoration(labelText: '用户名'))` | `hint="用户名"` | `//android.widget.EditText[@hint='用户名']` |
| `TextField(decoration: InputDecoration(hintText: '请输入密码'))` | `hint="请输入密码"` | `//android.widget.EditText[@hint='请输入密码']` |
| `Semantics(label: 'xxx', button: true)` | `content-desc="xxx"` | `accessibility_id:xxx` |
| BottomNavigationBarItem(label: '报表') | `content-desc="报表"` | `accessibility_id:报表` |

### 选择器优先级（从高到低）

1. **`accessibility_id:按钮文字或label`** — 按钮、文本、图标按钮、导航项
2. **`//android.widget.EditText[@hint='labelText或hintText']`** — 文本输入框
3. **`//ClassName[@attribute='value']`** — 其他精确 XPath

### 绝对禁止的选择器

- ❌ `id:xxx`（Flutter 的 Key 不等于 Android resource-id，Appium 无法识别）
- ❌ `#id`、`.class`（这是 Web CSS 选择器，Android 不支持）
- ❌ `UiSelector().className("xxx").instance(N)`（依赖顺序，极其脆弱）
- ❌ `//xxx[@index='N']`（索引定位，UI 变化即失效）
- ❌ 不带任何属性约束的纯 ClassName 选择器

### ⚠️ Flutter Key ≠ Appium 选择器

Flutter 代码中的 `Key('username_input')` **不会**生成 Appium 可用的 `id:username_input`。
Flutter 是自绘引擎，UI tree 通过 Semantics 暴露给 Appium，不是通过 Key。
**必须根据 Widget 的 text/label/hint 属性来确定选择器。**

---

## 四、瞬态 UI 不可断言清单

以下组件是瞬态的（短暂显示后自动消失），Appium **无法在 UI tree 中捕获**：

| 组件 | 框架 | 说明 |
|------|------|------|
| `SnackBar` | Flutter | `ScaffoldMessenger.showSnackBar()` 几秒后消失 |
| `Toast` | Android 原生 | `Toast.makeText()` 短暂显示 |
| `AlertDialog` 自动关闭 | 通用 | 设置了自动消失的对话框 |

**不能用 `assert_text` 断言 SnackBar/Toast 中的文字！**

### 代码稽核—持久性验证

生成蓝本前，必须检查代码中 `expected` 文字的渲染方式：

```
✅ 可以断言（持久化渲染）：
   - AppBar title: Text('记账台')          → expected: "记账台"
   - 页面中的 Text('收入')                 → expected: "收入"
   - 红色错误提示 Text(errorMessage)       → expected: "登录失败"（前提：errorMessage 在 UI tree 中持久存在）

❌ 不能断言（瞬态）：
   - ScaffoldMessenger.showSnackBar(SnackBar(content: Text('操作成功')))
   - Toast.makeText(context, "保存成功", Toast.LENGTH_SHORT)
```

**如果代码中成功/失败提示只通过 SnackBar 显示，则应建议开发者改为持久化 Text widget，或在蓝本中改为断言页面状态变化（如跳转后的页面标题）。**

---

## 五、等待时间计算公式

```
wait 时间 = 代码中的异步延迟 + 2000ms（预留 Flutter 渲染 + Appium UI tree 刷新）
```

| 代码场景 | wait 时间 |
|---------|----------|
| `Future.delayed(Duration(seconds: 2))` + 页面跳转 | wait 4000 |
| API 调用（假设 1 秒）+ 数据渲染 | wait 3000 |
| 纯 `setState()` 无异步 | wait 1500 |
| `Navigator.pushReplacementNamed()` 页面跳转 | wait 2000 |
| 应用冷启动（force-stop 后重启） | wait 3000 |

### wait 两种格式

| 格式 | 用法 | 说明 |
|------|------|------|
| 简单等待 | `{"action": "wait", "value": "3000"}` | 固定等待毫秒数 |
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 轮询等元素出现 |

> 推荐流程：先 `wait 3000`（固定），再 `wait target`（等关键元素就绪）。

---

## 六、场景自包含原则

- 引擎在每个场景间会自动 `force-stop` → 重建 Session → 重启 App
- 每个场景的第一步应该是 `wait 3000`（等待冷启动完成）
- **禁止**场景间传递状态
- 如果场景需要登录状态，必须在该场景内重新执行登录步骤

---

## 七、完整 JSON 模板

```json
{
  "app_name": "你的应用名",
  "description": "50-200字功能描述",
  "base_url": "",
  "platform": "android",
  "app_package": "com.example.app",
  "app_activity": ".MainActivity",
  "pages": [
    {
      "url": "",
      "name": "登录页",
      "scenarios": [
        {
          "name": "正确账号登录成功",
          "description": "使用演示账号admin/admin123登录",
          "steps": [
            {"action": "wait", "value": "3000", "description": "等待应用冷启动完成"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='用户名']", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='密码']", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "accessibility_id:登录", "description": "点击登录按钮，触发API调用后跳转到主页"},
            {"action": "wait", "value": "4000", "description": "等待API延迟(2秒)+页面跳转+UI tree刷新"},
            {"action": "assert_text", "expected": "主页", "description": "验证成功跳转到主页，AppBar标题显示'主页'"},
            {"action": "screenshot", "description": "登录成功后的主页"}
          ]
        }
      ]
    }
  ]
}
```

---

## 八、代码稽核清单（生成蓝本前必须逐项验证）

- [ ] 在源码中搜索每个 Widget 的 text/label/hint，确认选择器与实际属性一致
- [ ] **绝对不要**把 Flutter Key 当作 Appium 选择器
- [ ] 确认 `expected` 文字是通过 `Text()` widget 持久化渲染的，不是 SnackBar/Toast
- [ ] 检查代码中的异步调用（Future.delayed/http.get/dio），按公式计算 wait 时间
- [ ] 确认 `app_package` 是实际的包名（检查 `android/app/build.gradle` 中的 `applicationId`）
- [ ] 确认 `base_url` 为空字符串 `""`
- [ ] 确认每个操作后有 `assert_text` 或 `screenshot` 验证结果
- [ ] 确认 DropdownButton 用 `click` 操作（先点展开，再点选项），不用 `select`

---

## 九、踩坑清单

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 用 `id:username_input`（Flutter Key） | 找不到元素 | 用 `//android.widget.EditText[@hint='用户名']` |
| 断言 SnackBar 文字 | 文字已消失，断言失败 | 断言页面持久化状态或页面跳转 |
| `base_url` 填了包名 | 引擎困惑 | `base_url` 必须为 `""` |
| 用了 `reset_state` | 引擎不识别 | 删掉，引擎自动处理场景重置 |
| 用了 `select` 动作 | Android 不支持 | 用 `click` 展开 + `click` 选项 |
| wait 只写了代码延迟时间 | UI tree 还没刷新 | 延迟时间 + 2000ms |
| 用 CSS 选择器 `#id` `.class` | Android 不支持 | 用 accessibility_id 或 XPath |
