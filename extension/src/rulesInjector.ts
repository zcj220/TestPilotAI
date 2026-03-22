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

/** 规则模板内容（精简版：通用规则 + 引导AI读取平台专属规则文件） */
function getTemplateContent(): string {
  return `# TestPilot AI — 编程AI蓝本自动生成规则

> 本文件由 TestPilot AI 插件自动注入，指导编程AI在开发过程中自动生成和维护测试蓝本。
> 你可以根据项目需求自由修改本文件内容。

---

## ⚠️ 最重要的一条规则（必须严格遵守）

生成蓝本前，你**必须**先确定项目的 \`platform\` 类型，然后打开并阅读 \`.testpilot/platforms/\` 目录下对应平台的规则文件：

| platform | 必读文件 |
|----------|---------|
| \`web\` | \`.testpilot/platforms/web.md\` |
| \`android\` | \`.testpilot/platforms/android.md\` |
| \`ios\` | \`.testpilot/platforms/ios.md\` |
| \`miniprogram\` | \`.testpilot/platforms/miniprogram.md\` |
| \`desktop\` | \`.testpilot/platforms/desktop.md\` |

**不读平台规则就生成蓝本 = 必然出错。** 每个平台的选择器格式、可用动作、等待策略、模板结构完全不同。通用规则无法覆盖平台差异。

---

## 零、蓝本语言规则

蓝本中的 \`name\`、\`description\`、\`expected\`、\`app_name\` 等文字内容**必须使用用户项目的语言**：
- 如果项目的 UI 文字是中文 → 蓝本用中文
- 如果项目的 UI 文字是英文 → 蓝本用英文
- \`expected\` 断言内容必须与 UI 实际渲染的语言完全一致（否则断言必定失败）

---

## 一、蓝本生成时机

当项目中**不存在** \`testpilot.json\` 或 \`testpilot/\` 目录时，你在完成功能开发后**必须**自动生成蓝本文件。

| 时机 | 动作 |
|------|------|
| 新项目创建完成 | 生成完整蓝本，覆盖所有已实现功能 |
| 新增一个完整功能模块 | 在蓝本中追加对应场景 |
| 项目初始蓝本不存在 | 扫描现有代码，生成功能全覆盖的蓝本 |

**最佳实践**：不要等项目全部写完才生成蓝本，而是**每实现一个功能就追加一个场景**。刚写完代码时记忆最清晰，选择器和预期值一定准确。

---

## 二、蓝本管理规则

1. 蓝本文件放在**当前项目根目录**的 \`testpilot/\` 子目录下
2. 页面≤3个用单个 \`testpilot.json\`；页面>3个按功能模块拆分
3. 拆分命名：\`testpilot/模块名.testpilot.json\`（英文，如 \`auth.testpilot.json\`）
4. **更新而非新建**：已存在同名蓝本直接覆盖，**禁止**创建 \`_v2\`、\`_new\`、\`_backup\` 变体
5. 每个蓝本必须包含 \`app_name\`、\`description\`、\`platform\` 字段

### platform 取值

| 值 | 适用场景 | 额外必填字段 |
|----|---------|------------|
| \`web\` | 网页应用（React/Vue/Angular/纯HTML） | \`base_url\`、\`start_command\` |
| \`android\` | Android/Flutter 应用 | \`app_package\`、\`app_activity\` |
| \`ios\` | iOS/SwiftUI 应用（仅macOS） | \`bundle_id\` |
| \`miniprogram\` | 微信小程序 | \`base_url\`（miniprogram://路径） |
| \`desktop\` | Windows桌面应用 | \`window_title\` |

---

## 三、蓝本增量维护（6种触发条件）

当项目已有蓝本文件时，以下代码变更**必须**同步更新蓝本：

| # | 触发条件 | 蓝本更新动作 |
|---|---------|------------|
| 1 | 新增/删除 UI 元素 | 添加/删除对应场景和步骤 |
| 2 | 修改元素选择器（id/class/组件名） | 更新蓝本中所有 \`target\` |
| 3 | 修改文本内容（按钮文字/提示/错误信息） | 更新 \`assert_text\` 的 \`expected\` |
| 4 | 修改业务逻辑（表单验证/跳转/计算） | 更新断言和预期结果 |
| 5 | 修复 Bug | 更新蓝本中对应断言 |
| 6 | 修改应用配置（URL/端口/路由/启动命令） | 更新 \`base_url\` / \`start_command\` 等 |

**不触发更新**：纯CSS样式调整、代码注释修改、内部重构（不影响用户可见行为）。

---

## 三点五、连续流模式（flow）

蓝本默认每个场景独立运行（自包含，首步 navigate 冷启动）。但对于**同一页面内的连续操作**，可以启用连续流模式，让场景之间不重启应用、不清除状态，按真实用户操作路径连续执行。

### 启用方式

在 \`page\` 级别添加 \`"flow": true\`：

\`\`\`json
{
  "pages": [
    {
      "url": "",
      "title": "报表页面",
      "flow": true,
      "scenarios": [
        {
          "name": "查看利润表",
          "steps": [
            {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "冷启动应用"},
            {"action": "wait", "value": "3000"},
            {"action": "click", "target": "...", "description": "进入报表页"},
            {"action": "assert_text", "expected": "利润表"}
          ]
        },
        {
          "name": "切换到费用表",
          "steps": [
            {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "（flow模式下自动跳过）"},
            {"action": "click", "target": "...", "description": "点击费用标签"},
            {"action": "assert_text", "expected": "费用分析"}
          ]
        },
        {
          "name": "下载报表",
          "steps": [
            {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "（flow模式下自动跳过）"},
            {"action": "click", "target": "...", "description": "点击下载按钮"},
            {"action": "assert_text", "expected": "下载成功"}
          ]
        }
      ]
    }
  ]
}
\`\`\`

### flow 模式的行为

| 行为 | \`flow: false\`（默认） | \`flow: true\` |
|------|----------------------|---------------|
| 场景首步 navigate | 执行（冷启动） | **仅第1个场景执行**，后续场景的 navigate 自动跳过 |
| 场景间状态 | 清除（Cookie/Storage/应用重启） | **保持**（前一场景结束时的页面状态） |
| 步骤失败恢复 | AI中枢决策：重试→跳过步骤→跳过场景 | 同左，但跳过场景后**继续下一场景**（不放弃整个 page） |
| 连续失败止损 | 3个场景连续失败 → 终止 | 3个场景连续失败 → **冷启动恢复**后继续（而非终止） |

### 什么时候用 flow

- ✅ 同一页面内的 Tab 切换（报表页：利润表→费用表→分类表）
- ✅ 连续操作流程（添加商品→编辑→删除）
- ✅ 需要测试页面间导航是否正常（从A页面到B页面）
- ❌ 需要干净状态的独立测试（登录成功 vs 登录失败）
- ❌ 不同用户角色的测试场景

### 重要：flow 场景仍需保留 navigate 步骤

即使开启了 flow 模式，每个场景的 \`steps\` 中**仍然要写 navigate 步骤**。这是因为：
1. 单独运行某个场景时，navigate 是必需的
2. flow 模式下引擎会自动跳过非首个场景的 navigate
3. 保持蓝本结构一致性，方便切换 flow 开关

---

## 四、蓝本通用自检清单

生成或修改蓝本后，逐项检查：

- [ ] 所有用户可交互功能都有对应场景
- [ ] 每个场景自包含（第一步是 navigate），或页面启用了 \`flow: true\` 连续流模式
- [ ] \`platform\` 字段正确
- [ ] **已阅读对应平台规则文件**，选择器/动作/模板符合平台要求
- [ ] \`target\` 选择器在源码中确实存在（已搜索验证）
- [ ] \`expected\` 是界面上实际渲染的持久化文字（不是瞬态提示、不是变量名、不是注释）
- [ ] 异步操作后有足够的 \`wait\` 时间（已检查代码中的延迟/API调用）
- [ ] 页面跳转后有 \`wait\` + \`assert_text\` 验证到达目标页
- [ ] 每个操作后有断言验证结果（不能只操作不验证）

---

## 五、description 最佳实践

每个步骤的 \`description\` 应包含位置和预期变化：

\`\`\`
✅ "点击提交按钮，点击后表单数据提交到后端，页面显示'提交成功'提示"
✅ "在页面中部的用户名输入框输入admin，输入后输入框显示admin"
❌ "点击按钮"
❌ "输入用户名"
\`\`\`

---

## 六、选择器、动作表、模板、注意事项 → 参见平台规则

**禁止在不阅读平台规则的情况下编写蓝本。** 以下内容在各平台规则文件中定义，不在本文件重复：

- 该平台的封闭式动作表（只允许列出的动作）
- 该平台的选择器格式、优先级、禁止列表
- 该平台的完整 JSON 模板
- 该平台的瞬态 UI 不可断言清单
- 该平台的等待时间计算公式
- 该平台的踩坑清单和常见错误
- 该平台的代码稽核要求

请在确定 \`platform\` 后，立即打开 \`.testpilot/platforms/{platform}.md\` 阅读完整规则。
`;
}

