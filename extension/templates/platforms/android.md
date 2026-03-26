<!-- TestPilot-Template-Version: 9 -->
# Android/Flutter 平台蓝本规则（platform = "android"�?

> 本文件定�?Android 原生应用�?Flutter 应用蓝本的完整规则�?
> Flutter 应用�?platform 也是 `"android"`，不�?`"flutter"`�?
> 生成蓝本�?*必须**通读本文件，不得跳过任何章节�?

---

## 零、生成蓝本前必须先通读源代码（强制执行�?

**蓝本的唯一依据是代码，不是猜测，不是常识，不是用户描述�?*

在写任何 JSON 之前，必须按顺序完成�?

0. **先读 `testpilot/CHANGELOG.md`（如果存在）** �?了解当前已覆盖的功能和尚未测试的模块，避免重复写或漏写；如果不存在则跳过
1. **读入�?路由文件** �?了解应用整体结构和页面列表（�?`main.dart`、`AndroidManifest.xml`�?
2. **读每个页面的 UI 文件** �?找出所有可操作元素（按钮、输入框、下拉框、导航项�?
3. **记录元素的真实标�?* �?`hint` / `label` / `contentDescription` / `tooltip`（这是选择器的唯一来源�?
4. **读业务逻辑** �?确认每个操作的真实结果（跳转哪里、显示什么文字）
5. **确认提示方式** �?成功/失败提示�?SnackBar/Toast（瞬态，**不可断言**）还是持久化 Text（可断言�?
6. **列出已实现功�?* �?代码里有什么就测什么，未实现的功能不写蓝本

**禁止跳过代码阅读直接生成蓝本。凭想象写的选择器和断言几乎必然失败�?*

---

## 一、必填字�?

| 字段 | 说明 | 示例 |
|------|------|------|
| `platform` | 固定 `"android"` | `"android"` |
| `app_package` | 应用包名 | `"com.example.myapp"` |
| `app_activity` | 启动 Activity | `".MainActivity"` |
| `base_url` | **必须留空** `""` | `""` |
| `app_name` | 应用名称 | `"财务记账系统"` |
| `description` | 50-200字功能描�?| |

### 反面禁止

- �?**绝对禁止**�?`app_package` 的值填�?`base_url`。`base_url` 必须是空字符�?`""`
- �?不要�?`start_command`（Android 不需要命令行启动�?
- �?不要�?`bundle_id`（那�?iOS 的字段）
- �?页面�?`url` 也留�?`""`（原生应用没�?HTTP URL�?

---

## 二、封闭式动作表（只允许以下动作，禁止使用不在此列表中的动作）

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `navigate` | `value`(Activity路径), `description` | 重启应用到指�?Activity |
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本 |
| `wait` | `description` | 等待（`value` 指定毫秒，或 `target`+`timeout_ms` 等待元素�?|
| `assert_text` | `expected`, `description` | 断言页面包含文本 |
| `screenshot` | `description` | 截图留证 |

### 绝对禁止的动�?

- �?`reset_state`（这是小程序专用动作，Android 不支持）
- �?`select`（Android 原生下拉框用 click 选择，不�?select�?
- �?`navigate_to`、`evaluate`、`call_method`、`page_query`（小程序专用�?
- �?`hover`、`scroll`（Web 专用�?

---

## 三、选择器规�?

### Flutter Semantics �?Android 无障碍属性映�?

Flutter 代码中的 Widget �?Android 端通过 Appium UiAutomator2 呈现为无障碍属性：

| Flutter/Android 代码 | Appium 看到的属�?| 蓝本选择�?|
|---|---|---|
| `ElevatedButton(child: Text('登录'))` | `content-desc="登录"` | `accessibility_id:登录` |
| `IconButton(tooltip: '删除')` | `content-desc="删除"` | `accessibility_id:删除` |
| `Text('欢迎回来')` | `text="欢迎回来"` | `accessibility_id:欢迎回来` |
| `TextField(decoration: InputDecoration(labelText: '用户�?))` | `hint="用户�?` | `//android.widget.EditText[@hint='用户�?]` |
| `TextField(decoration: InputDecoration(hintText: '请输入密�?))` | `hint="请输入密�?` | `//android.widget.EditText[@hint='请输入密�?]` |
| `Semantics(label: 'xxx', button: true)` | `content-desc="xxx"` | `accessibility_id:xxx` |
| BottomNavigationBarItem(label: '报表') | `content-desc="报表"` | `accessibility_id:报表` |

