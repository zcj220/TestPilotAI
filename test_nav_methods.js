/**
 * 导航方法系统性测试
 * 
 * 在 FreshMart 项目上直接测试，找出从任意页面回首页的可靠方法。
 * 先 cli auto 重启，然后运行: node test_nav_methods.js
 */
const automator = require('miniprogram-automator');
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  const mp = await automator.connect({ wsEndpoint: 'ws://localhost:9420' });
  let p = await mp.currentPage();
  console.log(`[连接] 当前: ${p.path}\n`);

  // ── 测试1: navigateTo + navigateBack ──
  console.log('=== 测试1: navigateTo→cart→navigateBack ===');
  await mp.navigateTo('/pages/cart/cart');
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  跳后: ${p.path}`);
  let t = Date.now();
  try { await mp.navigateBack(); } catch(e) { console.log(`  navigateBack错误: ${e.message}`); }
  console.log(`  navigateBack耗时: ${Date.now()-t}ms`);
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  返回后: ${p.path} ${p.path==='pages/index/index'?'✅':'❌'}\n`);

  // ── 测试2: navigateTo + reLaunch ──
  console.log('=== 测试2: navigateTo→checkout→reLaunch ===');
  await mp.navigateTo('/pages/checkout/checkout');
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  跳后: ${p.path}`);
  t = Date.now();
  try { await mp.reLaunch('/pages/index/index'); } catch(e) { console.log(`  reLaunch错误: ${e.message}`); }
  console.log(`  reLaunch耗时: ${Date.now()-t}ms`);
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  reLaunch后: ${p.path} ${p.path==='pages/index/index'?'✅':'❌'}\n`);

  // ── 测试3: navigateTo + redirectTo ──
  console.log('=== 测试3: navigateTo→cart→redirectTo ===');
  await mp.navigateTo('/pages/cart/cart');
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  跳后: ${p.path}`);
  t = Date.now();
  try { await mp.redirectTo('/pages/index/index'); } catch(e) { console.log(`  redirectTo错误: ${e.message}`); }
  console.log(`  redirectTo耗时: ${Date.now()-t}ms`);
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  redirectTo后: ${p.path} ${p.path==='pages/index/index'?'✅':'❌'}\n`);

  // ── 测试4: 2层跳转 + navigateBack ──
  console.log('=== 测试4: →cart→checkout→navigateBack×2 ===');
  await mp.navigateTo('/pages/cart/cart');
  await sleep(1000);
  await mp.navigateTo('/pages/checkout/checkout');
  await sleep(1000);
  p = await mp.currentPage();
  console.log(`  2层后: ${p.path}`);
  t = Date.now();
  try { await mp.navigateBack(); } catch(e) { console.log(`  back1错误: ${e.message}`); }
  await sleep(1000);
  p = await mp.currentPage();
  console.log(`  back1后: ${p.path} (${Date.now()-t}ms)`);
  t = Date.now();
  try { await mp.navigateBack(); } catch(e) { console.log(`  back2错误: ${e.message}`); }
  await sleep(1000);
  p = await mp.currentPage();
  console.log(`  back2后: ${p.path} ${p.path==='pages/index/index'?'✅':'❌'}\n`);

  // ── 测试5: evaluate wx.reLaunch ──
  console.log('=== 测试5: →cart→evaluate(wx.reLaunch) ===');
  await mp.navigateTo('/pages/cart/cart');
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  跳后: ${p.path}`);
  t = Date.now();
  try {
    await mp.evaluate(() => {
      return new Promise((resolve) => {
        wx.reLaunch({ url: '/pages/index/index', success: resolve, fail: resolve });
      });
    });
  } catch(e) { console.log(`  evaluate错误: ${e.message}`); }
  console.log(`  evaluate耗时: ${Date.now()-t}ms`);
  await sleep(2000);
  p = await mp.currentPage();
  console.log(`  evaluate后: ${p.path} ${p.path==='pages/index/index'?'✅':'❌'}\n`);

  // ── 测试6: evaluate wx.navigateBack({delta:99}) ──
  console.log('=== 测试6: →cart→evaluate(wx.navigateBack delta:99) ===');
  await mp.navigateTo('/pages/cart/cart');
  await sleep(1500);
  p = await mp.currentPage();
  console.log(`  跳后: ${p.path}`);
  t = Date.now();
  try {
    await mp.evaluate(() => {
      return new Promise((resolve) => {
        wx.navigateBack({ delta: 99, success: resolve, fail: resolve });
      });
    });
  } catch(e) { console.log(`  evaluate错误: ${e.message}`); }
  console.log(`  evaluate耗时: ${Date.now()-t}ms`);
  await sleep(2000);
  p = await mp.currentPage();
  console.log(`  evaluate后: ${p.path} ${p.path==='pages/index/index'?'✅':'❌'}\n`);

  // ── 测试7: 连续5次 navigateTo→navigateBack ──
  console.log('=== 测试7: 连续5次跳转回退 ===');
  let ok = 0;
  for (let i = 0; i < 5; i++) {
    await mp.navigateTo('/pages/cart/cart');
    await sleep(800);
    try { await mp.navigateBack(); } catch(e) {}
    await sleep(800);
    p = await mp.currentPage();
    const success = p.path === 'pages/index/index';
    if (success) ok++;
    else console.log(`  第${i+1}次失败: 在${p.path}`);
  }
  console.log(`  成功率: ${ok}/5 ${ok===5?'✅':'❌'}\n`);

  // ── 测试8: 页面栈检查 ──
  console.log('=== 测试8: 检查页面栈 ===');
  const stack = await mp.evaluate(() => getCurrentPages().map(p => p.route));
  console.log(`  页面栈: ${JSON.stringify(stack)}`);
  console.log(`  栈深度: ${stack.length}\n`);

  await mp.disconnect();
  console.log('[完成]');
}

main().catch(e => console.log('Fatal:', e.message));
