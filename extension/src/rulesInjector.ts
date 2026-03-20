/**
 * TestPilot AI — 编程AI规则文件注入器
 *
 * 插件激活时自动在用户项目中创建规则文件，
 * 让所有主流IDE的编程AI都能读到蓝本生成规则。
 *
 * 覆盖9种IDE：
 * - AGENTS.md（跨工具通用：Cursor/Cline/Augment/Kilo Code）
 * - .github/copilot-instructions.md（VS Code Copilot）
 * - .cursor/rules/testpilot.md（Cursor）
 * - .windsurf/rules/testpilot.md（Windsurf）
 * - .trae/rules/testpilot.md（Trae / 字节跳动）
 * - .clinerules/testpilot.md（Cline）
 * - .aiassistant/rules/testpilot.md（JetBrains AI）
 * - .augment/rules/testpilot.md（Augment Code）
 * - CLAUDE.md（Claude Code / Anthropic CLI）
 */

import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

/** IDE类型到规则文件的映射 */
const IDE_RULES_MAP: Record<string, string> = {
  cursor: ".cursor/rules/testpilot.md",
  windsurf: ".windsurf/rules/testpilot.md",
  vscode: ".github/copilot-instructions.md",
  vscodium: ".github/copilot-instructions.md",
  cline: ".clinerules/testpilot.md",
  jetbrains: ".aiassistant/rules/testpilot.md",
  trae: ".trae/rules/testpilot.md",
  augment: ".augment/rules/testpilot.md",
  claude: "CLAUDE.md",
};

/**
 * 检测当前运行的IDE类型
 * @returns IDE类型标识符（小写）
 */
function detectCurrentIDE(): string {
  const appName = (vscode.env.appName || "").toLowerCase();

  if (appName.includes("windsurf")) return "windsurf";
  if (appName.includes("cursor")) return "cursor";
  if (appName.includes("vscodium")) return "vscodium";
  // 默认是 VS Code
  return "vscode";
}

