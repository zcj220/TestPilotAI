# TestPilot AI — 进度备忘录

> 最后更新：2026-03-15（v13.0 社区经验库+商业化 开始）

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

## 📋 当前重点（v13.0 社区经验库+商业化）

### 🔴 最高优先（v13.0-A/B 在Windows上做）
- [ ] **Step 1-3: 社区数据模型+Alembic+PG驱动**
  - 新建 `src/community/models.py`（6张表）
  - 添加 alembic + psycopg2-binary 依赖
  - 生成第一个迁移脚本
- [ ] **Step 4-6: 社区服务层+API路由+测试**
  - 新建 `src/community/service.py`（20+函数）
  - 新建 `src/community/routes.py`（15个端点）
  - 新建 `tests/test_community.py`（≥30个用例）
- [ ] **Step 7-15: Web门户**
  - 新建 `web/` React项目（8个页面）
  - 重点页面：用户主页（勋章墙+贡献统计+经验列表+平台雷达图）
  - FastAPI集成 或 Nginx独立部署

### 🔴 高优先（v13.0-C/D）
- [ ] **Step 16-18: 插件社区对接**
  - 后端API已有→插件自动生效
  - 测试后分享推荐弹窗
  - 勋章展示+社区搜索
- [ ] **Step 19-24: 部署+积分**
  - Docker Compose（PG+API+Web）
  - 积分系统（余额/消费/充值）
  - 支付接口预留

### 🍎 并行（Mac上做）
- [ ] **v13.0-E: Mac/iOS平台控制器**（不在Windows上改动）

### 保留待办（优先级降低）
- [ ] 桌面测试state隔离
- [ ] 插件自动闭环开关
- [ ] OCR进一步优化
- [ ] 桌面应用打包

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
