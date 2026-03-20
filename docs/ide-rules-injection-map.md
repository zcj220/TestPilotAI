# IDE 规则文件注入映射表

> 插件激活时，根据此映射表在用户项目中创建规则文件。
> 所有文件内容相同（来自 `docs/ide-rules-template.md`），只是路径不同。
> 最后更新：2026-03-20

---

## 注入策略

### 注入时机
1. **插件首次激活**：检测当前workspace，如果没有任何蓝本规则文件，自动创建
2. **用户手动触发**：插件命令 `TestPilot: 注入AI规则到项目`
3. **不重复注入**：如果目标文件已存在，跳过（不覆盖用户自定义内容）

### 注入哪些文件

插件应该创建**所有**以下文件，确保无论用户用什么IDE，编程AI都能读到规则：

| 优先级 | 文件路径 | 覆盖IDE | 说明 |
|:---:|---------|---------|------|
| 🔴 必须 | `AGENTS.md` | Cursor、Cline、Augment、Kilo Code | **跨工具通用标准**，覆盖面最广 |
| 🔴 必须 | `.github/copilot-instructions.md` | VS Code (Copilot)、GitHub Copilot | GitHub官方标准，VS Code用户最多 |
| 🔴 必须 | `.cursor/rules/testpilot.md` | Cursor | Cursor专用目录 |
| 🔴 必须 | `.windsurf/rules/testpilot.md` | Windsurf | Windsurf专用目录（不影响已有rules.md） |
| 🟡 推荐 | `.trae/rules/testpilot.md` | Trae（字节跳动） | Trae v1.3.0+ 支持 |
| 🟡 推荐 | `.clinerules/testpilot.md` | Cline（VS Code插件） | Cline专用目录 |
| 🟡 推荐 | `.aiassistant/rules/testpilot.md` | JetBrains AI Assistant | IntelliJ/WebStorm/PyCharm等 |
| 🟡 推荐 | `.augment/rules/testpilot.md` | Augment Code | Augment专用目录 |
| 🟡 推荐 | `CLAUDE.md` | Claude Code（Anthropic CLI） | Claude Code专用 |
| 🟢 可选 | `.cursorrules` | Cursor（旧版兼容） | 单文件格式，新版Cursor仍支持 |
| 🟢 可选 | `.windsurfrules` | Windsurf（Cline也读） | 单文件格式 |
| ❌ 暂无 | — | Xcode Coding Intelligence | Apple暂未支持项目级规则文件 |
| ❌ 暂无 | — | Google Cloud Code / Gemini | Google暂未支持项目级规则文件 |
| ❌ 暂无 | — | Qodo Gen | Qodo暂未支持项目级规则文件（仅PR-Agent配置） |

### 实际创建文件数量

**精简方案（推荐）**：只创建覆盖面最广的文件，避免项目目录过于杂乱：

```
项目根目录/
├── AGENTS.md                              ← 跨工具通用（Cursor/Cline/Augment/Kilo）
├── CLAUDE.md                              ← Claude Code
├── .github/
│   └── copilot-instructions.md            ← VS Code Copilot
├── .cursor/
│   └── rules/
│       └── testpilot.md                   ← Cursor
├── .windsurf/
│   └── rules/
│       └── testpilot.md                   ← Windsurf（不覆盖已有rules.md）
├── .trae/
│   └── rules/
│       └── testpilot.md                   ← Trae
├── .clinerules/
│   └── testpilot.md                       ← Cline
└── .aiassistant/
    └── rules/
        └── testpilot.md                   ← JetBrains
```

### .gitignore 处理

这些规则文件**应该提交到Git**（团队成员也需要），所以**不要**加到.gitignore。

---

## 插件实现伪代码

```typescript
// extension/src/rulesInjector.ts

const RULES_FILES = [
  'AGENTS.md',
  'CLAUDE.md',
  '.github/copilot-instructions.md',
  '.cursor/rules/testpilot.md',
  '.windsurf/rules/testpilot.md',
  '.trae/rules/testpilot.md',
  '.clinerules/testpilot.md',
  '.aiassistant/rules/testpilot.md',
  '.augment/rules/testpilot.md',
];

async function injectRules(workspaceRoot: string) {
  const templateContent = getTemplateContent(); // 读取规则模板
  
  for (const filePath of RULES_FILES) {
    const fullPath = path.join(workspaceRoot, filePath);
    
    // 已存在则跳过（不覆盖用户自定义）
    if (fs.existsSync(fullPath)) continue;
    
    // 创建目录
    fs.mkdirSync(path.dirname(fullPath), { recursive: true });
    
    // 写入规则文件
    fs.writeFileSync(fullPath, templateContent, 'utf-8');
  }
}
```

---

## 维护说明

- 新IDE出现时，在此映射表中添加对应路径
- 规则模板内容统一维护在 `docs/ide-rules-template.md`
- 所有IDE的规则文件内容完全相同，只是存放路径不同