/** 规则模板内容（内嵌，避免依赖外部文件） */
function getTemplateContent(): string {
  return `# TestPilot AI — 编程AI蓝本自动生成规则

> 本文件由 TestPilot AI 插件自动注入，指导编程AI在开发过程中自动生成和维护测试蓝本。
> 你可以根据项目需求自由修改本文件内容。

---

## ⚠️ 最重要：每个项目必须有自己的蓝本

- **每个项目目录**下必须有独立的 \`testpilot.json\`（或 \`testpilot/\` 目录）
- 不同项目绝对不能共用蓝本——即使功能相似，选择器和路由也不同
- 不同平台（Web/小程序/Android/桌面）必须各自独立蓝本，\`platform\` 字段不同
- 当项目中**不存在** \`testpilot.json\` 或 \`testpilot/\` 目录时，你在完成功能开发后**必须**自动生成蓝本文件

---

## 一、蓝本自动生成（最重要）

### 生成时机

| 时机 | 动作 |
|------|------|
| 新项目创建完成 | 生成完整蓝本，覆盖所有已实现功能 |
| 新增一个完整功能模块 | 在蓝本中追加对应场景 |
| 项目初始蓝本不存在 | 扫描现有代码，生成功能全覆盖的蓝本 |

### 生成规则

1. 蓝本文件固定命名 \`testpilot.json\`，放在**当前项目根目录**或 \`testpilot/\` 子目录下
2. 必须覆盖项目的**所有用户可交互功能**，不允许遗漏
3. 每个功能模块对应一个 \`page\`，每个用户场景对应一个 \`scenario\`
4. 如果项目功能较多，按功能模块拆分为多个蓝本文件放在 \`testpilot/\` 目录下：
   - 命名格式：\`testpilot/功能模块名.testpilot.json\`（用英文）
   - 拆分判断：页面≤3个用一个 testpilot.json；页面>3个按功能模块拆分
   - 由你根据项目实际代码结构自主决定如何拆分和命名
5. 每个蓝本必须包含 \`app_name\`、\`description\`、\`platform\`、\`base_url\` 字段

---

## 二、测试设计黄金规则（必须严格遵守）

### 核心哲学：绝对正向验证
- 蓝本 = 假设一切功能完全正确的测试路线图
- 写出"正确时应该是什么样"的断言，Bug由引擎自动发现（实际≠预期）
- ❌ 绝对禁止：看到代码有Bug就针对性写用例确认
- ✅ 正确做法：按功能正常逻辑写断言，Bug自然会暴露出来

### 核心哲学：穷举每条路径
- 代码是唯一真相：代码里实现了什么就测什么，没实现的不测
- 穷举 = 每条路径的每种合理输入变体都要试：
  - 搜索 → 精确匹配、部分匹配、大写、小写、空搜索
  - 登录 → 正确账号、错误密码、空账号、空密码
  - 数值输入 → 正常值、边界值、零、负数

### 场景自包含原则（极其重要）
- 每个 scenario 必须能独立运行，不依赖前一个场景的状态
- 每个场景的第一步必须是 \`navigate\` 到起始页面
- 引擎会在每个场景开始前自动清除 cookie/storage，确保干净状态
- 禁止场景间传递状态（如场景1登录后场景2直接操作已登录页面）
- 正确写法：
  \`\`\`
  场景1： navigate→填用户名→填密码→点登录→断言成功
  场景2： navigate→填用户名→填错密码→点登录→断言失败
  \`\`\`
- 错误写法（禁止）：
  \`\`\`
  场景1： navigate→登录成功
  场景2： 点退出→填错密码→登录  ← 依赖场景1已登录，禁止！
  \`\`\`

### 操作→断言配对
- 每一个操作后面必须跟断言验证结果
- 错误：click登录按钮 → 结束（没验证是否登录成功）
- 正确：click登录按钮 → assert_text验证"欢迎回来"
- 没有断言的操作等于没测

### 功能全覆盖
- 先通读全部源代码，列出所有功能点
- 每个按钮、表单、Tab、弹窗、下拉框必须至少有一个测试场景
- 自检：数一数代码里有多少个可操作元素，蓝本是否每个都覆盖到了

### 选择器规范
- 使用代码中的真实 id（如 #login-btn）或稳定 class
- 禁止用 div:nth-child(3) 这类脆弱选择器
- 必须先阅读源代码确认选择器存在

### 截图策略（省钱省时）
- 每个蓝本模块的第1个场景末尾加1张 screenshot，其余场景不加
- 断言失败时引擎会自动截图留证，蓝本不用额外写
- ❌ 禁止每个场景末尾都加 screenshot

---

## 三、蓝本基本结构

\`\`\`json
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
\`\`\`

### platform 取值

| 值 | 适用场景 |
|----|---------|
| \`web\` | 网页应用（React/Vue/Angular/纯HTML） |
| \`desktop\` | Windows桌面应用（需额外填 \`window_title\`） |
| \`android\` | Android应用（需额外填 \`app_package\`、\`app_activity\`） |
| \`ios\` | iOS应用（需额外填 \`bundle_id\`） |
| \`miniprogram\` | 微信小程序（\`base_url\` 格式为 \`miniprogram://项目路径\`） |

### 步骤动作

| 动作 | 必填参数 | 说明 |
|------|---------|------|
| \`click\` | \`target\`, \`description\` | 点击元素 |
| \`fill\` | \`target\`, \`value\`, \`description\` | 输入文本 |
| \`select\` | \`target\`, \`value\`, \`description\` | 下拉框选择（\`<select>\`元素用select不用fill） |
| \`screenshot\` | \`description\` | 截图 |
| \`assert_text\` | \`expected\`, \`description\` | 断言页面包含文本 |
| \`wait\` | \`description\` | 等待（可用 \`value\` 指定毫秒） |
| \`navigate\` | \`value\`(URL), \`description\` | 页面跳转 |

### target 写法

- **Web/小程序**：CSS选择器，如 \`#loginBtn\`、\`.submit-btn\`、\`input[name="email"]\`
- **桌面应用**：\`name:屏幕上可见的原文\`，如 \`name:Login\`、\`name:确定\`
  - ⚠️ **禁止**在 \`name:\` 后加中文后缀（按钮/输入框/列表项等）
- **Android/iOS**：\`accessibility_id:xxx\` 或 \`id:xxx\`

### description 最佳实践

每个步骤的 \`description\` 应包含：
1. **位置**：上方/下方/左侧/右侧
2. **预期变化**：点击后页面会发生什么

\`\`\`
✅ "点击提交按钮，点击后表单数据提交到后端，页面显示'提交成功'提示"
❌ "点击按钮"
\`\`\`

---

## 四、蓝本增量维护（日常开发）

当项目已有蓝本文件时，以下代码变更**必须**同步更新蓝本：

| # | 触发条件 | 蓝本更新动作 |
|---|---------|------------|
| 1 | 新增/删除 UI 元素 | 添加/删除对应场景和步骤 |
| 2 | 修改元素 id/class/选择器 | 更新蓝本中所有用到该选择器的 \`target\` |
| 3 | 修改文本内容（按钮文字/提示/错误信息） | 更新 \`assert_text\` 的 \`expected\` |
| 4 | 修改业务逻辑（表单验证/跳转/计算） | 更新断言和预期结果 |
| 5 | 修复 Bug | 更新蓝本中对应断言 |
| 6 | 修改应用配置（URL/端口/路由） | 更新 \`base_url\` / \`start_command\` |

**已有蓝本时，只修改/新增变更涉及的场景，不要重写整个文件。**

---

## 五、蓝本自检清单

生成或修改蓝本后，逐项检查：

- [ ] 所有用户可交互功能都有对应场景
- [ ] \`target\` 选择器与实际代码中的 id/class 一致
- [ ] \`expected\` 是界面上实际会显示的文字（不是描述性文字）
- [ ] 页面切换后有 \`wait\` 步骤
- [ ] 每个场景自包含（第一步是navigate，不依赖前一个场景的状态）
- [ ] \`<select>\` 下拉框用 \`select\` 动作，不用 \`fill\`
- [ ] \`platform\` 字段正确
- [ ] \`base_url\` 和 \`start_command\` 填写正确

---

## 六、常见错误（经验教训）

| 错误 | 后果 | 正确做法 |
|------|------|---------|
| 对 \`<select>\` 元素用 \`fill\` | 引擎报错"Element is not an input" | 用 \`select\` 动作 |
| 场景依赖前一个场景的登录状态 | 引擎每场景清cookie，后续场景全部失败 | 每个场景独立登录 |
| 两个项目共用一个蓝本 | 选择器/路由不同导致全部失败 | 每个项目独立蓝本 |
| 蓝本里写死了注册的用户名 | 第二次测试时"用户已存在" | 用带时间戳的用户名或每次清数据 |
| 没有断言就结束场景 | 什么Bug都检测不到 | 每个操作后跟assert验证 |
`;
}

