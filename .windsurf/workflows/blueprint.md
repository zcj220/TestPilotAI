---
description: 生成或修改 TestPilot AI 测试蓝本（testpilot.json）时必须遵守的规范
---

# TestPilot AI 蓝本编写规范（全平台）

当用户要求你生成、修改、审查 `testpilot.json` 蓝本文件时，**必须严格遵守以下规范**。

---

## 一、通用结构（所有平台）

```json
{
  "app_name": "应用名称",
  "description": "测试目标的完整描述",
  "base_url": "应用URL（web必填，其他平台可空）",
  "platform": "web | desktop | android | ios | miniprogram",
  "pages": [
    {
      "url": "页面路径",
      "name": "模块名",
      "scenarios": [
        {
          "name": "场景名",
          "description": "场景目标",
          "steps": [...]
        }
      ]
    }
  ]
}
```

### 平台特有字段

| 平台 | 额外必填字段 |
|------|-------------|
| `desktop` | `window_title`（窗口标题），`app_exe`（启动命令，可选） |
| `android` | `app_package`，`app_activity` |
| `ios` | `bundle_id`（必填），`udid`（可选） |
| `miniprogram` | `base_url` 格式为 `miniprogram://项目绝对路径` |
| `web` | `base_url` 为完整URL |

---

## 二、⚠️ target 写法铁律（最关键！违反必导致定位失败）

### 铁律1：target 必须使用屏幕上可见的原文

`target` 中 `name:` 后面的文字，必须是**应用界面上肉眼可见的原文**。

**绝对禁止**在 target 里加任何中文后缀：按钮、输入框、列表项、链接、标签、区域、文本、图标。

```
✅ 正确：
"target": "name:Login"
"target": "name:Add"
"target": "name:Toggle Done"
"target": "name:Buy milk"
"target": "name:输入待办事项..."      ← placeholder也算可见文字
"target": "name:Search notes..."

❌ 错误（加了中文后缀）：
"target": "name:Login按钮"            ← 屏幕上只有 Login
"target": "name:Add按钮"              ← 屏幕上只有 Add
"target": "name:Toggle Done按钮"      ← 屏幕上只有 Toggle Done
"target": "name:Buy milk列表项"       ← 屏幕上只有 Buy milk
"target": "name:用户名输入框"          ← 屏幕上是 Username 或 placeholder
"target": "name:笔记统计区域"          ← 屏幕上是 Total: 3 notes
"target": "name:登录页提示信息"         ← 屏幕上是 Please enter username
```

### 铁律2：元素类型/位置/颜色写在 description 里

`description` 是给AI视觉定位的辅助信息，越具体越好：

```json
{
  "action": "click",
  "target": "name:Delete",
  "description": "点击列表下方中间的红色Delete按钮"
}
```

```json
{
  "action": "click",
  "target": "name:Buy milk",
  "description": "点击列表中包含Buy milk文字的那一行"
}
```

```json
{
  "action": "fill",
  "target": "name:Search notes...",
  "description": "在页面顶部包含Search notes...占位符的搜索输入框输入"
}
```

### 铁律3：不同平台的 target 格式

| 平台 | target格式 | 示例 |
|------|-----------|------|
| **desktop** | `name:屏幕可见原文` | `name:Login`、`name:Add` |
| **web** | CSS选择器 | `#loginBtn`、`.submit-btn` |
| **android** | `accessibility_id:xxx` 或 `id:xxx` | `accessibility_id:btn_login` |
| **ios** | `accessibility_id:xxx` | `accessibility_id:btn_login` |
| **miniprogram** | CSS选择器 | `#price-1`、`.btn-primary` |

> Web和小程序用CSS选择器，不受"屏幕原文"铁律限制。
> Desktop和Android（视觉模式）必须严格遵守"屏幕原文"铁律。

---

## 三、description 最佳实践

每个步骤的 `description` 必须包含以下辅助信息（越多越好）：

1. **位置**：上方/下方/左侧/右侧/中间/顶部/底部/右上角
2. **颜色**：蓝色/红色/绿色/灰色/白色
3. **相邻元素**：输入框右侧的、列表下方的、标题旁边的
4. **元素类型**：按钮/输入框/列表行/下拉框/复选框（在description里说，不在target里说）
5. **⭐ 预期页面变化**：点击/输入后页面会发生什么变化（编程AI应该根据源码预测）

### 为什么要写预期页面变化？

桌面应用没有DOM树，AI需要看截图定位元素。**description越丰富，AI定位越快越准**。
编程AI在写蓝本时已经读过源码，知道每个按钮点击后会触发什么行为、页面会怎么变化，
应该把这些信息写进description，帮助测试引擎理解上下文。

```
✅ 好的description（包含位置+预期变化）：
"description": "点击输入框右侧的蓝色Add按钮，点击后列表区域会新增一行显示刚输入的内容，底部统计栏Total数字会+1"
"description": "点击列表中Buy milk那一行左侧的复选框，点击后该行文字会加删除线，底部Done数+1"
"description": "点击列表下方红色Delete按钮，点击后当前选中行会从列表消失，Total数-1"
"description": "在顶部搜索框输入关键词，输入后列表会实时过滤只显示匹配项"
"description": "点击右上角红色Logout按钮，点击后整个页面切换为登录表单"

❌ 差的description（只说了操作没说预期）：
"description": "点击按钮"           ← 太模糊
"description": "输入内容"           ← 没有位置信息
"description": "点击Add"           ← 没有预期变化
```

### assert_text 的 description 也要写明验证的上下文

```
✅ "description": "验证底部统计栏总数从3变为4（因为刚添加了Learn Python）"
✅ "description": "验证列表中出现新添加的Learn Python文字行"
❌ "description": "验证数量"        ← 没有上下文
```

