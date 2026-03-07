/**
 * 导航研究 - 自动化测试脚本
 *
 * 系统测试各种页面跳转和回退方式，记录成功率。
 * 用微信开发者工具打开 nav-research 文件夹，然后：
 *   cli auto --project "路径/nav-research" --auto-port 9420
 *   node test_nav.js
 *
 * 每个测试独立，失败不影响后续。
 */
const automator = require('miniprogram-automator');
const WS_PORT = process.argv[2] || 9420;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

let mp = null;
const log = [];

function record(test, success, detail, ms) {
  const icon = success ? '✅' : '❌';
  console.log(`  ${icon} ${test}: ${detail} (${ms}ms)`);
  log.push({ test, success, detail, ms });
}

async function getPage() {
  const p = await mp.currentPage();
  return p.path;
}

// ═══════ 测试1: navigateBack 基本测试 ═══════
// home → sub → navigateBack → 应该回home
async function test_navigateBack_basic() {
  console.log('\n── 测试1: navigateBack 基本 ──');

  // 确保在首页
  let path = await getPage();
  console.log(`  起始: ${path}`);

  // 跳到子页
  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);
  path = await getPage();
  console.log(`  跳转后: ${path}`);

  // navigateBack
  const t0 = Date.now();
  await mp.navigateBack();
  const ms = Date.now() - t0;
  await sleep(1000);

  path = await getPage();
  console.log(`  返回后: ${path} (耗时${ms}ms)`);
  record('navigateBack基本', path === 'pages/home/home', `回到${path}`, ms);
}

// ═══════ 测试2: navigateBack 连续跳2层再回 ═══════
// home → sub → sub → navigateBack → 应该回第1个sub
async function test_navigateBack_2layers() {
  console.log('\n── 测试2: navigateBack 2层 ──');

  let path = await getPage();
  console.log(`  起始: ${path}`);

  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);
  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);

  // 获取页面栈
  const stack = await mp.evaluate(() => getCurrentPages().map(p => p.route));
  console.log(`  页面栈: ${JSON.stringify(stack)}`);

  const t0 = Date.now();
  await mp.navigateBack();
  const ms = Date.now() - t0;
  await sleep(1000);

  path = await getPage();
  console.log(`  返回后: ${path} (${ms}ms)`);
  record('navigateBack_2层', path === 'pages/sub/sub', `回到${path}`, ms);
}

// ═══════ 测试3: navigateBack delta=10 回到底 ═══════
async function test_navigateBack_delta10() {
  console.log('\n── 测试3: navigateBack delta=10 ──');

  let path = await getPage();
  console.log(`  起始: ${path}`);

  // 跳2层
  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);
  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);

  const t0 = Date.now();
  try {
    await mp.evaluate(() => { wx.navigateBack({ delta: 10 }); });
    await sleep(2000);
  } catch(e) {
    console.log(`  evaluate报错: ${e.message}`);
  }
  const ms = Date.now() - t0;

  path = await getPage();
  console.log(`  返回后: ${path} (${ms}ms)`);
  record('navigateBack_delta10', path === 'pages/home/home', `回到${path}`, ms);
}

// ═══════ 测试4: reLaunch ═══════
async function test_reLaunch() {
  console.log('\n── 测试4: reLaunch ──');

  // 先跳到子页
  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);
  let path = await getPage();
  console.log(`  跳转后: ${path}`);

  const t0 = Date.now();
  try {
    await mp.evaluate(() => { wx.reLaunch({ url: '/pages/home/home' }); });
    await sleep(3000);
  } catch(e) {
    console.log(`  evaluate报错: ${e.message}`);
  }
  const ms = Date.now() - t0;

  path = await getPage();
  console.log(`  reLaunch后: ${path} (${ms}ms)`);
  record('reLaunch', path === 'pages/home/home', `回到${path}`, ms);
}