/**
 * 智能注入规则文件（只注入当前IDE对应的文件）
 * @param workspaceRoot 工作区根目录绝对路径
 * @param outputChannel 日志输出通道
 * @param forceAll 是否强制注入所有IDE规则（手动触发时用）
 * @returns 注入结果 { created: string[], skipped: string[] }
 */
export function injectRules(
  workspaceRoot: string,
  outputChannel?: vscode.OutputChannel,
  forceAll = false,
): { created: string[]; skipped: string[] } {
  const template = getTemplateContent();
  const created: string[] = [];
  const skipped: string[] = [];

  // 确定要注入的文件列表
  let filesToInject: string[];
  
  if (forceAll) {
    // 强制注入所有IDE规则（手动触发时）
    filesToInject = ["AGENTS.md", ...Object.values(IDE_RULES_MAP)];
  } else {
    // 智能注入：AGENTS.md + 当前IDE专用文件
    const currentIDE = detectCurrentIDE();
    filesToInject = ["AGENTS.md"];
    
    const ideRuleFile = IDE_RULES_MAP[currentIDE];
    if (ideRuleFile) {
      filesToInject.push(ideRuleFile);
    }
    
    outputChannel?.appendLine(`[TestPilot AI] 检测到当前IDE: ${currentIDE}`);
  }

  // 注入文件
  for (const relPath of filesToInject) {
    const fullPath = path.join(workspaceRoot, relPath);

    // 已存在则跳过（不覆盖用户自定义内容）
    if (fs.existsSync(fullPath)) {
      skipped.push(relPath);
      continue;
    }

    try {
      // 创建目录
      const dir = path.dirname(fullPath);
      if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
      }

      // 写入规则文件
      fs.writeFileSync(fullPath, template, "utf-8");
      created.push(relPath);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      outputChannel?.appendLine(`[TestPilot AI] ⚠️ 创建 ${relPath} 失败: ${msg}`);
    }
  }

  if (created.length > 0) {
    outputChannel?.appendLine(
      `[TestPilot AI] ✅ 已注入 ${created.length} 个规则文件: ${created.join(", ")}`,
    );
  }
  if (skipped.length > 0) {
    outputChannel?.appendLine(
      `[TestPilot AI] ⏭️ 跳过 ${skipped.length} 个已存在文件: ${skipped.join(", ")}`,
    );
  }

  return { created, skipped };
}