---

## 四、步骤动作规范

### 所有平台通用动作

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| `click` | `target`, `description` | 点击元素 |
| `fill` | `target`, `value`, `description` | 输入文本（自动清空旧内容） |
| `screenshot` | `description` | 截图保存 |
| `assert_text` | `expected`, `description` | 断言页面包含指定文本 |
| `wait` | `description` | 等待（默认1秒，可用value指定毫秒） |
| `navigate` | `value`(URL), `description` | 页面跳转（web/小程序） |

### desktop 专用注意事项

- 不支持 `navigate`（没有URL概念）
- `fill` 会自动 Ctrl+A 全选后输入，无需手动清空
- 页面切换后必须加 `wait`（等窗口重绘）
- **⚠️ 弹窗必须关闭**：任何触发弹窗（QMessageBox/alert/confirm）的操作后，必须加一个click步骤关闭弹窗（点OK/Yes/No/Cancel等），否则弹窗会遮挡主界面，导致后续所有步骤失败

```json
✅ 正确（弹窗后关闭）：
{"action": "click", "target": "name:Add", "description": "点击Add，因输入为空会弹出警告"},
{"action": "wait", "value": "500", "description": "等待弹窗出现"},
{"action": "screenshot", "description": "空输入警告弹窗"},
{"action": "click", "target": "name:OK", "description": "点击OK关闭弹窗，回到主界面"},
{"action": "wait", "value": "300", "description": "等待弹窗关闭"}

❌ 错误（弹窗不关闭，后续全部卡死）：
{"action": "click", "target": "name:Add", "description": "点击Add"},
{"action": "screenshot", "description": "警告弹窗"}
// 下一个场景的操作全部被弹窗遮挡！
```

---

## 五、场景设计规范

### 5.1 状态连贯

场景按执行顺序排列，后一个场景的初始状态 = 前一个场景的结束状态。

```
场景1: 登录 → 进入主页
场景2: 主页添加数据（基于场景1的结束状态）
场景3: 搜索（基于场景2添加后的数据）
场景4: 登出 → 回到登录页
场景5: 错误登录验证（基于场景4的登录页）
```

### 5.2 页面切换必须加 wait（带合适时长）

任何导致页面/状态变化的操作后，下一步必须是 `wait`，且时长要够：

| 场景 | 推荐wait时长 | 说明 |
|------|-------------|------|
| 登录/登出等页面切换 | `"value": "1500"` ~ `"2000"` | 桌面应用重绘需要时间 |
| 列表更新/数据刷新 | `"value": "500"` ~ `"1000"` | 简单数据变化 |
| 弹窗/动画 | `"value": "500"` | 通常很快 |
| 默认（不写value） | 1000ms | 引擎默认值 |

```json
{"action": "click", "target": "name:Logout", "description": "点击右上角红色Logout按钮"},
{"action": "wait", "value": "2000", "description": "等待回到登录页（桌面应用重绘需要较长时间）"},
{"action": "screenshot", "description": "回到登录页"}
```

> ⚠️ **常见错误**：Logout/Login等页面切换后只等500ms或1000ms，导致AI截图时看到的还是旧页面，后续所有步骤连锁失败。桌面应用页面切换至少等1500ms。

### 5.3 截图策略

- 每个场景的**第一个步骤**或**最后一个步骤**放一个 `screenshot`
- 不要每步都加截图（浪费AI费用）
- 断言失败时引擎会自动截图，无需额外加

### 5.4 断言写法

- `expected` 写界面上会出现的**精确文本片段**
- 不要写模糊的描述，要写实际会显示的文字

```json
✅ {"action": "assert_text", "expected": "Total: 4", "description": "验证总数变为4"}
✅ {"action": "assert_text", "expected": "Hello World", "description": "验证搜索结果包含Hello World"}
❌ {"action": "assert_text", "expected": "显示4条记录", "description": "验证数量"}  ← 界面上不会出现这个文字
```

---

## 六、完整蓝本示例（桌面）

```json
{
  "app_name": "TodoApp",
  "description": "PyQt5待办事项应用测试",
  "platform": "desktop",
  "window_title": "TodoApp",
  "app_exe": "python todo_app.py",
  "base_url": "",
  "pages": [
    {
      "url": "",
      "name": "完整流程",
      "scenarios": [
        {
          "name": "添加待办",
          "steps": [
            {"action": "fill", "target": "name:输入待办事项...", "value": "Buy milk", "description": "在顶部包含'输入待办事项...'占位符的输入框输入"},
            {"action": "click", "target": "name:Add", "description": "点击输入框右侧的蓝色Add按钮"},
            {"action": "wait", "description": "等待列表更新"},
            {"action": "assert_text", "expected": "Buy milk", "description": "验证列表包含新添加的项"},
            {"action": "screenshot", "description": "添加完成后的列表"}
          ]
        }
      ]
    }
  ]
}
```

---

## 七、自查清单（生成蓝本后必须逐项检查）

1. [ ] **target没有中文后缀**：所有 `name:` 后面都是屏幕原文，没有"按钮""输入框""列表项"等
2. [ ] **description够具体**：每个步骤都说明了位置、颜色、元素类型
3. [ ] **expected是精确文本**：断言的expected是界面上实际显示的文字片段
4. [ ] **页面切换后有wait**：每个导致页面/状态变化的操作后都加了wait
5. [ ] **场景状态连贯**：场景间状态正确衔接，没有跳跃
6. [ ] **平台字段完整**：desktop有window_title，android有app_package，ios有bundle_id，web有base_url
7. [ ] **截图不过量**：每个场景最多1-2个screenshot，不是每步都截
