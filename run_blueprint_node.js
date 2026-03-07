/**
 * 小程序蓝本测试 - 单连接版
 * 一个连接跑完所有场景，用 setData+evaluate 重置状态，避免页面跳转超时。
 * Bug3 和 Bug4 需要跳转到 cart 页面，放最后执行。
 */
const automator = require('miniprogram-automator');
const WS_PORT = 60427;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  console.log('============================================================');
  console.log('  BuggyMini 小程序蓝本测试');
  console.log('  预埋4个Bug，验证自动化测试能否发现');
  console.log('============================================================');

  const start = Date.now();
  const mp = await automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` });
  let page = await mp.currentPage();
  console.log(`\n[连接成功] 当前页面: ${page.path}`);

  const results = [];

  // ── 重置函数 ──
  async function resetCart() {
    await mp.evaluate(() => { getApp().globalData.cart = []; });
    page = await mp.currentPage();
    await page.setData({ cartCount: 0, cartTotal: '0', message: '', msgClass: '' });
    await sleep(200);
  }

  // ══════════════════════════════════════════════
  // Bug1: 机械键盘价格不一致
  // ══════════════════════════════════════════════
  console.log('\n──────────────────────────────────────────────────');
  console.log('场景: Bug1-机械键盘价格不一致');
  console.log('描述: 页面显示199但加入购物车变599');
  console.log('──────────────────────────────────────────────────');
  try {
    await resetCart();
    page = await mp.currentPage();

    const priceEl = await page.$('#price-2');
    const price = priceEl ? await priceEl.text() : '未找到';
    console.log(`  [1] 机械键盘页面价格: ${price}`);

    // 获取所有按钮，点击第2个（键盘）
    const btns1 = await page.$$('.btn-primary');
    if (btns1[1]) { await btns1[1].tap(); await sleep(500); }
    console.log('  [2] 点击机械键盘"加入购物车"');

    const totalEl = await page.$('#cartTotal');
    const total = totalEl ? await totalEl.text() : '';
    console.log(`  [3] 购物车总计: ${total}`);

    if (price.includes('199') && !total.includes('199')) {
      console.log(`  🐛 页面显示${price}，购物车变成${total}，价格不一致！`);
      results.push({ name: 'Bug1', bug: true, msg: `页面${price}→购物车${total}` });
    } else {
      console.log(`  ✅ 页面=${price}，购物车=${total}`);
      results.push({ name: 'Bug1', bug: false, msg: `页面=${price}，购物车=${total}` });
    }
  } catch (e) {
    console.log(`  ⚠️ 异常: ${e.message}`);
    results.push({ name: 'Bug1', bug: false, msg: `异常: ${e.message}` });
  }

  // ══════════════════════════════════════════════
  // Bug2: 浮点精度
  // ══════════════════════════════════════════════
  console.log('\n──────────────────────────────────────────────────');
  console.log('场景: Bug2-浮点精度');
  console.log('描述: 耳机(299)+扩展坞(159)=458，总价应为458.00');
  console.log('──────────────────────────────────────────────────');
  try {
    await resetCart();
    page = await mp.currentPage();
    const btns2 = await page.$$('.btn-primary');

    // 点击耳机(btns[0])
    if (btns2[0]) { await btns2[0].tap(); await sleep(300); }
    console.log('  [1] 加入无线耳机(299)');

    // 点击扩展坞(btns[2])
    if (btns2[2]) { await btns2[2].tap(); await sleep(300); }
    console.log('  [2] 加入扩展坞(159)');

    const totalEl2 = await page.$('#cartTotal');
    const total2 = totalEl2 ? await totalEl2.text() : '';
    console.log(`  [3] 购物车总计: ${total2}`);

    if (total2.includes('458.00')) {
      console.log(`  ✅ 总计=${total2}，正常`);
      results.push({ name: 'Bug2', bug: false, msg: `总计=${total2}` });
    } else {
      console.log(`  🐛 总计=${total2}，期望含"458.00"，出现计算误差！`);
      results.push({ name: 'Bug2', bug: true, msg: `总计=${total2}，应为458.00` });
    }
  } catch (e) {
    console.log(`  ⚠️ 异常: ${e.message}`);
    results.push({ name: 'Bug2', bug: false, msg: `异常: ${e.message}` });
  }

  // ══════════════════════════════════════════════
  // Bug4: 大金额结算报错（在首页直接调用 checkout）
  // ══════════════════════════════════════════════
  console.log('\n──────────────────────────────────────────────────');
  console.log('场景: Bug4-大金额结算报错');
  console.log('描述: 全部商品(>500)结算应成功但报500错误');
  console.log('──────────────────────────────────────────────────');
  try {
    await resetCart();
    page = await mp.currentPage();
    const btns4 = await page.$$('.btn-primary');

    // 添加3个商品
    for (let i = 0; i < 3 && i < btns4.length - 1; i++) {
      await btns4[i].tap();
      await sleep(300);
    }
    console.log('  [1] 加入全部3个商品(耳机+键盘+扩展坞)');

    const totalEl4 = await page.$('#cartTotal');
    const total4 = totalEl4 ? await totalEl4.text() : '';
    console.log(`  [2] 购物车总计: ${total4}`);

    // 直接在首页调用 checkout 方法（index.js 有500限制）
    await page.callMethod('checkout');
    await sleep(300);
    console.log('  [3] 调用 checkout()');

    const msgEl4 = await page.$('#message');
    const msg4 = msgEl4 ? await msgEl4.text() : '';
    console.log(`  [4] 结算消息: ${msg4}`);

    if (msg4.includes('错误') || msg4.includes('Error') || msg4.includes('500')) {
      console.log(`  🐛 总价=${total4}，消息="${msg4}"，大金额应成功但报错！`);
      results.push({ name: 'Bug4', bug: true, msg: `${total4}→"${msg4}"` });
    } else if (msg4.includes('成功')) {
      console.log(`  ✅ 结算成功: ${msg4}`);
      results.push({ name: 'Bug4', bug: false, msg: `结算成功` });
    } else {
      console.log(`  ⚠️ 意外结果: ${msg4}`);
      results.push({ name: 'Bug4', bug: false, msg: `意外: "${msg4}"` });
    }
  } catch (e) {
    console.log(`  ⚠️ 异常: ${e.message}`);
    results.push({ name: 'Bug4', bug: false, msg: `异常: ${e.message}` });
  }

  // ══════════════════════════════════════════════
  // Bug3: 空购物车跳转（放最后，因为会跳页面）
  // ══════════════════════════════════════════════
  console.log('\n──────────────────────────────────────────────────');
  console.log('场景: Bug3-空购物车跳转');
  console.log('描述: 空购物车点查看应提示而非直接跳转');
  console.log('──────────────────────────────────────────────────');
  try {
    await resetCart();
    page = await mp.currentPage();
    console.log(`  [1] 当前页面: ${page.path}`);

    // 点击最后一个 btn-primary（"查看购物车"）
    const btns3 = await page.$$('.btn-primary');
    const lastBtn = btns3[btns3.length - 1];
    if (lastBtn) {
      await lastBtn.tap();
      await sleep(1500);
      console.log('  [2] 点击"查看购物车"');
    }

    page = await mp.currentPage();
    console.log(`  [3] 跳转后页面: ${page.path}`);

    if (page.path.includes('cart/cart')) {
      console.log(`  🐛 空购物车直接跳转到${page.path}，应提示而非跳转！`);
      results.push({ name: 'Bug3', bug: true, msg: `空购物车跳转到${page.path}` });
    } else {
      console.log(`  ✅ 当前页面=${page.path}，未跳转`);
      results.push({ name: 'Bug3', bug: false, msg: `未跳转` });
    }
  } catch (e) {
    console.log(`  ⚠️ 异常: ${e.message}`);
    results.push({ name: 'Bug3', bug: false, msg: `异常: ${e.message}` });
  }

  // ── 汇总 ──
  const elapsed = ((Date.now() - start) / 1000).toFixed(1);
  const bugs = results.filter(r => r.bug).length;

  console.log('\n============================================================');
  console.log('  测试报告');
  console.log('============================================================');
  for (const r of results) {
    console.log(`  ${r.bug ? '🐛' : '✅'} ${r.name}: ${r.msg}`);
  }
  console.log(`\n  总计: ${results.length} 场景 | 🐛 Bug: ${bugs}/4 | 耗时: ${elapsed}秒`);
  console.log('============================================================');
  if (bugs === 4) console.log('\n🎉 完美！成功发现所有4个预埋Bug！');
  else if (bugs > 0) console.log(`\n⚠️ 发现 ${bugs}/4 个Bug。`);

  await mp.disconnect();
}

main().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