/** 平台模板文件列表 */
const PLATFORM_FILES = ["web.md", "android.md", "ios.md", "miniprogram.md", "desktop.md"];

/**
 * 获取平台模板文件内容（从插件内置的 templates 目录读取）
 * @param extensionPath 插件安装路径
 * @returns 平台名 → 文件内容 的 Map
 */
function getPlatformTemplates(extensionPath: string): Map<string, string> {
  const templates = new Map<string, string>();
  const templatesDir = path.join(extensionPath, "templates", "platforms");

  for (const fileName of PLATFORM_FILES) {
    const filePath = path.join(templatesDir, fileName);
    try {
      if (fs.existsSync(filePath)) {
        templates.set(fileName, fs.readFileSync(filePath, "utf-8"));
      }
    } catch {
      // 静默忽略读取失败
    }
  }
  return templates;
}

/**
 * 注入平台模板文件到用户项目的 .testpilot/platforms/ 目录
 * @param workspaceRoot 工作区根目录
 * @param extensionPath 插件安装路径
 * @param outputChannel 日志输出通道
 * @returns 创建的文件列表
 */
function injectPlatformTemplates(
  workspaceRoot: string,
  extensionPath: string,
  outputChannel?: vscode.OutputChannel,
): string[] {
  const created: string[] = [];
  const templates = getPlatformTemplates(extensionPath);
  const targetDir = path.join(workspaceRoot, ".testpilot", "platforms");

  // 如果 .testpilot/platforms 目录已存在并且有内容，跳过
  if (fs.existsSync(targetDir)) {
    const existing = fs.readdirSync(targetDir).filter((f: string) => f.endsWith(".md"));
    if (existing.length >= PLATFORM_FILES.length) {
      outputChannel?.appendLine(`[TestPilot AI] ⏭️ .testpilot/platforms/ 已有 ${existing.length} 个模板，跳过`);
      return created;
    }
  }

  // 创建目录
  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }

  // 写入每个平台模板（不存在才创建）
  for (const [fileName, content] of templates) {
    const targetPath = path.join(targetDir, fileName);
    if (!fs.existsSync(targetPath)) {
      try {
        fs.writeFileSync(targetPath, content, "utf-8");
        created.push(`.testpilot/platforms/${fileName}`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel?.appendLine(`[TestPilot AI] ⚠️ 创建 ${fileName} 失败: ${msg}`);
      }
    }
  }

  if (created.length > 0) {
    outputChannel?.appendLine(
      `[TestPilot AI] ✅ 已注入 ${created.length} 个平台模板: ${created.join(", ")}`,
    );
  }
  return created;
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
  extensionPath = "",
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

  // TestPilot 内容标记（用于检测是否已追加过）
  const TESTPILOT_MARKER = "# TestPilot AI — 编程AI蓝本自动生成规则";

  // 注入文件
  for (const relPath of filesToInject) {
    const fullPath = path.join(workspaceRoot, relPath);
    const isAgentsMd = relPath === "AGENTS.md" || relPath === "CLAUDE.md";

    if (fs.existsSync(fullPath)) {
      if (isAgentsMd) {
        // AGENTS.md / CLAUDE.md 是 TestPilot 专属文件，已存在则跳过
        skipped.push(relPath);
        continue;
      }

      // IDE 专用规则文件（如 .github/copilot-instructions.md）：追加模式
      try {
        const existingContent = fs.readFileSync(fullPath, "utf-8");
        if (existingContent.includes(TESTPILOT_MARKER)) {
          // 已包含 TestPilot 规则，跳过
          skipped.push(relPath);
          continue;
        }
        // 在用户已有内容末尾追加 TestPilot 规则
        const separator = "\n\n---\n\n";
        fs.writeFileSync(fullPath, existingContent.trimEnd() + separator + template, "utf-8");
        created.push(relPath + " (追加)");
        outputChannel?.appendLine(
          `[TestPilot AI] 📎 已将蓝本规则追加到已有文件: ${relPath}`,
        );
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel?.appendLine(`[TestPilot AI] ⚠️ 追加 ${relPath} 失败: ${msg}`);
      }
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

  // 注入平台模板文件到 .testpilot/platforms/
  outputChannel?.appendLine(`[TestPilot AI] extensionPath="${extensionPath}"`);
  if (extensionPath) {
    const templatesCheck = path.join(extensionPath, "templates", "platforms");
    outputChannel?.appendLine(`[TestPilot AI] 模板目录: ${templatesCheck}, 存在=${fs.existsSync(templatesCheck)}`);
    const platformCreated = injectPlatformTemplates(workspaceRoot, extensionPath, outputChannel);
    created.push(...platformCreated);
    outputChannel?.appendLine(`[TestPilot AI] 平台模板注入结果: ${platformCreated.length} 个文件`);
  } else {
    outputChannel?.appendLine(`[TestPilot AI] ⚠️ extensionPath 为空，跳过平台模板注入！`);
  }

  return { created, skipped };
}

/**
 * 检查工作区是否需要注入规则
 * 缺少 AGENTS.md 或缺少 .testpilot/platforms 目录都需要注入
 */
export function needsInjection(workspaceRoot: string): boolean {
  if (!fs.existsSync(path.join(workspaceRoot, "AGENTS.md"))) {
    return true;
  }
  // 检查平台模板是否已注入
  const platformDir = path.join(workspaceRoot, ".testpilot", "platforms");
  if (!fs.existsSync(platformDir)) {
    return true;
  }
  const existing = fs.readdirSync(platformDir).filter((f: string) => f.endsWith(".md"));
  return existing.length < PLATFORM_FILES.length;
}

/**
 * 插件激活时自动注入规则到所有工作区
 * 只在首次（工作区没有任何规则文件时）自动注入，不会重复打扰用户
 */
export async function autoInjectOnActivate(
  outputChannel?: vscode.OutputChannel,
  extensionPath = "",
): Promise<void> {
  outputChannel?.appendLine(`[TestPilot AI] autoInjectOnActivate 启动, extensionPath=${extensionPath}`);
  const folders = vscode.workspace.workspaceFolders;
  if (!folders) {
    outputChannel?.appendLine(`[TestPilot AI] 没有工作区文件夹，跳过`);
    return;
  }

  outputChannel?.appendLine(`[TestPilot AI] 发现 ${folders.length} 个工作区文件夹`);

  for (const folder of folders) {
    const root = folder.uri.fsPath;
    outputChannel?.appendLine(`[TestPilot AI] 检查文件夹: ${folder.name} (${root})`);

    // 跳过 TestPilotAI 项目本身（我们自己的项目已有规则）
    if (fs.existsSync(path.join(root, "cli.py")) && fs.existsSync(path.join(root, "src", "app.py"))) {
      outputChannel?.appendLine(`[TestPilot AI] 跳过 TestPilotAI 项目本身: ${root}`);
      continue;
    }

    // 检查是否需要注入
    const needs = needsInjection(root);
    outputChannel?.appendLine(`[TestPilot AI] ${folder.name} needsInjection=${needs}`);
    if (needs) {
      outputChannel?.appendLine(`[TestPilot AI] 检测到 ${folder.name} 没有蓝本规则，自动注入中...`);
      const result = injectRules(root, outputChannel, false, extensionPath);

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
