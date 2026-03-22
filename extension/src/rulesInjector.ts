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

  if (appName.includes("trae")) return "trae";
  if (appName.includes("windsurf")) return "windsurf";
  if (appName.includes("cursor")) return "cursor";
  if (appName.includes("vscodium")) return "vscodium";
  if (appName.includes("positron")) return "vscode";   // Posit的IDE，基于VS Code
  if (appName.includes("theia")) return "vscode";      // Eclipse Theia
  if (appName.includes("code - oss")) return "vscode"; // 开源版VS Code
  return "vscode";
}

/**
 * 检测所有应该注入规则的IDE列表
 * 除当前IDE外，还检测已安装的AI扩展（Cline/Augment等）
 */
function detectAllIDEs(): string[] {
  const ides = new Set<string>();
  ides.add(detectCurrentIDE());

  // 检测已安装的AI编程扩展
  const extensionChecks: [string[], string][] = [
    [["saoudrizwan.claude-dev", "cline.cline"], "cline"],
    [["augment.augment-vscode", "augmentcode.augment"], "augment"],
    [["anthropics.claude-code"], "claude"],
    [["kilocode.kilocode", "nicepkg.aide-pro"], "cline"], // Kilo Code等Cline分支用同clinerules
  ];
  for (const [extIds, ideKey] of extensionChecks) {
    for (const extId of extIds) {
      if (vscode.extensions.getExtension(extId)) {
        ides.add(ideKey);
        break;
      }
    }
  }

  return Array.from(ides);
}

/**
 * 模板版本号。每次更新模板内容时递增。
 * rulesInjector 会检测已注入文件的版本号，低于此版本则自动更新。
 */
const TEMPLATE_VERSION = 2;

/** 从文件内容中提取版本号，找不到返回 0（旧版无版本标记） */
function extractVersion(content: string): number {
  const match = content.match(/<!-- TestPilot-Template-Version: (\d+) -->/);
  return match ? parseInt(match[1], 10) : 0;
}