### 🚨 选择器三步验证（强制执行，每�?target 都必须做�?

写任何一�?`target` 选择器之前，必须完成以下三步�?*缺一不可**�?

1. **定位源码**：找到该 Widget 所在的 `.dart` / `.kt` / `.java` 文件，定位到具体�?
2. **复制属�?*：从代码中复�?Widget 的真�?`child: Text('xxx')`、`tooltip`、`labelText`、`hintText`�?*禁止凭记忆或猜测**�?
3. **唯一性验�?*：在同一页面源码中搜索该文字，确认不会匹配到多个元素

**不做三步验证就写的选择�?= 必然出错。这是选择器失败的第一大原因�?*

### 选择器优先级（从高到低）

1. **`accessibility_id:按钮文字或label`** �?按钮、文本、图标按钮、导航项
2. **`//android.widget.EditText[@hint='labelText或hintText']`** �?文本输入�?
3. **`//ClassName[@attribute='value']`** �?其他精确 XPath

### 绝对禁止的选择�?

- �?`id:xxx`（Flutter �?Key 不等�?Android resource-id，Appium 无法识别�?
- �?`#id`、`.class`（这�?Web CSS 选择器，Android 不支持）
- �?`UiSelector().className("xxx").instance(N)`（依赖顺序，极其脆弱�?
- �?`//xxx[@index='N']`（索引定位，UI 变化即失效）
- �?不带任何属性约束的�?ClassName 选择�?

### ⚠️ Flutter Key �?Appium 选择�?

Flutter 代码中的 `Key('username_input')` **不会**生成 Appium 可用�?`id:username_input`�?
Flutter 是自绘引擎，UI tree 通过 Semantics 暴露�?Appium，不是通过 Key�?
**必须根据 Widget �?text/label/hint 属性来确定选择器�?*

### 🚨 不要猜测按钮文字（必读！�?

AI 常犯的错误：看到 `ElevatedButton` 就猜按钮文字�?登录"�?保存"。但实际代码中可能是 `Text('�?�?)` �?`Text('保存修改')` �?`Icon(Icons.save)`�?

**强制要求**：打开按钮所在的 `.dart` 文件，找�?`child:` 属性中�?`Text('...')` 原文，逐字复制到选择器中。空格、标点、全半角都必须完全一致�?

| �?错误（猜测） | �?正确（从代码复制�?|
|---|---|
| `accessibility_id:登录` | 读源码发�?`Text('�?�?)` �?`accessibility_id:�?录` |
| `accessibility_id:保存` | 读源码发�?`Text('保存修改')` �?`accessibility_id:保存修改` |
| `accessibility_id:add` | 读源码发�?`IconButton(tooltip: '新增')` �?`accessibility_id:新增` |

---

## 四、瞬�?UI 不可断言清单

以下组件是瞬态的（短暂显示后自动消失），Appium **无法�?UI tree 中捕�?*�?

| 组件 | 框架 | 说明 |
|------|------|------|
| `SnackBar` | Flutter | `ScaffoldMessenger.showSnackBar()` 几秒后消�?|
| `Toast` | Android 原生 | `Toast.makeText()` 短暂显示 |
| `AlertDialog` 自动关闭 | 通用 | 设置了自动消失的对话�?|

**不能�?`assert_text` 断言 SnackBar/Toast 中的文字�?*

### 代码稽核—持久性验�?

生成蓝本前，必须检查代码中 `expected` 文字的渲染方式：

```
�?可以断言（持久化渲染）：
   - AppBar title: Text('记账�?)          �?expected: "记账�?
   - 页面中的 Text('收入')                 �?expected: "收入"
   - 红色错误提示 Text(errorMessage)       �?expected: "登录失败"（前提：errorMessage �?UI tree 中持久存在）

�?不能断言（瞬态）�?
   - ScaffoldMessenger.showSnackBar(SnackBar(content: Text('操作成功')))
   - Toast.makeText(context, "保存成功", Toast.LENGTH_SHORT)
```

