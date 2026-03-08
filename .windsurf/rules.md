# TestPilotAI 项目铁律

> 以下规则必须严格遵守，违反任何一条都可能导致插件崩溃或功能失效。

## 插件开发铁律

1. **永远不要删除HTML中有JS引用的DOM元素**
   - `sidebarProvider.ts`中HTML的button/input/div如果被JS的`getElementById().addEventListener()`引用，删除该元素会导致null异常，**后续所有JS代码不执行**
   - 已犯2次：btnScanBp（v10.2）、btnCheckEngine（v10.3）
   - 要隐藏元素用CSS `class="hidden"` 或 `style="display:none"`，不要删HTML
   - 修改前先全文搜索该元素ID在JS中是否有引用

2. **插件改造用最小改动策略**
   - 不要大规模重写，逐步叠加功能
   - 每次只改一个功能点，编译测试通过后再改下一个

3. **每次改完必须编译测试**
   - `npx tsc --noEmit` → 编译检查
   - `npx vsce package` → 打包
   - `windsurf --install-extension xxx.vsix --force` → 安装
   - Reload Window → 确认基本功能正常（启动引擎、扫描蓝本、项目切换）

## 小程序测试铁律

4. **绝不使用SDK导航方法**
   - `mp.navigateTo()`, `mp.navigateBack()`, `mp.reLaunch()` 全部10秒超时
   - 必须用 `evaluate(() => wx.navigateTo({url:...}))` 等原生API，仅需64ms

5. **自动化端口固定9420**
   - `cli.bat auto --project <path> --auto-port 9420`
   - 9420是automator WebSocket端口，不是HTTP服务端口

## 记忆存储铁律

6. **三层存储策略**
   - 第1层：本文件（`.windsurf/rules.md`）— 铁律，每次会话自动全量加载
   - 第2层：`开发备忘录.md` — 详细经验，AI按需读取
   - 第3层：Cascade持久记忆 — 辅助检索，不作为唯一依赖

7. **跨项目经验必须标注来源**
   - 格式：`[来源: 项目名] [仅供参考] 经验描述`
   - AI引用时说明来源和"不保证适用"
