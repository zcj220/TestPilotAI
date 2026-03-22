// 临时脚本：替换 rulesInjector.ts 中的 getTemplateContent 函数
// 并在 injectRules 中加入平台模板注入逻辑
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, 'rulesInjector.ts');
let content = fs.readFileSync(filePath, 'utf-8');

// ============ 第一步：替换 getTemplateContent 函数 ============
const marker1 = '/** 规则模板内容（内嵌，避免依赖外部文件） */';
const marker2 = '/**\n * 智能注入规则文件';

const funcStart = content.indexOf(marker1);
const funcEnd = content.indexOf(marker2);

if (funcStart === -1 || funcEnd === -1) {
  console.error('FATAL: Cannot find markers!', funcStart, funcEnd);
  process.exit(1);
}

// 新的 getTemplateContent + 平台模板相关函数
const newFunctions = `/** 规则模板内容（精简版：通用规则 + 引导AI读取平台专属规则文件） */
function getTemplateContent(): string {
  return \`# TestPilot AI — 编程AI蓝本自动生成规则

> 本文件由 TestPilot AI 插件自动注入，指导编程AI在开发过程中自动生成和维护测试蓝本。
> 你可以根据项目需求自由修改本文件内容。

---

## ⚠️ 最重要的一条规则（必须严格遵守）

生成蓝本前，你**必须**先确定项目的 \\\`platform\\\` 类型，然后打开并阅读 \\\`.testpilot/platforms/\\\` 目录下对应平台的规则文件：

| platform | 必读文件 |
|----------|---------|
| \\\`web\\\` | \\\`.testpilot/platforms/web.md\\\` |
| \\\`android\\\` | \\\`.testpilot/platforms/android.md\\\` |
| \\\`ios\\\` | \\\`.testpilot/platforms/ios.md\\\` |
| \\\`miniprogram\\\` | \\\`.testpilot/platforms/miniprogram.md\\\` |
| \\\`desktop\\\` | \\\`.testpilot/platforms/desktop.md\\\` |

**不读平台规则就生成蓝本 = 必然出错。** 每个平台的选择器格式、可用动作、等待策略、模板结构完全不同。通用规则无法覆盖平台差异。

---

## 一、蓝本生成时机

当项目中**不存在** \\\`testpilot.json\\\` 或 \\\`testpilot/\\\` 目录时，你在完成功能开发后**必须**自动生成蓝本文件。

| 时机 | 动作 |
|------|------|
| 新项目创建完成 | 生成完整蓝本，覆盖所有已实现功能 |
| 新增一个完整功能模块 | 在蓝本中追加对应场景 |
| 项目初始蓝本不存在 | 扫描现有代码，生成功能全覆盖的蓝本 |

**最佳实践**：不要等项目全部写完才生成蓝本，而是**每实现一个功能就追加一个场景**。刚写完代码时记忆最清晰，选择器和预期值一定准确。

---

## 二、蓝本管理规则

1. 蓝本文件放在**当前项目根目录**的 \\\`testpilot/\\\` 子目录下
2. 页面≤3个用单个 \\\`testpilot.json\\\`；页面>3个按功能模块拆分
3. 拆分命名：\\\`testpilot/模块名.testpilot.json\\\`（英文，如 \\\`auth.testpilot.json\\\`）
4. **更新而非新建**：已存在同名蓝本直接覆盖，**禁止**创建 \\\`_v2\\\`、\\\`_new\\\`、\\\`_backup\\\` 变体
5. 每个蓝本必须包含 \\\`app_name\\\`、\\\`description\\\`、\\\`platform\\\` 字段

### platform 取值

| 值 | 适用场景 | 额外必填字段 |
|----|---------|------------|
| \\\`web\\\` | 网页应用（React/Vue/Angular/纯HTML） | \\\`base_url\\\`、\\\`start_command\\\` |
| \\\`android\\\` | Android/Flutter 应用 | \\\`app_package\\\`、\\\`app_activity\\\` |
| \\\`ios\\\` | iOS/SwiftUI 应用（仅macOS） | \\\`bundle_id\\\` |
| \\\`miniprogram\\\` | 微信小程序 | \\\`base_url\\\`（miniprogram://路径） |
| \\\`desktop\\\` | Windows桌面应用 | \\\`window_title\\\` |

---

## 三、蓝本增量维护（6种触发条件）

当项目已有蓝本文件时，以下代码变更**必须**同步更新蓝本：

| # | 触发条件 | 蓝本更新动作 |
|---|---------|------------|
| 1 | 新增/删除 UI 元素 | 添加/删除对应场景和步骤 |
| 2 | 修改元素选择器（id/class/组件名） | 更新蓝本中所有 \\\`target\\\` |
| 3 | 修改文本内容（按钮文字/提示/错误信息） | 更新 \\\`assert_text\\\` 的 \\\`expected\\\` |
| 4 | 修改业务逻辑（表单验证/跳转/计算） | 更新断言和预期结果 |
| 5 | 修复 Bug | 更新蓝本中对应断言 |
| 6 | 修改应用配置（URL/端口/路由/启动命令） | 更新 \\\`base_url\\\` / \\\`start_command\\\` 等 |

**不触发更新**：纯CSS样式调整、代码注释修改、内部重构（不影响用户可见行为）。

---

## 四、蓝本通用自检清单

生成或修改蓝本后，逐项检查：

- [ ] 所有用户可交互功能都有对应场景
- [ ] 每个场景自包含（第一步是 navigate，不依赖前一个场景的状态）
- [ ] \\\`platform\\\` 字段正确
- [ ] **已阅读对应平台规则文件**，选择器/动作/模板符合平台要求
- [ ] \\\`target\\\` 选择器在源码中确实存在（已搜索验证）
- [ ] \\\`expected\\\` 是界面上实际渲染的持久化文字（不是瞬态提示、不是变量名、不是注释）
- [ ] 异步操作后有足够的 \\\`wait\\\` 时间（已检查代码中的延迟/API调用）
- [ ] 页面跳转后有 \\\`wait\\\` + \\\`assert_text\\\` 验证到达目标页
- [ ] 每个操作后有断言验证结果（不能只操作不验证）

---

## 五、description 最佳实践

每个步骤的 \\\`description\\\` 应包含位置和预期变化：

\\\`\\\`\\\`
✅ "点击提交按钮，点击后表单数据提交到后端，页面显示'提交成功'提示"
✅ "在页面中部的用户名输入框输入admin，输入后输入框显示admin"
❌ "点击按钮"
❌ "输入用户名"
\\\`\\\`\\\`

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

请在确定 \\\`platform\\\` 后，立即打开 \\\`.testpilot/platforms/{platform}.md\\\` 阅读完整规则。
\`;
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
      outputChannel?.appendLine(\`[TestPilot AI] ⏭️ .testpilot/platforms/ 已有 \${existing.length} 个模板，跳过\`);
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
        created.push(\`.testpilot/platforms/\${fileName}\`);
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        outputChannel?.appendLine(\`[TestPilot AI] ⚠️ 创建 \${fileName} 失败: \${msg}\`);
      }
    }
  }

  if (created.length > 0) {
    outputChannel?.appendLine(
      \`[TestPilot AI] ✅ 已注入 \${created.length} 个平台模板: \${created.join(", ")}\`,
    );
  }
  return created;
}

`;