**如果代码中成�?失败提示只通过 SnackBar 显示，则应建议开发者改为持久化 Text widget，或在蓝本中改为断言页面状态变化（如跳转后的页面标题）�?*

---

## 五、等待时间计算公�?

```
wait 时间 = 代码中的异步延迟 + 2000ms（预�?Flutter 渲染 + Appium UI tree 刷新�?
```

| 代码场景 | wait 时间 |
|---------|----------|
| `Future.delayed(Duration(seconds: 2))` + 页面跳转 | wait 4000 |
| API 调用（假�?1 秒）+ 数据渲染 | wait 3000 |
| �?`setState()` 无异�?| wait 1500 |
| `Navigator.pushReplacementNamed()` 页面跳转 | wait 2000 |
| 应用冷启动（force-stop 后重启） | wait 3000 |

### wait 两种格式

| 格式 | 用法 | 说明 |
|------|------|------|
| 简单等�?| `{"action": "wait", "value": "3000"}` | 固定等待毫秒�?|
| 等待元素 | `{"action": "wait", "target": "accessibility_id:xxx", "timeout_ms": 15000}` | 轮询等元素出�?|

> 推荐流程：先 `wait 3000`（固定），再 `wait target`（等关键元素就绪）�?

---

## 六、场景自包含原则与连续流模式（flow 强制决策�?

### ⚠️ 生成蓝本时必须对每个 page �?flow 决策

**判断规则（按顺序检查）�?*
1. �?page 下有 �? 个场景，且都需要先登录才能操作？→ **必须 `"flow": true`**
2. �?page 下有 �? 个场景是同页�?Tab 切换或连续操作？�?**必须 `"flow": true`**
3. �?page 下场景需要互相独立的干净状态（如正确登�?vs 错误登录）？�?不写 flow（默�?false�?

**简单总结：如果多个场景都要先登录再操作同一个页面，那这�?page 必须�?`"flow": true`。不�?flow 导致每个场景都冷启动+重复登录 = 严重浪费�?*

### 默认模式（`flow: false`�?

- 引擎在每个场景间会自�?`force-stop` �?重建 Session �?重启 App
- 每个场景的第一步应该是 `wait 3000`（等待冷启动完成�?
- **禁止**场景间传递状�?
- 如果场景需要登录状态，必须在该场景内重新执行登录步�?

### 连续流模式（`flow: true`�?

�?`page` 级别设置 `"flow": true`，同一页面内的场景将连续执行：

```json
{
  "url": "",
  "title": "记账�?,
  "flow": true,
  "scenarios": [
    {
      "name": "登录进入记账�?,
      "steps": [
        {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "冷启�?},
        {"action": "wait", "value": "3000"},
        {"action": "fill", "target": "...", "value": "admin"},
        {"action": "click", "target": "...", "description": "登录"},
        {"action": "wait", "value": "3000"},
        {"action": "assert_text", "expected": "记账�?}
      ]
    },
    {
      "name": "添加交易",
      "steps": [
        {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "（flow下自动跳过）"},
        {"action": "fill", "target": "...", "value": "50.00"},
        {"action": "click", "target": "...", "description": "提交"},
        {"action": "assert_text", "expected": "50.00"}
      ]
    },
    {
      "name": "删除交易",
      "steps": [
        {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "（flow下自动跳过）"},
        {"action": "click", "target": "...", "description": "删除"},
        {"action": "assert_text", "expected": "已删�?}
      ]
    }
  ]
}
```

**flow 模式行为�?*
- 仅第1个场景执�?navigate 冷启动，后续场景�?navigate **自动跳过**
- 场景间保持页面状态（不重启、不清除�?
- 连续3个场景失�?�?尝试冷启动恢复后继续

**重要�?* flow 场景仍需�?navigate 步骤（方便单独运行），引擎在 flow 模式下自动跳过非首场景的 navigate�?

### 🚨 flow 非首场景写法（极其重要，必须遵守！）

**flow 模式下，�?个及之后的场景只�?navigate + 该场景自己的操作步骤，绝对禁止重复写登录步骤�?*

引擎会跳过非首场景的 navigate，直接从�?步开始执行。如果第2步是 `fill 用户名`，但页面此时已经登录在功能页�?�?找不到输入框 �?超时失败 �?连续3步失�?�?整个场景被熔断跳�?�?后续场景全部同样失败�?