/** 规则模板内容（精简版：通用规则 + 引导AI读取平台专属规则文件） */
function getTemplateContent(): string {
  return `<!-- TestPilot-Template-Version: ${TEMPLATE_VERSION} -->
# TestPilot AI — 编程AI蓝本自动生成规则

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

## 三点五、连续流模式（flow）— 强制决策

### ⚠️ 必须执行的决策步骤

生成蓝本时，你**必须**对每个 \`page\` 做出 flow 决策，不允许跳过：

**判断规则（按顺序检查）：**
1. 该 page 下有 ≥2 个场景，且这些场景都需要先登录才能操作？→ **\`"flow": true\`**
2. 该 page 下有 ≥2 个场景是同一页面内的 Tab 切换或连续操作？→ **\`"flow": true\`**
3. 该 page 下的场景需要互相独立的干净状态（如：正确登录 vs 错误登录 vs 空字段）？→ **\`"flow": false\`**（可省略，默认就是 false）

**常见错误（你必须避免）：**
- ❌ 记账台有8个场景（添加交易、删除交易、切换类型…），每个都独立冷启动+登录 → **严重浪费！必须 flow: true**
- ❌ 报表页有6个场景（看利润表、看费用表、下载报表…），每个都冷启动+登录+跳转到报表页 → **严重浪费！必须 flow: true**
- ✅ 登录页有4个场景（正确登录、空用户名、错密码、注册），每个需要干净状态 → flow: false，正确

**简单总结：如果多个场景都要先登录再操作同一个页面，那这个 page 必须设 \`"flow": true\`。**

### 启用方式

在 \`page\` 对象中添加 \`"flow": true\`：

\`\`\`json
{
  "pages": [
    {
      "url": "",
      "title": "记账台",
      "flow": true,
      "scenarios": [
        {
          "name": "登录进入记账台",
          "steps": [
            {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "冷启动应用"},
            {"action": "wait", "value": "3000"},
            {"action": "fill", "target": "...", "value": "admin"},
            {"action": "click", "target": "...", "description": "登录"},
            {"action": "wait", "value": "3000"},
            {"action": "assert_text", "expected": "记账台"}
          ]
        },
        {
          "name": "添加一笔交易",
          "steps": [
            {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "（flow模式下自动跳过）"},
            {"action": "fill", "target": "...", "value": "50.00", "description": "输入金额"},
            {"action": "click", "target": "...", "description": "提交"},
            {"action": "assert_text", "expected": "50.00"}
          ]
        },
        {
          "name": "删除交易",
          "steps": [
            {"action": "navigate", "value": "com.example.app/.MainActivity", "description": "（flow模式下自动跳过）"},
            {"action": "click", "target": "...", "description": "删除"},
            {"action": "assert_text", "expected": "已删除"}
          ]
        }
      ]
    }
  ]
}
\`\`\`

**注意看：** 只有第1个场景做了完整的登录流程，后续场景直接在当前页面操作。navigate 步骤仍然保留（方便单独运行），但 flow 模式下引擎会自动跳过。

### flow 模式的行为

| 行为 | \`flow: false\`（默认） | \`flow: true\` |
|------|----------------------|---------------|
| 场景首步 navigate | 执行（冷启动） | **仅第1个场景执行**，后续场景的 navigate 自动跳过 |
| 场景间状态 | 清除（应用重启） | **保持**（前一场景的页面状态） |
| 连续失败止损 | 3个场景连续失败 → 终止 | 3个场景连续失败 → **冷启动恢复**后继续 |

---

## 四、蓝本通用自检清单

生成或修改蓝本后，**按顺序**逐项检查：

- [ ] **【最重要】每个 page 都做了 flow 决策**：多场景共享登录状态 → \`"flow": true\`；需要干净状态的独立测试 → 不写 flow
- [ ] 所有用户可交互功能都有对应场景
- [ ] 每个场景的第一步是 navigate（flow 模式下引擎自动跳过非首场景的 navigate）
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

  // 检查 .testpilot/platforms 目录
  if (fs.existsSync(targetDir)) {
    const existing = fs.readdirSync(targetDir).filter((f: string) => f.endsWith(".md"));
    if (existing.length >= PLATFORM_FILES.length) {
      // 所有文件都存在，检查版本号决定是否需要更新
      let needsUpdate = false;
      for (const fileName of PLATFORM_FILES) {
        const targetPath = path.join(targetDir, fileName);
        if (fs.existsSync(targetPath)) {
          const content = fs.readFileSync(targetPath, "utf-8");
          const ver = extractVersion(content);
          if (ver < TEMPLATE_VERSION) {
            needsUpdate = true;
            break;
          }
        }
      }
      if (!needsUpdate) {
        outputChannel?.appendLine(`[TestPilot AI] ⏭️ .testpilot/platforms/ 已有 ${existing.length} 个模板且版本最新，跳过`);
        return created;
      }
      outputChannel?.appendLine(`[TestPilot AI] 🔄 .testpilot/platforms/ 版本过旧，更新中...`);
    }
  }

  // 创建目录
  if (!fs.existsSync(targetDir)) {
    fs.mkdirSync(targetDir, { recursive: true });
  }

  // 写入每个平台模板（不存在则创建，版本过旧则更新）
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
    } else {
      // 已存在：检查版本号
      try {
        const existingContent = fs.readFileSync(targetPath, "utf-8");
        const existingVersion = extractVersion(existingContent);
        if (existingVersion < TEMPLATE_VERSION) {
          fs.writeFileSync(targetPath, content, "utf-8");
          created.push(`.testpilot/platforms/${fileName} (v${existingVersion}→v${TEMPLATE_VERSION})`);
        }
      } catch {
        // 静默忽略
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
    // 智能注入：AGENTS.md + CLAUDE.md + 当前IDE + 已安装的AI扩展
    const detectedIDEs = detectAllIDEs();
    filesToInject = ["AGENTS.md", "CLAUDE.md"];
    
    for (const ide of detectedIDEs) {
      const ruleFile = IDE_RULES_MAP[ide];
      if (ruleFile && !filesToInject.includes(ruleFile)) {
        filesToInject.push(ruleFile);
      }
    }
    
    outputChannel?.appendLine(`[TestPilot AI] 检测到IDE: ${detectedIDEs.join(", ")}`);
  }

  // TestPilot 内容标记（用于检测是否已追加过）
  const TESTPILOT_MARKER = "# TestPilot AI — 编程AI蓝本自动生成规则";

  // 注入文件
  for (const relPath of filesToInject) {
    const fullPath = path.join(workspaceRoot, relPath);
    const isAgentsMd = relPath === "AGENTS.md" || relPath === "CLAUDE.md";

    if (fs.existsSync(fullPath)) {
      if (isAgentsMd) {
        // AGENTS.md / CLAUDE.md：检查版本号，旧版本则自动更新
        try {
          const existingContent = fs.readFileSync(fullPath, "utf-8");
          const existingVersion = extractVersion(existingContent);
          if (existingVersion >= TEMPLATE_VERSION) {
            skipped.push(relPath);
            continue;
          }
          // 版本过旧，更新文件
          fs.writeFileSync(fullPath, template, "utf-8");
          created.push(relPath + ` (v${existingVersion}→v${TEMPLATE_VERSION})`);
          outputChannel?.appendLine(
            `[TestPilot AI] 🔄 ${relPath} 版本过旧(v${existingVersion})，已更新到 v${TEMPLATE_VERSION}`,
          );
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          outputChannel?.appendLine(`[TestPilot AI] ⚠️ 更新 ${relPath} 失败: ${msg}`);
          skipped.push(relPath);
        }
        continue;
      }

      // IDE 专用规则文件（如 .github/copilot-instructions.md）：追加模式
      try {
        const existingContent = fs.readFileSync(fullPath, "utf-8");
        if (existingContent.includes(TESTPILOT_MARKER)) {
          // 已包含 TestPilot 规则，检查版本
          const existingVersion = extractVersion(existingContent);
          if (existingVersion >= TEMPLATE_VERSION) {
            skipped.push(relPath);
            continue;
          }
          // 版本过旧：替换 TestPilot 部分（保留用户自己的内容）
          const markerIndex = existingContent.indexOf(TESTPILOT_MARKER);
          // 向前找分隔线或版本标记
          let startIndex = existingContent.lastIndexOf("---", markerIndex);
          if (startIndex === -1) startIndex = existingContent.lastIndexOf("<!-- TestPilot", markerIndex);
          if (startIndex === -1) startIndex = markerIndex;
          const userContent = existingContent.substring(0, startIndex).trimEnd();
          if (userContent.length > 0) {
            fs.writeFileSync(fullPath, userContent + "\n\n---\n\n" + template, "utf-8");
          } else {
            fs.writeFileSync(fullPath, template, "utf-8");
          }
          created.push(relPath + ` (v${existingVersion}→v${TEMPLATE_VERSION})`);
          outputChannel?.appendLine(
            `[TestPilot AI] 🔄 ${relPath} TestPilot规则已更新到 v${TEMPLATE_VERSION}`,
          );
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
 * 缺少 AGENTS.md、.testpilot/platforms 目录不全、或版本过旧都需要注入
 */
export function needsInjection(workspaceRoot: string): boolean {
  const agentsPath = path.join(workspaceRoot, "AGENTS.md");
  if (!fs.existsSync(agentsPath)) {
    return true;
  }
  // 检查 AGENTS.md 版本号
  try {
    const content = fs.readFileSync(agentsPath, "utf-8");
    if (extractVersion(content) < TEMPLATE_VERSION) {
      return true;
    }
  } catch {
    return true;
  }
  // 检查平台模板是否已注入
  const platformDir = path.join(workspaceRoot, ".testpilot", "platforms");
  if (!fs.existsSync(platformDir)) {
    return true;
  }
  const existing = fs.readdirSync(platformDir).filter((f: string) => f.endsWith(".md"));
  if (existing.length < PLATFORM_FILES.length) {
    return true;
  }
  // 检查平台模板版本
  for (const fileName of PLATFORM_FILES) {
    const filePath = path.join(platformDir, fileName);
    if (fs.existsSync(filePath)) {
      try {
        const content = fs.readFileSync(filePath, "utf-8");
        if (extractVersion(content) < TEMPLATE_VERSION) {
          return true;
        }
      } catch {
        return true;
      }
    }
  }
  return false;
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

    // 检查是否有蓝本文件，没有则创建空壳蓝本
    ensureSkeletonBlueprint(root, outputChannel);
  }
}

/**
 * 确保项目有蓝本文件（至少一个空壳）。
 * 如果 testpilot/ 目录不存在或为空，自动创建一个骨架蓝本，
 * 使项目始终出现在插件面板中。
 */
function ensureSkeletonBlueprint(
  workspaceRoot: string,
  outputChannel?: vscode.OutputChannel,
): void {
  const testpilotDir = path.join(workspaceRoot, "testpilot");
  const rootBlueprint = path.join(workspaceRoot, "testpilot.json");

  // 如果已有蓝本文件，跳过
  if (fs.existsSync(rootBlueprint)) return;
  if (fs.existsSync(testpilotDir)) {
    try {
      const files = fs.readdirSync(testpilotDir).filter((f: string) => f.endsWith(".json"));
      if (files.length > 0) return;
    } catch { /* ignore */ }
  }

  // 检测项目类型和名称
  const folderName = path.basename(workspaceRoot);
  let appName = folderName;
  let platform = "web";

  // Flutter / Dart
  if (fs.existsSync(path.join(workspaceRoot, "pubspec.yaml"))) {
    platform = "android";
    try {
      const pubspec = fs.readFileSync(path.join(workspaceRoot, "pubspec.yaml"), "utf-8");
      const nameMatch = pubspec.match(/^name:\s*(.+)$/m);
      if (nameMatch) appName = nameMatch[1].trim();
    } catch { /* ignore */ }
  }
  // Node.js / Web
  else if (fs.existsSync(path.join(workspaceRoot, "package.json"))) {
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(workspaceRoot, "package.json"), "utf-8"));
      if (pkg.name) appName = pkg.name;
    } catch { /* ignore */ }
    // 小程序检测
    if (fs.existsSync(path.join(workspaceRoot, "app.json")) && fs.existsSync(path.join(workspaceRoot, "app.wxss"))) {
      platform = "miniprogram";
    }
  }
  // 微信小程序（无 package.json）
  else if (fs.existsSync(path.join(workspaceRoot, "app.json")) && fs.existsSync(path.join(workspaceRoot, "app.js"))) {
    platform = "miniprogram";
  }
  // iOS / Swift
  else if (fs.existsSync(path.join(workspaceRoot, "Package.swift")) || fs.readdirSync(workspaceRoot).some((f: string) => f.endsWith(".xcodeproj") || f.endsWith(".xcworkspace"))) {
    platform = "ios";
  }

  // 创建空壳蓝本
  const skeleton = {
    app_name: appName,
    description: `请让编程AI为 ${appName} 生成完整的测试蓝本（当前为空壳，尚无测试场景）`,
    base_url: platform === "web" ? "http://localhost:3000" : "",
    platform: platform,
    start_command: "",
    pages: [],
  };

  try {
    if (!fs.existsSync(testpilotDir)) {
      fs.mkdirSync(testpilotDir, { recursive: true });
    }
    const skeletonPath = path.join(testpilotDir, "testpilot.json");
    fs.writeFileSync(skeletonPath, JSON.stringify(skeleton, null, 2), "utf-8");
    outputChannel?.appendLine(`[TestPilot AI] 📦 已为 ${appName} 创建空壳蓝本: testpilot/testpilot.json`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    outputChannel?.appendLine(`[TestPilot AI] ⚠️ 创建空壳蓝本失败: ${msg}`);
  }
}
