/**
 * 小程序蓝本测试执行器 v3
 *
 * 设计原则：
 * 1. 固定端口 9420（通过 cli auto --auto-port 9420 启动）
 * 2. 自动扫描端口作为备选（如果9420连不上）
 * 3. 任意场景顺序都能跑
 * 4. 每步失败记录原因，跳过继续下一个
 * 5. 输出JSON报告给大模型
 *
 * 页面回退策略：
 * - navigateBack 在自动化模式下不可靠（执行但不生效）
 * - 解决方案：避免依赖页面跳转，用 callMethod/setData/evaluate 代替
 * - 会跳转页面的场景放最后执行
 * - 如果卡在非首页，记录原因跳过，不阻塞后续场景
 */
const automator = require('miniprogram-automator');

const DEFAULT_PORT = 9420;
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

let mp = null;
const report = { scenarios: [], startTime: 0, endTime: 0 };

// ── 连接（先试固定端口，再扫描） ──
async function connectToDevTools() {
  // 方案1: 固定端口
  const port = process.argv[2] || DEFAULT_PORT;
  try {
    console.log(`[连接] 尝试端口 ${port}...`);
    mp = await automator.connect({ wsEndpoint: `ws://localhost:${port}` });
    const p = await mp.currentPage();
    console.log(`[连接] 成功！当前页面: ${p.path}`);
    return;
  } catch (e) {
    console.log(`[连接] 端口 ${port} 失败: ${e.message}`);
  }

  // 方案2: 扫描微信开发者工具的端口
  console.log('[连接] 扫描端口...');
  const { execSync } = require('child_process');
  const ports = new Set();
  try {
    const tasks = execSync('tasklist /FI "IMAGENAME eq wechatdevtools.exe" /FO CSV /NH', { encoding: 'utf8' });
    const pids = [...tasks.matchAll(/"wechatdevtools\.exe","(\d+)"/gi)].map(m => m[1]);
    const netstat = execSync('netstat -ano', { encoding: 'utf8' });
    for (const line of netstat.split('\n')) {
      if (!line.includes('LISTENING')) continue;
      for (const pid of pids) {
        if (line.trim().endsWith(pid)) {
          const m = line.match(/127\.0\.0\.1:(\d+)/);
          if (m) ports.add(parseInt(m[1]));
        }
      }
    }
  } catch (e) {}

  for (const p of [...ports].sort((a, b) => a - b)) {
    try {
      mp = await automator.connect({ wsEndpoint: `ws://localhost:${p}` });
      const page = await mp.currentPage();
      console.log(`[连接] 端口 ${p} 成功！当前页面: ${page.path}`);
      return;
    } catch (e) {}
  }
  throw new Error('无法连接微信开发者工具，请用 cli auto --auto-port 9420 启动');
}

// ── 确保在首页 ──
async function ensureHomePage() {
  let page = await mp.currentPage();
  if (page.path === 'pages/index/index') return page;

  // 尝试 navigateBack（最多2次，每次等3秒）
  for (let i = 0; i < 2; i++) {
    try {
      await mp.navigateBack();
      await sleep(3000);
      page = await mp.currentPage();
      if (page.path === 'pages/index/index') return page;
    } catch (e) { break; }
  }
  throw new Error(`无法回到首页，当前在 ${page.path}`);
}

// ── 重置购物车 ──
async function resetState() {
  await mp.evaluate(() => { getApp().globalData.cart = []; });
  const page = await mp.currentPage();
  await page.setData({ cartCount: 0, cartTotal: '0', message: '', msgClass: '' });
  await sleep(200);
}

// ── 安全执行场景 ──
async function runScenario(name, desc, fn) {
  console.log(`\n${'─'.repeat(50)}`);
  console.log(`场景: ${name}`);
  console.log(`描述: ${desc}`);
  console.log('─'.repeat(50));

  const sr = { name, desc, status: 'unknown', steps: [], bug: null, error: null };
  try {
    await ensureHomePage();
    await resetState();
    console.log('  [准备] 首页+状态已重置');
    const result = await fn(sr);
    sr.status = result.bug ? 'bug_found' : 'passed';
    sr.bug = result.bug;
  } catch (e) {
    console.log(`  ❌ 失败: ${e.message}`);
    sr.status = 'skipped';
    sr.error = e.message;
  }
  report.scenarios.push(sr);
  return sr;
}

// ══════ Bug1: 机械键盘价格不一致 ══════
async function bug1(sr) {
  const page = await mp.currentPage();
  const priceEl = await page.$('#price-2');
  const price = priceEl ? await priceEl.text() : '';
  sr.steps.push({ action: '读取键盘价格', result: price });
  console.log(`  [1] 键盘页面价格: ${price}`);

  const btns = await page.$$('.btn-primary');
  if (btns[1]) { await btns[1].tap(); await sleep(500); }
  sr.steps.push({ action: '点击键盘加入购物车', result: 'OK' });
  console.log('  [2] 点击键盘"加入购物车"');

  const totalEl = await page.$('#cartTotal');
  const total = totalEl ? await totalEl.text() : '';
  sr.steps.push({ action: '读取总计', result: total });
  console.log(`  [3] 购物车总计: ${total}`);

  if (price.includes('199') && !total.includes('199')) {
    const msg = `页面${price}→购物车${total}，价格不一致`;
    console.log(`  🐛 ${msg}`);
    return { bug: { type: '数据不一致', message: msg, severity: 'high' } };
  }
  return { bug: null };
}