| �?错误写法（非首场景重复登录） | �?正确写法（非首场景直接操作） |
|---|---|
| 场景2: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?实际操作 | 场景2: navigate �?实际操作 �?assert_text |
| 场景3: navigate �?wait �?fill用户�?�?fill密码 �?click登录 �?wait �?实际操作 | 场景3: navigate �?实际操作 �?assert_text |

**核心原则：flow 模式下，只有�?个场景做完整的冷启动+登录流程，后续场景的 navigate 后面直接写该场景自己的操作�?*

---

## 七、完�?JSON 模板

```json
{
  "app_name": "你的应用�?,
  "description": "50-200字功能描�?,
  "base_url": "",
  "platform": "android",
  "app_package": "com.example.app",
  "app_activity": ".MainActivity",
  "pages": [
    {
      "url": "",
      "name": "登录�?,
      "scenarios": [
        {
          "name": "正确账号登录成功",
          "description": "使用演示账号admin/admin123登录",
          "steps": [
            {"action": "wait", "value": "3000", "description": "等待应用冷启动完�?},
            {"action": "fill", "target": "//android.widget.EditText[@hint='用户�?]", "value": "admin", "description": "在用户名输入框输入admin"},
            {"action": "fill", "target": "//android.widget.EditText[@hint='密码']", "value": "admin123", "description": "在密码输入框输入admin123"},
            {"action": "click", "target": "accessibility_id:登录", "description": "点击登录按钮，触发API调用后跳转到主页"},
            {"action": "wait", "value": "4000", "description": "等待API延迟(2�?+页面跳转+UI tree刷新"},
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

## 八、代码稽核清单（生成蓝本前必须逐项验证�?

- [ ] 在源码中搜索每个 Widget �?text/label/hint，确认选择器与实际属性一�?
- [ ] **绝对不要**�?Flutter Key 当作 Appium 选择�?
- [ ] 确认 `expected` 文字是通过 `Text()` widget 持久化渲染的，不�?SnackBar/Toast
- [ ] 检查代码中的异步调用（Future.delayed/http.get/dio），按公式计�?wait 时间
- [ ] 确认 `app_package` 是实际的包名（检�?`android/app/build.gradle` 中的 `applicationId`�?
- [ ] 确认 `base_url` 为空字符�?`""`
- [ ] 确认每个操作后有 `assert_text` �?`screenshot` 验证结果
- [ ] 确认 DropdownButton �?`click` 操作（先点展开，再点选项），不用 `select`
### 🚨 输出前强制回检（3项必检，不通过必须修正）

**回检1 — flow 决策**：扫描每个 page，该 page 下是否有 ≥2 个场景都需要先登录再操作？
- 是 → 该 page **必须**有 `"flow": true`，且非首场景**禁止**写登录步骤
- 否 → 不设 flow（场景各自独立登录）

**回检2 — 断言覆盖**：扫描每个 scenario，是否至少有一个 `assert_text` 步骤？
- **只有 screenshot 没有 assert_text = 不合格**，必须补充文本断言
- `expected` 必须是通过 `Text()` widget 持久化渲染的文字（不是 SnackBar/Toast）

**回检3 — 重复登录检查**：扫描整个蓝本，是否存在 ≥3 个场景都有完全相同的登录步骤序列？
- 是 → 必须把这些场景合并到同一个 page 并启用 `"flow": true`，只在首场景登录一次
---

## 九、踩坑清�?

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| �?`id:username_input`（Flutter Key�?| 找不到元�?| �?`//android.widget.EditText[@hint='用户�?]` |
| 断言 SnackBar 文字 | 文字已消失，断言失败 | 断言页面持久化状态或页面跳转 |
| `base_url` 填了包名 | 引擎困惑 | `base_url` 必须�?`""` |
| 用了 `reset_state` | 引擎不识�?| 删掉，引擎自动处理场景重�?|
| 用了 `select` 动作 | Android 不支�?| �?`click` 展开 + `click` 选项 |
| wait 只写了代码延迟时�?| UI tree 还没刷新 | 延迟时间 + 2000ms |
| �?CSS 选择�?`#id` `.class` | Android 不支�?| �?accessibility_id �?XPath |
