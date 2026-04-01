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
const TEMPLATE_VERSION = 16;

/** 从文件内容中提取版本号，找不到返回 0（旧版无版本标记） */
function extractVersion(content: string): number {
  const match = content.match(/<!-- TestPilot-Template-Version: (\d+) -->/);
  return match ? parseInt(match[1], 10) : 0;
}

/** Template content injected into user projects as AGENTS.md / copilot-instructions.md */
function getTemplateContent(): string {
  return `<!-- TestPilot-Template-Version: ${TEMPLATE_VERSION} -->
# TestPilot AI  Blueprint Auto-Generation Rules

> This file is auto-injected by the TestPilot AI extension to guide AI coding assistants.
> You can freely modify this file to fit your project needs.

---

## Most Important Rule (MUST Follow Strictly)

Before generating any blueprint, you MUST determine the project \`platform\` type,
then open and read the corresponding platform rule file under \`.testpilot/platforms/\`:

| platform | Required reading |
|----------|-----------------|
| \`web\` | \`.testpilot/platforms/web.md\` |
| \`android\` | \`.testpilot/platforms/android.md\` |
| \`ios\` | \`.testpilot/platforms/ios.md\` |
| \`miniprogram\` | \`.testpilot/platforms/miniprogram.md\` |
| \`desktop\` | \`.testpilot/platforms/desktop.md\` |

**Generating a blueprint without reading the platform rules = guaranteed errors.**
Each platform has completely different selector formats, available actions, wait strategies, and template structure.

---

## ZERO: Platform Identification (determine before writing any blueprint)

**Do NOT generate any blueprint content until platform is confirmed.**

### Identification order (by priority)

1. **Check code file characteristics** (the only objective evidence):

| File / feature | platform |
|----------------|----------|
| \`pubspec.yaml\` / \`AndroidManifest.xml\` / \`*.kt\` / \`*.java\` | \`android\` |
| \`*.xcodeproj\` / \`*.swift\` / \`Info.plist\` | \`ios\` |
| \`app.json\` + \`pages/\` directory (mini program structure) | \`miniprogram\` |
| \`*.xaml\` / \`tkinter\` / \`pywinauto\` (pure native desktop, no embedded web) | \`desktop\` |
| \`package.json\` + \`electron\` dependency (Electron shell app) | **\`web\`** (NOT desktop! Electron content is a web page; Playwright selectors are far more accurate than desktop AI vision) |
| \`package.json\` + \`*.html\` / React / Vue / Angular | \`web\` |

> ⚠️ **Electron projects MUST use \`web\` not \`desktop\`**: Electron is just a shell; the actual content is a web page. \`desktop\` mode relies on AI visual screenshots (very inaccurate); \`web\` mode uses Playwright CSS selectors (faster and more reliable).

2. **Check existing blueprint \`platform\` field** — but verify against code features; code wins if they conflict
3. **Read \`testpilot/CHANGELOG.md\`** (if exists) — may state the platform
4. **If still unclear → ask the user**: "Is this Web / Android / iOS / Mini Program / Desktop?"

### Three cases when no blueprint exists (must distinguish clearly)

| Case | Assessment | Action |
|------|------------|--------|
| **Project completely empty** (no source files) | Nothing to test | **Wait silently** — do NOT write blueprint, do NOT bother user |
| **Has source code, platform identifiable, blueprint absent** (including manually deleted) | Can generate | **Scan source immediately, generate full blueprint — no user confirmation needed** |
| **Has source code, but platform unidentifiable** | Cannot generate | **Create minimal placeholder blueprint** (framework only, \`scenarios\` empty), then ask user for platform; fill in immediately after confirmation |

> ⚠️ **STRICTLY FORBIDDEN: asking the user "should I generate a blueprint?" when source code exists and platform is identified — generate it immediately!**

- **User description conflicts with code** → code wins; inform user

### Correcting wrong platform

If existing blueprint \`platform\` conflicts with code features:
1. Notify user immediately: "blueprint platform=web but project shows android, auto-correcting"
2. Update all blueprints \`platform\` field  re-read correct platform file  fix selectors/actions
3. No user confirmation needed  correct and notify

---

## ONE: Blueprint Language Rule

The \`name\`, \`description\`, \`expected\`, \`app_name\` fields MUST use the project UI language:
- If project UI text is Chinese  use Chinese in blueprints
- If project UI text is English  use English in blueprints
- \`expected\` assertions must exactly match the language actually rendered on screen

---

## TWO: When to Generate Blueprints

When the project does NOT have a \`testpilot.json\` or \`testpilot/\` directory,
after completing feature development you MUST auto-generate blueprint files.

| When | Action |
|------|--------|
| New project completed | Generate full blueprint covering all implemented features |
| New feature module added | Append corresponding scenarios to blueprint |
| Project has no blueprint yet | Scan existing code, generate full-coverage blueprint |

**Best practice:** Don't wait until all features are done. Add a scenario each time you implement a feature  your memory of selectors and expected values is clearest right then.

---

## THREE: Blueprint Management Rules

1. Blueprint files go in the \`testpilot/\` subdirectory under the project root
2. Pages  3: use a single \`testpilot.json\`; Pages > 3: split by feature module
3. Split naming: \`testpilot/module-name.testpilot.json\` (English, e.g. \`auth.testpilot.json\`)
4. **Update, don't recreate**: overwrite existing blueprints directly  NEVER create \`_v2\`, \`_new\`, \`_backup\` variants
5. Every blueprint must include \`app_name\`, \`description\`, \`platform\` fields

### platform field values

| Value | Use case | Extra required fields |
|-------|----------|-----------------------|
| \`web\` | Web apps (React/Vue/Angular/HTML) | \`base_url\`, \`start_command\` |
| \`android\` | Android/Flutter apps | \`app_package\`, \`app_activity\` |
| \`ios\` | iOS/SwiftUI apps (macOS only) | \`bundle_id\` |
| \`miniprogram\` | WeChat Mini Programs | \`base_url\` (miniprogram://path) |
| \`desktop\` | Windows desktop apps | \`window_title\` |

---

## FOUR: Incremental Blueprint Maintenance (6 triggers)

When a project already has blueprints, these code changes MUST sync to the blueprint:

| # | Trigger | Blueprint update action |
|---|---------|------------------------|
| 1 | Add/remove UI elements | Add/remove corresponding scenarios and steps |
| 2 | Change element selector (id/class/component name) | Update all \`target\` in blueprint |
| 3 | Change text content (button label/message/error) | Update \`assert_text\` \`expected\` values |
| 4 | Change business logic (validation/navigation/calculation) | Update assertions and expected results |
| 5 | Fix a Bug | Update corresponding assertions to detect that bug |
| 6 | Change app config (URL/port/route/start command) | Update \`base_url\` / \`start_command\` etc. |

**Does NOT trigger update:** Pure CSS styling, code comments, internal refactoring (no visible behavior change).

---

## FOUR-PLUS: Two Cross-Platform Iron Rules (all platforms, no exceptions)

> These two rules apply to Web / Android / iOS / Mini Program / Desktop.
> Platform-specific selector prohibitions (e.g. Web \`:contains()\`, Tailwind decimal classes) are defined in platform rule files — read them carefully.

### 🚨 Iron Rule 1: \`target\` attribute values MUST be copied from source code — never guessed

When using \`[title='xxx']\`, \`[placeholder='xxx']\`, \`[aria-label='xxx']\`, \`accessibility_id:xxx\` selectors:
1. **Open the source file containing the element first**
2. **Search the code for that attribute name** — confirm it exists and matches exactly
3. **NEVER guess attribute values from experience, common sense, or user description**

> Typical mistake: seeing a back-arrow button and guessing \`button[title='Back']\` when the source code has no \`title\` attribute → element never found, timeout.

### 🚨 Iron Rule 2: \`assert_text\` \`expected\` values MUST be copied verbatim from source code

1. **Find the corresponding text node in JSX/WXML/Swift/XML/Kotlin source** — copy it verbatim to \`expected\`
2. **NEVER create, paraphrase, or summarize text** (source says "Item A" → do NOT assert "Item B")
3. **NEVER assert text that never appears in the DOM/view tree** (internal variable names, code comments)

> Typical mistake: source only has text "X" and "Y" but asserts "Z" — that phrase appears nowhere in any source file → assertion always fails.

---

## FIVE: All Detailed Rules → Read Platform Rule File (MANDATORY)

**Selector prohibitions, action tables, complete JSON templates, flow mode, checklists, wait strategies, and gotcha tables are all defined in the platform-specific rule files.**

After confirming \`platform\`, **immediately open and read** \`.testpilot/platforms/{platform}.md\`
and strictly follow all rules in that file.

> ⚠️ The platform rule file is the final authority on blueprint quality. AGENTS.md defines general principles only; specific selector formats, forbidden syntax, and wait strategies are governed solely by the platform rule file.

**NEVER write a blueprint without reading the platform rule file.**

---

## SIX: Mandatory Self-Check Before Saving Blueprint

Before saving any blueprint file, the AI MUST self-check all of the following:

1. No bare tag selectors: 
  - Forbidden: 
    - \`button\`
    - \`div\`
    - \`span\`
    - \`a\`
  - Every click target must include a real attribute, stable class, parent scope, or verified \`:has-text()\`
2. Every attribute selector value must be searchable in source code:
  - \`[title='x']\`
  - \`[placeholder='x']\`
  - \`[aria-label='x']\`
  - \`[data-testid='x']\`
  - \`[name='x']\`
  If the exact value cannot be found in source code, do NOT use that selector.
3. Every \`assert_text.expected\` must be copied verbatim from source-rendered UI text, not summarized or paraphrased.
4. Routing mode must be checked before writing \`flow\` or page URLs:
  - If the project has no router library and uses store/state to switch components, treat it as state-based routing
  - In state-based routing projects, pages must default to \`flow: false\` and scenarios must enter submodules by UI clicks, not fake URLs
5. After writing selectors, perform a uniqueness review across the codebase. If a selector is likely to match multiple elements, refine it before saving.

If any self-check item fails, keep reading source code and revise the blueprint. Never guess and never save a half-correct blueprint.
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
    // 智能注入：AGENTS.md + 当前IDE + 已安装的AI扩展
    // （CLAUDE.md 只在检测到 Claude Code 扩展时才注入，不强制创建）
    const detectedIDEs = detectAllIDEs();
    filesToInject = ["AGENTS.md"];
    
    for (const ide of detectedIDEs) {
      const ruleFile = IDE_RULES_MAP[ide];
      if (ruleFile && !filesToInject.includes(ruleFile)) {
        filesToInject.push(ruleFile);
      }
    }
    
    // 额外：扫描所有已存在的规则文件，如果版本过旧也一并更新（防止跨IDE版本漂移）
    for (const [, ruleFile] of Object.entries(IDE_RULES_MAP)) {
      if (!filesToInject.includes(ruleFile)) {
        const ruleFullPath = path.join(workspaceRoot, ruleFile);
        if (fs.existsSync(ruleFullPath)) {
          filesToInject.push(ruleFile);
        }
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
        // 只通知真正的规则文件（排除平台模板 .testpilot/platforms/），避免每次版本更新都打扰用户
        const ruleFilesCreated = result.created.filter(f => !f.startsWith(".testpilot"));
        if (ruleFilesCreated.length > 0) {
          vscode.window.showInformationMessage(
            `TestPilot AI: 已为 ${folder.name} 注入 ${ruleFilesCreated.length} 个编程AI规则文件，编程AI将自动生成测试蓝本`,
            "查看详情",
          ).then((action) => {
            if (action === "查看详情") {
              const agentsPath = path.join(root, "AGENTS.md");
              if (fs.existsSync(agentsPath)) {
                vscode.workspace.openTextDocument(agentsPath).then((doc) => {
                  vscode.window.showTextDocument(doc, { preview: true });
                });
              }
            }
          });
        }
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
  let platformDetected = false;

  const listDir = (dir: string): string[] => {
    try { return fs.readdirSync(dir); } catch { return []; }
  };
  const rootFiles = listDir(workspaceRoot);

  // Flutter / Dart
  if (fs.existsSync(path.join(workspaceRoot, "pubspec.yaml"))) {
    platform = "android";
    platformDetected = true;
    try {
      const pubspec = fs.readFileSync(path.join(workspaceRoot, "pubspec.yaml"), "utf-8");
      const nameMatch = pubspec.match(/^name:\s*(.+)$/m);
      if (nameMatch) appName = nameMatch[1].trim();
    } catch { /* ignore */ }
  }
  // Android 原生（AndroidManifest.xml 或 .kt/.java 源码）
  else if (
    fs.existsSync(path.join(workspaceRoot, "app", "src", "main", "AndroidManifest.xml")) ||
    fs.existsSync(path.join(workspaceRoot, "AndroidManifest.xml"))
  ) {
    platform = "android";
    platformDetected = true;
  }
  // iOS / Swift（.xcodeproj / .xcworkspace / Package.swift）
  else if (
    fs.existsSync(path.join(workspaceRoot, "Package.swift")) ||
    rootFiles.some((f: string) => f.endsWith(".xcodeproj") || f.endsWith(".xcworkspace"))
  ) {
    platform = "ios";
    platformDetected = true;
  }
  // Node.js / Web / Electron
  else if (fs.existsSync(path.join(workspaceRoot, "package.json"))) {
    try {
      const pkg = JSON.parse(fs.readFileSync(path.join(workspaceRoot, "package.json"), "utf-8"));
      if (pkg.name) appName = pkg.name;
      // Electron 检测：Electron 项目本质是 Web 内容套了一个桌面壳，用 web 模式测试更准确（Playwright CSS选择器）
      // 只有纯桌面原生应用（无 web 内容、无 base_url）才应用 desktop 模式
      // 因此即使有 electron 依赖，也判定为 web——让 AI 用 Playwright 测试 Web 内容
      const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };
      if (allDeps["electron"]) {
        platform = "web";   // Electron 套壳 Web App，内容是 Web，用 web 模式更稳定
        platformDetected = true;
      }
    } catch { /* ignore */ }
    if (!platformDetected) {
      // 小程序检测
      if (fs.existsSync(path.join(workspaceRoot, "app.json")) && fs.existsSync(path.join(workspaceRoot, "app.wxss"))) {
        platform = "miniprogram";
        platformDetected = true;
      } else {
        platform = "web";
        platformDetected = true;
      }
    }
  }
  // 微信小程序（无 package.json）
  else if (fs.existsSync(path.join(workspaceRoot, "app.json")) && fs.existsSync(path.join(workspaceRoot, "app.js"))) {
    platform = "miniprogram";
    platformDetected = true;
  }
  // Python 桌面应用（tkinter / pywinauto）
  else if (rootFiles.some((f: string) => f.endsWith(".py"))) {
    platform = "desktop";
    platformDetected = true;
  }

  // 构造 description：未能识别时明确提示 AI 需要先判断 platform
  const platformNote = platformDetected
    ? `（已自动识别为 platform="${platform}"，请编程AI在生成蓝本前先核对代码特征确认无误）`
    : `（⚠️ 平台类型无法自动识别，编程AI必须先检查代码文件特征确认 platform 是 web/android/ios/miniprogram/desktop 中的哪一种，然后再生成蓝本）`;

  // 创建空壳蓝本
  const skeleton = {
    app_name: appName,
    description: `【占位蓝本，需编程AI补全】请先阅读 .testpilot/platforms/ 下对应平台规则文件，再扫描源码生成完整测试场景。${platformNote}`,
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