/**
 * 检查工作区是否需要注入规则（没有AGENTS.md时才需要）
 */
export function needsInjection(workspaceRoot: string): boolean {
  // 只检查 AGENTS.md 是否存在（跨工具通用文件）
  return !fs.existsSync(path.join(workspaceRoot, "AGENTS.md"));
}

/**
 * 插件激活时自动注入规则到所有工作区
 * 只在首次（工作区没有任何规则文件时）自动注入，不会重复打扰用户
 */
export async function autoInjectOnActivate(
  outputChannel?: vscode.OutputChannel,
): Promise<void> {
  const folders = vscode.workspace.workspaceFolders;
  if (!folders) { return; }

  for (const folder of folders) {
    const root = folder.uri.fsPath;

    // 跳过 TestPilotAI 项目本身（我们自己的项目已有规则）
    if (fs.existsSync(path.join(root, "cli.py")) && fs.existsSync(path.join(root, "src", "app.py"))) {
      outputChannel?.appendLine(`[TestPilot AI] 跳过 TestPilotAI 项目本身: ${root}`);
      continue;
    }

    // 检查是否需要注入
    if (needsInjection(root)) {
      outputChannel?.appendLine(`[TestPilot AI] 检测到 ${folder.name} 没有蓝本规则，自动注入中...`);
      const result = injectRules(root, outputChannel);

      if (result.created.length > 0) {
        vscode.window.showInformationMessage(
          `TestPilot AI: 已为 ${folder.name} 注入 ${result.created.length} 个编程AI规则文件，编程AI将自动生成测试蓝本`,
          "查看详情",
        ).then((action) => {
          if (action === "查看详情") {
            // 打开 AGENTS.md 让用户看看注入了什么
            const agentsPath = path.join(root, "AGENTS.md");
            if (fs.existsSync(agentsPath)) {
              vscode.workspace.openTextDocument(agentsPath).then((doc) => {
                vscode.window.showTextDocument(doc, { preview: true });
              });
            }
          }
        });
      }
    } else {
      outputChannel?.appendLine(`[TestPilot AI] ${folder.name} 已有规则文件，跳过注入`);
    }
  }
}