// ═══════ 测试5: redirectTo ═══════
async function test_redirectTo() {
  console.log('\n── 测试5: redirectTo ──');

  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);
  let path = await getPage();
  console.log(`  跳转后: ${path}`);

  const t0 = Date.now();
  try {
    await mp.evaluate(() => { wx.redirectTo({ url: '/pages/home/home' }); });
    await sleep(3000);
  } catch(e) {
    console.log(`  evaluate报错: ${e.message}`);
  }
  const ms = Date.now() - t0;

  path = await getPage();
  console.log(`  redirectTo后: ${path} (${ms}ms)`);
  record('redirectTo', path === 'pages/home/home', `回到${path}`, ms);
}

// ═══════ 测试6: mp.navigateBack (SDK方法) ═══════
async function test_sdk_navigateBack() {
  console.log('\n── 测试6: SDK mp.navigateBack() ──');

  await mp.navigateTo('/pages/sub/sub');
  await sleep(1000);
  let path = await getPage();
  console.log(`  跳转后: ${path}`);

  const t0 = Date.now();
  try {
    await mp.navigateBack();
  } catch(e) {
    console.log(`  SDK报错: ${e.message}`);
  }
  const ms = Date.now() - t0;
  await sleep(1000);

  path = await getPage();
  console.log(`  SDK返回后: ${path} (${ms}ms)`);
  record('SDK_navigateBack', path === 'pages/home/home', `回到${path}`, ms);
}

// ═══════ 测试7: 连续跳转+返回 重复10次 ═══════
async function test_repeat() {
  console.log('\n── 测试7: 重复跳转返回 10次 ──');

  let successCount = 0;
  for (let i = 0; i < 10; i++) {
    await mp.navigateTo('/pages/sub/sub');
    await sleep(500);

    await mp.navigateBack();
    await sleep(500);

    const path = await getPage();
    if (path === 'pages/home/home') successCount++;
    else console.log(`  第${i+1}次失败: 在${path}`);
  }

  console.log(`  成功: ${successCount}/10`);
  record('重复跳转返回x10', successCount === 10, `${successCount}/10成功`, 0);
}

// ═══════ 测试8: 跳转后等不同时间再返回 ═══════
async function test_wait_times() {
  console.log('\n── 测试8: 不同等待时间后返回 ──');

  const waits = [100, 500, 1000, 2000, 3000, 5000];
  for (const w of waits) {
    // 先确保在首页
    let path = await getPage();
    if (path !== 'pages/home/home') {
      try { await mp.navigateBack(); await sleep(1000); } catch(e) {}
    }

    await mp.navigateTo('/pages/sub/sub');
    await sleep(w);

    const t0 = Date.now();
    await mp.navigateBack();
    const ms = Date.now() - t0;
    await sleep(1000);

    path = await getPage();
    const ok = path === 'pages/home/home';
    console.log(`  等${w}ms: ${ok ? '✅' : '❌'} 回到${path} (返回耗时${ms}ms)`);
    record(`等${w}ms后返回`, ok, `回到${path}`, ms);
  }
}

// ── 主流程 ──
async function main() {
  console.log('════════════════════════════════════════════');
  console.log('  导航研究 - 自动化测试');
  console.log('  系统测试各种页面跳转和回退方式');
  console.log('════════════════════════════════════════════');

  mp = await automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` });
  const path = await getPage();
  console.log(`[连接成功] 当前: ${path}`);

  await test_navigateBack_basic();
  await test_navigateBack_2layers();
  await test_navigateBack_delta10();
  await test_reLaunch();
  await test_redirectTo();
  await test_sdk_navigateBack();
  await test_repeat();
  await test_wait_times();

  await mp.disconnect();

  // 汇总
  const total = log.length;
  const ok = log.filter(l => l.success).length;
  const fail = log.filter(l => !l.success).length;

  console.log('\n════════════════════════════════════════════');
  console.log('  汇总报告');
  console.log('════════════════════════════════════════════');
  for (const l of log) {
    console.log(`  ${l.success ? '✅' : '❌'} ${l.test}: ${l.detail} (${l.ms}ms)`);
  }
  console.log(`\n  ✅ ${ok}/${total} 成功 | ❌ ${fail}/${total} 失败`);

  // JSON
  console.log('\n[JSON]');
  console.log(JSON.stringify({ total, ok, fail, details: log }, null, 2));
}

main().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