content = content.substring(0, funcStart) + newFunctions + content.substring(funcEnd);

// ============ 第二步：修改 injectRules 函数签名，增加 extensionPath 参数 ============
content = content.replace(
  'export function injectRules(\n  workspaceRoot: string,\n  outputChannel?: vscode.OutputChannel,\n  forceAll = false,\n): { created: string[]; skipped: string[] } {',
  'export function injectRules(\n  workspaceRoot: string,\n  outputChannel?: vscode.OutputChannel,\n  forceAll = false,\n  extensionPath = "",\n): { created: string[]; skipped: string[] } {'
);

// ============ 第三步：在 injectRules 函数末尾 return 前插入平台模板注入 ============
content = content.replace(
  '  return { created, skipped };\n}',
  `  // 注入平台模板文件到 .testpilot/platforms/
  if (extensionPath) {
    const platformCreated = injectPlatformTemplates(workspaceRoot, extensionPath, outputChannel);
    created.push(...platformCreated);
  }

  return { created, skipped };
}`
);

// ============ 第四步：修改 autoInjectOnActivate 签名，传入 extensionPath ============
content = content.replace(
  'export async function autoInjectOnActivate(\n  outputChannel?: vscode.OutputChannel,\n): Promise<void> {',
  'export async function autoInjectOnActivate(\n  outputChannel?: vscode.OutputChannel,\n  extensionPath = "",\n): Promise<void> {'
);

// 修改 autoInjectOnActivate 中的 injectRules 调用，传入 extensionPath
content = content.replace(
  '      const result = injectRules(root, outputChannel);',
  '      const result = injectRules(root, outputChannel, false, extensionPath);'
);

fs.writeFileSync(filePath, content, 'utf-8');

console.log('SUCCESS - rulesInjector.ts rewritten');
console.log('New file size:', fs.statSync(filePath).size);
