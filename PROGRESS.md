# TestPilot AI — 进度备忘录

> 最后更新：2026-03-13

---

## ✅ 已完成（本周）

### 桌面测试优化（desktop_blueprint_runner.py）
1. **步骤28修复** — 场景切换后加1.5s等待，防止Logout后截图时机太快，AI误把登录后状态当未登录
2. **截图hash跨场景坐标缓存** — 同一界面不重复发图给AI，7次→3次AI调用
   - `_page_hash` + `_global_coord_cache`：界面MD5相同直接复用坐标
   - `_invalidate_coord_cache()`：navigate动作主动清缓存
3. **OCR缓存复用** — `assert_text`连续复用截图hash，不重复发OCR请求
   - click/fill后清空缓存（界面可能变化）
   - 相同界面连续多个assert_text只发一次AI
4. **坐标定位reasoning_effort** — 保持`low`（精度优先）；OCR用`minimal`（速度优先）

### 经验库 + AI模型评分（anonymizer.py）
5. **模型等级评分** — `calc_share_score`加入AI模型等级权重
   - `high`（claude-3.5/gpt-4o等）：多次尝试=真难题，加分
   - `low`（免费/mini/本地等）：多次尝试可能是模型能力不足，少加分

### VS Code插件修复（sidebarProvider.ts）
6. **Tab切换null安全** — switchTab对null元素filter(Boolean)防崩溃
7. **CSP违规修复** — 移除内联onclick，改用事件委托（data-action）
8. **社区按钮null检查** — btnSearchCommunity/btnRefreshCommunity/btnShareExperience加if检查

---

## 📊 当前测试成绩

| 平台 | 通过率 | 备注 |
|------|--------|------|
| 桌面（NoteApp tkinter） | 32/34 = **94%** | 步骤28是NoteApp预埋Bug（预期失败），步骤7是state问题 |
| Web（shop-demo） | 100/102 = **98%** | 2个真实Bug |
| Android（NoteApp） | 38/40 = **95%** | 2个APP本身Bug |

---

## 📋 下次继续（待办）

### 高优先
- [ ] **Phase 2: AI自动评估分享价值 + 弹窗推荐**
  - 测试完成后，如果发现Bug+Fix记录，AI自动算分享价值（已有calc_share_score）
  - 超过阈值（如≥5分）弹窗询问用户是否分享到经验库
  - 文件：`src/community/anonymizer.py` + 插件弹窗逻辑

- [ ] **桌面测试state隔离**
  - 每次测试前通过`app_exe`参数重启被测应用，确保状态干净
  - MCP工具`run_desktop_test`需要支持`app_exe`参数

### 中优先
- [ ] **插件自动闭环开关**
  - 测试→发现Bug→AI自动修复→重测→直到Bug=0
  - 需要`auto_repair`开关 + 循环测试逻辑

- [ ] **OCR进一步优化（可选）**
  - 坐标分析时同时顺带返回页面文字（一次API调用返回坐标+文字）
  - 需要改prompt格式，解析逻辑要处理混合输出

### 低优先
- [ ] **桌面应用打包** — `cargo tauri build`（Rust已配置在D:\DevEnv）
- [ ] **Web测试截图优化** — 类似桌面hash缓存机制

---

## 🔑 关键路径

```
项目根目录:    D:\Projects\TestPilotAI
GitHub:        https://github.com/zcj220/TestPilotAI
引擎启动:      poetry run python main.py  （在项目根目录）
插件打包:      cd extension && npm run compile && vsce package
NoteApp测试:   desktop-demo/testpilot.json  |  app: notepad_app.py
```

---

## ⚠️ 已知坑

1. tkinter对UI Automation几乎不暴露控件信息，坐标定位全靠AI视觉（慢）
2. `minimal`推理精度不足（坐标定位用`low`才稳定）
3. MCP工具`run_desktop_test`没有`app_exe`参数，需要手动重启被测应用保持状态干净
4. `reasoning_effort=low`的Claude会产生扩展思考token（~1000 tokens），每次约10-36秒——这是Claude模型特性，不是bug
