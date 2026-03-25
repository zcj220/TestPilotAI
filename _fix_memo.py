
with open(r'd:\projects\TestPilotAI\开发备忘录.md', 'r', encoding='utf-8') as f:
    content = f.read()

idx = content.find('\n## 30. v14.2')
before = content[:idx]

new_section = """

---

## 30. v14.2 上架准备（2026-03-24）

### 30.1 今日完成内容

| 事项 | 状态 |
|------|------|
| 插件侧边栏"引擎未连接"日志去重 | ✅ 完成（`hasLoggedDisconnected` 标志位）|
| `extension/package.json` 完善（英文描述/关键词/分类/repository字段）| ✅ 完成 |
| 官网语言切换按钮移除（Navbar.jsx）| ✅ 完成 |
| 语言改为域名自动判定（LocaleContext.jsx）| ✅ 完成（修复了 `.com` 误判 Bug）|
| Publisher ID 确认为 `wenzhouxinzao` | ✅ 写入 package.json |

### 30.2 域名语言判断规则（已修复）

**正确逻辑**（以 `LocaleContext.jsx` 为准）：
- `testpilotai.pages.dev` → 英文（国际站，Cloudflare Pages 托管）
- `xinzaoai.com` / 其他所有域名 → 中文（国内站）

**修复的 Bug**：之前用 `host.endsWith('.com')` 会把 `xinzaoai.com` 也误判为英文版，现已改为只检测 `host.includes('pages.dev')`。

### 30.3 VS Code Marketplace 关键账号

| 项目 | 值 |
|------|---|
| Publisher ID | `wenzhouxinzao`（永久，账号级别，不会因插件不同而改变）|
| 注册邮箱 | `375612929@qq.com` |
| 国际官网 | https://testpilotai.pages.dev |
| 国内官网 | https://xinzaoai.com |
| PAT 令牌 | 待生成（dev.azure.com → Personal Access Tokens → Marketplace Manage 权限）|

### 30.4 待完成（明日继续）

- [ ] 生成 PAT 令牌并执行 `vsce publish` 正式上架 VS Code Marketplace
- [ ] 确认 `/privacy` 页面在 pages.dev 上是否正确展示
- [ ] 一键安装脚本（Windows .ps1 + macOS .sh）
- [ ] Open VSX Registry 上架（覆盖 Cursor/Windsurf）

### 30.5 commit 记录

| commit | 内容 |
|--------|------|
| `af24e7a` | 日志去重 + 插件重打包 v1.3.0 |
| `b408a2c` | v14.0-E 安全增强（完整实现）|
| `44b2497` | 去掉语言切换按钮 + package.json 完善 |
| `6f7451f` | 修复域名判断 Bug + Publisher ID 改为 wenzhouxinzao |
| `d313005` | 更新上架行动清单（记录账号信息）|
"""

with open(r'd:\projects\TestPilotAI\开发备忘录.md', 'w', encoding='utf-8') as f:
    f.write(before + new_section)

print('Done')
