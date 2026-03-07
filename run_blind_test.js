/**
 * FreshMart 盲测脚本 v3
 *
 * 正规盲测：完全根据蓝本功能需求操作UI，测试者不知道Bug在哪。
 *
 * 核心策略：每个场景前用 cli auto 重启小程序，确保干净的首页状态。
 * 这样每个场景完全独立，不受前一个场景影响，随便跳页面。
 *
 * 用法: node run_blind_test.js
 */
const automator = require('miniprogram-automator');
const { execSync } = require('child_process');
const WS_PORT = 9420;
const CLI_PATH = 'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat';
const PROJECT_PATH = 'D:\\projects\\TestPilotAI\\miniprogram-demo';

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

let mp = null;
const results = [];

// ── 重启小程序并连接（每个场景前调用） ──
async function restart() {
  if (mp) {
    try { await mp.disconnect(); } catch(e) {}
    mp = null;
  }
  console.log('  [重启] cli auto...');
  try {
    execSync(`"${CLI_PATH}" auto --project "${PROJECT_PATH}" --auto-port ${WS_PORT}`, {
      encoding: 'utf8', timeout: 30000, stdio: 'pipe',
    });
  } catch(e) {
    // cli auto 有时 stderr 输出但实际成功
  }
  await sleep(2000);

  // 连接
  for (let retry = 0; retry < 3; retry++) {
    try {
      mp = await automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` });
      const page = await mp.currentPage();
      console.log(`  [重启] 成功，页面: ${page.path}`);
      return page;
    } catch(e) {
      console.log(`  [重启] 连接重试 ${retry+1}...`);
      await sleep(2000);
    }
  }
  throw new Error('重启后无法连接');
}

function logResult(name, passed, detail) {
  const icon = passed ? '✅' : '🐛';
  console.log(`  ${icon} ${detail}`);
  results.push({ name, passed, detail });
}

// ═══════════════════════════════════════
// 场景1: 会员价格验证
// 蓝本: "会员享8折优惠，验证会员价=原价×0.8"
// 方式: 读取页面上的原价和会员价，计算验证
// ═══════════════════════════════════════
async function testVipPrice() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 会员价格验证');
  console.log('蓝本: 页面标注"会员享8折优惠"，验证会员价=原价×0.8');
  console.log('═'.repeat(50));

  const page = await restart();

  // 读页面上的会员标识
  const badge = await page.$('#vipBadge');
  const badgeText = badge ? await badge.text() : '';
  console.log(`  [1] 会员标识: "${badgeText}"`);

  // 读第1个商品（苹果）的原价和会员价
  const priceEl = await page.$('#price-1');
  const vipPriceEl = await page.$('#vipPrice-1');
  const priceText = priceEl ? await priceEl.text() : '';
  const vipText = vipPriceEl ? await vipPriceEl.text() : '';
  console.log(`  [2] 原价: ${priceText}`);
  console.log(`  [3] 会员价: ${vipText}`);

  const price = parseFloat(priceText.replace(/[^0-9.]/g, ''));
  const vip = parseFloat(vipText.replace(/[^0-9.]/g, ''));
  const expected = Math.round(price * 0.8 * 100) / 100;
  console.log(`  [4] ${price} × 0.8 = ${expected}，实际 = ${vip}`);

  if (Math.abs(vip - expected) < 0.01) {
    logResult('会员价格', true, `会员价${vip}=原价${price}×0.8=${expected}，正确`);
  } else {
    logResult('会员价格', false, `会员价${vip}≠原价${price}×0.8=${expected}，差${(vip - expected).toFixed(2)}元`);
  }
}

// ═══════════════════════════════════════
// 场景2: 库存限制验证
// 蓝本: "商品有库存限制，验证加入购物车时是否检查库存上限"
// 方式: 连续点"加入购物车"超过库存次数，看是否拦截
// ═══════════════════════════════════════
async function testStockLimit() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 库存限制验证');
  console.log('蓝本: 库存10的商品，加入超过10次应拦截');
  console.log('═'.repeat(50));

  const page = await restart();

  // 读取苹果库存
  const stockEl = await page.$('#stock-1');
  const stockText = stockEl ? await stockEl.text() : '';
  const stockNum = parseInt(stockText.replace(/[^0-9]/g, ''));
  console.log(`  [1] 苹果库存: ${stockNum}`);

  // 连续点击加入购物车 stockNum+2 次
  const addBtns = await page.$$('.btn-primary');
  for (let i = 0; i < stockNum + 2; i++) {
    if (addBtns[0]) await addBtns[0].tap();
    await sleep(150);
  }
  await sleep(300);

  // 读取提示消息和购物车数量
  const msgEl = await page.$('#message');
  const msg = msgEl ? await msgEl.text() : '';
  const cartCountEl = await page.$('#cartCount');
  const cartCount = cartCountEl ? await cartCountEl.text() : '';
  console.log(`  [2] 消息: "${msg}"`);
  console.log(`  [3] 购物车数量: ${cartCount}`);

  const count = parseInt(cartCount) || 0;
  if (count <= stockNum) {
    logResult('库存限制', true, `库存${stockNum}，购物车${count}件，限制正确`);
  } else {
    logResult('库存限制', false, `库存${stockNum}但购物车${count}件，超出未限制！`);
  }
}

// ═══════════════════════════════════════
// 场景3: 搜索排序验证
// 蓝本: "按价格从低到高排序，验证排序结果是否正确"
// 方式: 选择排序方式，读取页面上的价格列表
// ═══════════════════════════════════════
async function testSortOrder() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 搜索排序验证');
  console.log('蓝本: 价格从低到高排序应正确');
  console.log('═'.repeat(50));

  const page = await restart();

  // 选择"价格从低到高"排序 (picker index=1)
  // picker 不能直接tap，用 callMethod 模拟事件
  await page.callMethod('onSortChange', { detail: { value: 1 } });
  await sleep(500);

  // 读取排序后的价格
  const priceEls = await page.$$('.p-price');
  const prices = [];
  for (const el of priceEls) {
    const text = await el.text();
    const num = parseFloat(text.replace(/[^0-9.]/g, ''));
    if (!isNaN(num)) prices.push(num);
  }
  console.log(`  [1] 排序后价格: [${prices.join(', ')}]`);

  let sorted = true;
  for (let i = 1; i < prices.length; i++) {
    if (prices[i] < prices[i - 1]) {
      sorted = false;
      console.log(`  [2] 错误: ${prices[i-1]} > ${prices[i]}（位置${i-1}和${i}）`);
      break;
    }
  }

  if (sorted) {
    logResult('搜索排序', true, '价格升序排序正确');
  } else {
    logResult('搜索排序', false, `排序错误: [${prices.join(', ')}] 不是升序！`);
  }
}

// ═══════════════════════════════════════
// 场景4: 售罄商品验证
// 蓝本: "库存0的商品应显示售罄且不能加入购物车"
// 方式: 找到售罄商品，点击按钮，检查购物车
// ═══════════════════════════════════════
async function testSoldOut() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 售罄商品验证');
  console.log('蓝本: 库存0应显示售罄且不能加购');
  console.log('═'.repeat(50));

  const page = await restart();

  // 红心火龙果 id=7 库存=0
  const stockEl = await page.$('#stock-7');
  const stockText = stockEl ? await stockEl.text() : '';
  console.log(`  [1] 火龙果库存: ${stockText}`);

  const btn = await page.$('#product-7 .btn-primary');
  const btnText = btn ? await btn.text() : '';
  console.log(`  [2] 按钮: "${btnText}"`);

  if (btn) { await btn.tap(); await sleep(300); }

  const cartCountEl = await page.$('#cartCount');
  const count = cartCountEl ? await cartCountEl.text() : '0';
  console.log(`  [3] 购物车: ${count}`);

  if (btnText.includes('售罄') && parseInt(count) === 0) {
    logResult('售罄商品', true, '售罄正确显示，不能加购');
  } else {
    logResult('售罄商品', false, `按钮"${btnText}"，购物车${count}`);
  }
}

// ═══════════════════════════════════════
// 场景5: 购物车总价精度
// 蓝本: "验证购物车总价计算是否精确"
// 方式: 加多件商品→跳购物车→读总价→验证
// ═══════════════════════════════════════
async function testCartPrecision() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 购物车总价精度');
  console.log('蓝本: 多件商品总价应无浮点误差');
  console.log('═'.repeat(50));

  const page = await restart();

  // 加3次苹果（会员价10.63）
  const addBtns = await page.$$('.btn-primary');
  for (let i = 0; i < 3; i++) {
    if (addBtns[0]) await addBtns[0].tap();
    await sleep(200);
  }
  console.log('  [1] 加入3个苹果');

  // 点"查看购物车"跳到购物车页
  const cartBar = await page.$('.cart-bar');
  if (cartBar) { await cartBar.tap(); await sleep(2000); }

  let cartPage = await mp.currentPage();
  console.log(`  [2] 当前页面: ${cartPage.path}`);

  const subtotalEl = await cartPage.$('#subtotal');
  const subtotal = subtotalEl ? await subtotalEl.text() : '';
  console.log(`  [3] 总计: ${subtotal}`);

  // 会员价10.63 × 3 = 31.89 精确
  const actual = parseFloat(subtotal.replace(/[^0-9.]/g, ''));
  const expected = Math.round(10.63 * 3 * 100) / 100; // 31.89
  console.log(`  [4] 期望: ${expected}，实际: ${actual}`);

  if (Math.abs(actual - expected) < 0.01) {
    logResult('总价精度', true, `总价${actual}=${expected}，精确`);
  } else {
    logResult('总价精度', false, `总价${actual}≠${expected}，差${(actual - expected).toFixed(4)}！`);
  }
}

// ═══════════════════════════════════════
// 场景6: 优惠券满减验证
// 蓝本: "满100减20，验证金额=100时能否使用"
// 方式: 加商品凑到100→跳结算→选优惠券→看消息
// ═══════════════════════════════════════
async function testCoupon() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 优惠券满减验证');
  console.log('蓝本: "满100减20"，金额=100时应能使用');
  console.log('═'.repeat(50));

  const page = await restart();

  // 加8个苹果：原价12.5 × 8 = 100（会员价10.63×8=85.04，不够100）
  // 所以要用原价凑。先关闭会员
  await mp.evaluate(() => { getApp().globalData.isVip = false; });
  await page.callMethod('onShow'); // 刷新页面数据
  await sleep(300);

  const addBtns = await page.$$('.btn-primary');
  for (let i = 0; i < 8; i++) {
    if (addBtns[0]) await addBtns[0].tap();
    await sleep(150);
  }
  console.log('  [1] 加入8个苹果(非会员，原价12.5×8=100)');

  // 直接跳到结算页
  await mp.navigateTo('/pages/checkout/checkout');
  await sleep(2000);

  let checkoutPage = await mp.currentPage();
  console.log(`  [2] 当前: ${checkoutPage.path}`);

  // 读小计
  const subtotalEl = await checkoutPage.$('#checkoutSubtotal');
  const subtotal = subtotalEl ? await subtotalEl.text() : '';
  console.log(`  [3] 小计: ${subtotal}`);

  // 点"满100减20"优惠券
  const coupon1 = await checkoutPage.$('#coupon-1');
  if (coupon1) { await coupon1.tap(); await sleep(500); }

  const msgEl = await checkoutPage.$('#checkoutMessage');
  const msg = msgEl ? await msgEl.text() : '';
  console.log(`  [4] 消息: "${msg}"`);

  if (msg.includes('已使用')) {
    logResult('优惠券满减', true, `小计100，满100减20成功使用`);
  } else {
    logResult('优惠券满减', false, `小计${subtotal}满100却不能用券: "${msg}"`);
  }
}

// ═══════════════════════════════════════
// 场景7: 配送费验证
// 蓝本: "同城配送免费，快递10元"
// 方式: 加商品→跳结算→选同城配送→看配送费
// ═══════════════════════════════════════
async function testDeliveryFee() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 配送费验证');
  console.log('蓝本: 同城配送标注免费(0元)');
  console.log('═'.repeat(50));

  const page = await restart();

  // 加1个商品
  const addBtns = await page.$$('.btn-primary');
  if (addBtns[0]) { await addBtns[0].tap(); await sleep(300); }
  console.log('  [1] 加入1个商品');

  // 直接跳到结算页
  await mp.navigateTo('/pages/checkout/checkout');
  await sleep(2000);

  let checkoutPage = await mp.currentPage();
  console.log(`  [2] 当前: ${checkoutPage.path}`);

  // 选同城配送 (picker index 0)
  await checkoutPage.callMethod('onDeliveryChange', { detail: { value: 0 } });
  await sleep(300);

  const feeEl = await checkoutPage.$('#deliveryFee');
  const fee = feeEl ? await feeEl.text() : '';
  console.log(`  [3] 配送费: ${fee}`);

  const feeNum = parseFloat(fee.replace(/[^0-9.]/g, ''));

  if (feeNum === 0) {
    logResult('配送费', true, '同城配送费=0，免费正确');
  } else {
    logResult('配送费', false, `同城配送标注免费但实际收¥${feeNum}！`);
  }
}

// ── 主流程 ──
async function main() {
  console.log('============================================================');
  console.log('  FreshMart 生鲜超市 - 正规盲测 v3');
  console.log('  每个场景前 cli auto 重启，正规操作UI发现Bug');
  console.log('============================================================');

  const start = Date.now();

  await testVipPrice();
  await testStockLimit();
  await testSortOrder();
  await testSoldOut();
  await testCartPrecision();
  await testCoupon();
  await testDeliveryFee();

  if (mp) await mp.disconnect();

  // 汇总
  const elapsed = ((Date.now() - start) / 1000).toFixed(1);
  const bugs = results.filter(r => !r.passed);
  const passed = results.filter(r => r.passed);

  console.log('\n============================================================');
  console.log('  盲测报告');
  console.log('============================================================');
  for (const r of results) {
    console.log(`  ${r.passed ? '✅' : '🐛'} ${r.name}: ${r.detail}`);
  }
  console.log(`\n  🐛 发现: ${bugs.length} | ✅ 通过: ${passed.length} | 总计: ${results.length} | 耗时: ${elapsed}秒`);
  console.log('============================================================');

  // JSON报告
  console.log('\n[JSON报告]');
  console.log(JSON.stringify({
    summary: { total: results.length, bugs: bugs.length, passed: passed.length, seconds: parseFloat(elapsed) },
    bugs: bugs.map(r => ({ scenario: r.name, detail: r.detail })),
    passed: passed.map(r => ({ scenario: r.name, detail: r.detail })),
  }, null, 2));
}

main().catch(e => { console.error('Fatal:', e.message); process.exit(1); });