// ══════ Bug2: 浮点精度 ══════
async function bug2(sr) {
  const page = await mp.currentPage();
  const btns = await page.$$('.btn-primary');
  if (btns[0]) { await btns[0].tap(); await sleep(300); }
  console.log('  [1] 加入耳机(299)');
  if (btns[2]) { await btns[2].tap(); await sleep(300); }
  console.log('  [2] 加入扩展坞(159)');

  const totalEl = await page.$('#cartTotal');
  const total = totalEl ? await totalEl.text() : '';
  sr.steps.push({ action: '读取总计', result: total });
  console.log(`  [3] 总计: ${total}`);

  if (!total.includes('458.00')) {
    const msg = `总计=${total}，期望458.00(299+159)，计算误差`;
    console.log(`  🐛 ${msg}`);
    return { bug: { type: '计算错误', message: msg, severity: 'medium' } };
  }
  return { bug: null };
}

// ══════ Bug4: 大金额结算报错（在首页用 callMethod） ══════
async function bug4(sr) {
  const page = await mp.currentPage();
  const btns = await page.$$('.btn-primary');
  for (let i = 0; i < 3 && i < btns.length - 1; i++) {
    await btns[i].tap(); await sleep(300);
  }
  console.log('  [1] 加入全部3个商品');

  const totalEl = await page.$('#cartTotal');
  const total = totalEl ? await totalEl.text() : '';
  sr.steps.push({ action: '读取总计', result: total });
  console.log(`  [2] 总计: ${total}`);

  await page.callMethod('checkout');
  await sleep(300);
  console.log('  [3] 调用checkout()');

  const msgEl = await page.$('#message');
  const msg = msgEl ? await msgEl.text() : '';
  sr.steps.push({ action: '结算消息', result: msg });
  console.log(`  [4] 消息: ${msg}`);

  if (msg.includes('错误') || msg.includes('Error') || msg.includes('500')) {
    const detail = `总价${total}→"${msg}"，大金额应成功但报错`;
    console.log(`  🐛 ${detail}`);
    return { bug: { type: '业务逻辑错误', message: detail, severity: 'high' } };
  }
  return { bug: null };
}

// ══════ Bug3: 空购物车跳转（会跳页面，放最后） ══════
async function bug3(sr) {
  let page = await mp.currentPage();
  console.log(`  [1] 当前: ${page.path}`);

  const btns = await page.$$('.btn-primary');
  const lastBtn = btns[btns.length - 1];
  if (lastBtn) { await lastBtn.tap(); await sleep(2000); }
  console.log('  [2] 点击"查看购物车"');

  page = await mp.currentPage();
  sr.steps.push({ action: '跳转后页面', result: page.path });
  console.log(`  [3] 跳转到: ${page.path}`);

  if (page.path.includes('cart/cart')) {
    const msg = `空购物车直接跳转${page.path}，应提示而非跳转`;
    console.log(`  🐛 ${msg}`);
    return { bug: { type: '缺少输入验证', message: msg, severity: 'medium' } };
  }
  return { bug: null };
}

// ── 主流程 ──
async function main() {
  console.log('============================================================');
  console.log('  BuggyMini 小程序蓝本测试 v3');
  console.log('  固定端口9420 | 自动回退 | 任意顺序');
  console.log('============================================================');

  report.startTime = Date.now();
  await connectToDevTools();

  // 执行顺序：Bug1→Bug2→Bug4→Bug3
  // Bug3会跳转页面，放最后。但即使Bug3在前面，Bug4也会尝试回退
  await runScenario('Bug1-机械键盘价格不一致', '页面显示199但加购变599', bug1);
  await runScenario('Bug2-浮点精度', '耳机+扩展坞=458应为458.00', bug2);
  await runScenario('Bug4-大金额结算报错', '总价>500结算应成功但报500错误', bug4);
  await runScenario('Bug3-空购物车跳转', '空购物车点查看应提示而非跳转', bug3);

  report.endTime = Date.now();
  await mp.disconnect();

  // 汇总
  const elapsed = ((report.endTime - report.startTime) / 1000).toFixed(1);
  const bugs = report.scenarios.filter(s => s.status === 'bug_found');
  const passed = report.scenarios.filter(s => s.status === 'passed');
  const skipped = report.scenarios.filter(s => s.status === 'skipped');

  console.log('\n============================================================');
  console.log('  测试报告');
  console.log('============================================================');
  for (const s of report.scenarios) {
    const icon = s.status === 'bug_found' ? '🐛' : s.status === 'passed' ? '✅' : '⏭️';
    const msg = s.bug ? s.bug.message : s.error ? `跳过: ${s.error}` : '通过';
    console.log(`  ${icon} ${s.name}: ${msg}`);
  }
  console.log(`\n  🐛 ${bugs.length} | ✅ ${passed.length} | ⏭️ ${skipped.length} | ${elapsed}秒`);

  // JSON报告（给大模型用）
  console.log('\n[JSON报告]');
  console.log(JSON.stringify({
    summary: { total: report.scenarios.length, bugs: bugs.length, passed: passed.length, skipped: skipped.length, seconds: parseFloat(elapsed) },
    bugs: bugs.map(s => ({ scenario: s.name, type: s.bug.type, message: s.bug.message, severity: s.bug.severity, steps: s.steps })),
    skipped: skipped.map(s => ({ scenario: s.name, reason: s.error })),
  }, null, 2));

  if (bugs.length === 4) console.log('\n🎉 4/4 Bug全部发现！');
}

main().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
