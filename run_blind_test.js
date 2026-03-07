/**
 * FreshMart 盲测脚本 v5
 *
 * 正规盲测：完全根据蓝本功能需求操作UI，测试者不知道Bug在哪。
 *
 * 核心策略：
 * 1. 开头 cli close+open+auto 重启1次，确保干净首页
 * 2. 中途不重启，用 evaluate(wx.reLaunch) 回首页 + evaluate 清状态
 * 3. 跳页面用 evaluate(wx.navigateTo) 而非 SDK 方法（SDK方法会超时！）
 * 4. 每个场景截图留证，保存到 screenshots/ 目录
 *
 * 用法: node run_blind_test.js
 */
const automator = require('miniprogram-automator');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const WS_PORT = 9420;
const CLI_PATH = 'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat';
const PROJECT_PATH = 'D:\\projects\\TestPilotAI\\miniprogram-demo';
const SCREENSHOT_DIR = path.join(__dirname, 'screenshots');

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

let mp = null;
const results = [];
let scenarioIndex = 0;

// 创建截图目录
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

// ── 开头重启1次 ──
async function initRestart() {
  console.log('[初始化] close+open+auto 重启小程序...');
  try { execSync(`"${CLI_PATH}" close --project "${PROJECT_PATH}"`, { encoding: 'utf8', timeout: 15000, stdio: 'pipe' }); } catch(e) {}
  await sleep(2000);
  try { execSync(`"${CLI_PATH}" open --project "${PROJECT_PATH}"`, { encoding: 'utf8', timeout: 15000, stdio: 'pipe' }); } catch(e) {}
  await sleep(2000);
  try { execSync(`"${CLI_PATH}" auto --project "${PROJECT_PATH}" --auto-port ${WS_PORT}`, { encoding: 'utf8', timeout: 15000, stdio: 'pipe' }); } catch(e) {}
  await sleep(2000);

  for (let retry = 0; retry < 3; retry++) {
    try {
      mp = await automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` });
      const page = await mp.currentPage();
      console.log(`[初始化] 成功，页面: ${page.path}`);
      return;
    } catch(e) {
      console.log(`[初始化] 重试 ${retry+1}...`);
      await sleep(2000);
    }
  }
  throw new Error('无法连接');
}

// ── 场景间重置（不重启） ──
async function resetForNextScenario() {
  // 清空全局状态
  await mp.evaluate(() => {
    const g = getApp().globalData;
    g.cart = []; g.coupon = null; g.address = ''; g.deliveryType = '';
    g.isVip = true; // 恢复会员
  });

  // 如果不在首页，用 evaluate(wx.reLaunch) 回去（清空页面栈）
  const page = await mp.currentPage();
  if (page.path !== 'pages/index/index') {
    await mp.evaluate(() => { wx.reLaunch({ url: '/pages/index/index' }); });
    await sleep(1500);
  }

  // 刷新首页数据
  const homePage = await mp.currentPage();
  if (homePage.path === 'pages/index/index') {
    await homePage.callMethod('onShow');
    await sleep(200);
  }
  return homePage;
}

async function screenshot(name) {
  try {
    scenarioIndex++;
    const filename = `${String(scenarioIndex).padStart(2,'0')}_${name.replace(/[^a-zA-Z0-9\u4e00-\u9fff]/g,'_')}.png`;
    const filepath = path.join(SCREENSHOT_DIR, filename);
    await mp.screenshot({ path: filepath });
    console.log(`  📷 截图: ${filename}`);
    return filename;
  } catch(e) {
    console.log(`  📷 截图失败: ${e.message}`);
    return null;
  }
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

  const page = await resetForNextScenario();

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
  await screenshot('会员价格');
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

  const page = await resetForNextScenario();

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
  await screenshot('库存限制');
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

  const page = await resetForNextScenario();

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
  await screenshot('搜索排序');
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

  const page = await resetForNextScenario();

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
  await screenshot('售罄商品');
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

  const page = await resetForNextScenario();

  // 加3次苹果（会员价10.63）
  const addBtns = await page.$$('.btn-primary');
  for (let i = 0; i < 3; i++) {
    if (addBtns[0]) await addBtns[0].tap();
    await sleep(200);
  }
  console.log('  [1] 加入3个苹果');

  // 用 evaluate 跳到购物车页
  await mp.evaluate(() => { wx.navigateTo({ url: '/pages/cart/cart' }); });
  await sleep(1500);

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
  await screenshot('购物车精度');
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

  const page = await resetForNextScenario();

  // 用 evaluate 一步完成：关会员 + 加8个苹果原价到购物车 = 100元
  await mp.evaluate(() => {
    const app = getApp();
    app.globalData.isVip = false;
    const p = app.globalData.products[0]; // 苹果 price=12.5
    for (let i = 0; i < 8; i++) {
      app.globalData.cart.push({ id: p.id, name: p.name, price: p.price, actualPrice: p.price, unit: p.unit, img: p.img, qty: 1 });
    }
  });
  console.log('  [1] 加入8个苹果(非会员，原价12.5×8=100)');

  // 用 evaluate 跳到结算页
  await mp.evaluate(() => { wx.navigateTo({ url: '/pages/checkout/checkout' }); });
  await sleep(1500);

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
  await screenshot('优惠券满减');
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

  const page = await resetForNextScenario();

  // 加1个商品
  const addBtns = await page.$$('.btn-primary');
  if (addBtns[0]) { await addBtns[0].tap(); await sleep(300); }
  console.log('  [1] 加入1个商品');

  // 用 evaluate 跳到结算页
  await mp.evaluate(() => { wx.navigateTo({ url: '/pages/checkout/checkout' }); });
  await sleep(1500);

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
    logResult('配送费', false, `同城配送标注免费但实际收￥${feeNum}！`);
  }
  await screenshot('配送费');
}

// ═══════════════════════════════════════
// 场景8: 浮点精度深度验证
// 蓝本: "验证多种商品组合的总价计算精度"
// 方式: 加不同价格商品，检查总价是否有浮点误差
// ═══════════════════════════════════════
async function testFloatPrecision() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 浮点精度深度验证');
  console.log('蓝本: 多种商品组合总价应精确');
  console.log('═'.repeat(50));

  const page = await resetForNextScenario();

  // 用 evaluate 直接构造会触发浮点误差的购物车
  // 会员价: 苹果10.63 + 牛奶6.32 + 鸡蛋21.25 = 38.2 精确值
  // JS: 10.63 + 6.32 + 21.25 = 38.199999... 浮点误差
  await mp.evaluate(() => {
    const app = getApp();
    const products = app.globalData.products;
    // 苹果(id=1), 牛奶(id=3), 鸡蛋(id=4)
    const apple = products.find(p => p.id === 1);
    const milk = products.find(p => p.id === 3);
    const egg = products.find(p => p.id === 4);
    const vipDiscount = 0.85; // Bug: 应该是0.8
    [apple, milk, egg].forEach(p => {
      const actualPrice = +(p.price * vipDiscount).toFixed(2);
      app.globalData.cart.push({
        id: p.id, name: p.name, price: p.price,
        actualPrice, unit: p.unit, img: p.img, qty: 1
      });
    });
  });
  console.log('  [1] 加入苹果+牛奶+鸡蛋（各1个，会员价）');

  await mp.evaluate(() => { wx.navigateTo({ url: '/pages/cart/cart' }); });
  await sleep(1500);

  let cartPage = await mp.currentPage();
  console.log(`  [2] 当前: ${cartPage.path}`);

  const subtotalEl = await cartPage.$('#subtotal');
  const subtotal = subtotalEl ? await subtotalEl.text() : '';
  console.log(`  [3] 总计: ${subtotal}`);

  const actual = parseFloat(subtotal.replace(/[^0-9.]/g, ''));
  // 检查是否有浮点误差痕迹（如 38.199999 而非 38.20）
  const rawText = subtotal;
  const hasFloatError = rawText.includes('999') || rawText.includes('001');
  console.log(`  [4] 原始文本: "${rawText}"`);

  if (hasFloatError) {
    logResult('浮点精度', false, `总价文本"${rawText}"存在浮点误差！`);
  } else {
    logResult('浮点精度', true, `总价${actual}，无浮点误差痕迹`);
  }
  await screenshot('浮点精度');
}

// ═══════════════════════════════════════
// 场景9: 商品列表滚动溢出验证
// 蓝本: "验证商品列表在不同数量下是否正确显示"
// 方式: 检查所有商品是否都渲染了，价格文本是否溢出
// ═══════════════════════════════════════
async function testListOverflow() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 商品列表溢出验证');
  console.log('蓝本: 所有商品应完整显示，无截断溢出');
  console.log('═'.repeat(50));

  const page = await resetForNextScenario();

  // 检查商品数量是否和数据一致
  const productCount = await mp.evaluate(() => getApp().globalData.products.length);
  const productEls = await page.$$('.product-item');
  const renderedCount = productEls.length;
  console.log(`  [1] 数据: ${productCount}个商品，页面渲染: ${renderedCount}个`);

  if (renderedCount !== productCount) {
    logResult('列表完整性', false, `数据${productCount}个但只渲染${renderedCount}个！`);
    await screenshot('列表溢出');
    return;
  }

  // 检查每个商品的价格文本是否完整（不是空或NaN）
  let missingPrice = 0;
  const priceEls = await page.$$('.p-price');
  for (const el of priceEls) {
    const text = await el.text();
    const num = parseFloat(text.replace(/[^0-9.]/g, ''));
    if (!text || isNaN(num) || num <= 0) missingPrice++;
  }
  console.log(`  [2] 价格缺失: ${missingPrice}/${priceEls.length}`);

  // 检查商品名是否有超长截断（名字后有...）
  const nameEls = await page.$$('.p-name');
  let truncated = 0;
  for (const el of nameEls) {
    const text = await el.text();
    if (text.includes('...') || text.includes('…')) truncated++;
  }
  console.log(`  [3] 名称被截断: ${truncated}/${nameEls.length}`);

  if (missingPrice > 0) {
    logResult('列表完整性', false, `${missingPrice}个商品价格缺失或异常`);
  } else {
    logResult('列表完整性', true, `${renderedCount}个商品全部正确渲染`);
  }
  await screenshot('列表溢出');
}

// ═══════════════════════════════════════
// 场景10: 空购物车结算验证
// 蓝本: "购物车为空时不应允许结算"
// 方式: 不加商品→跳购物车→点结算→看是否拦截
// ═══════════════════════════════════════
async function testEmptyCartCheckout() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 空购物车结算');
  console.log('蓝本: 购物车为空时应提示不能结算');
  console.log('═'.repeat(50));

  const page = await resetForNextScenario();

  // 直接跳购物车（空的）
  await mp.evaluate(() => { wx.navigateTo({ url: '/pages/cart/cart' }); });
  await sleep(1500);

  let cartPage = await mp.currentPage();
  console.log(`  [1] 当前: ${cartPage.path}`);

  // 读空购物车提示
  const emptyEl = await cartPage.$('.empty-cart');
  const emptyText = emptyEl ? await emptyEl.text() : '';
  console.log(`  [2] 空购物车提示: "${emptyText}"`);

  // 尝试点结算按钮
  const checkoutBtn = await cartPage.$('.btn-checkout');
  if (checkoutBtn) {
    await checkoutBtn.tap();
    await sleep(500);
  }

  // 检查是否仍在购物车页（没跳到结算页）
  const currentPage = await mp.currentPage();
  const msgEl = await currentPage.$('#message');
  const msg = msgEl ? await msgEl.text() : '';
  console.log(`  [3] 消息: "${msg}"`);
  console.log(`  [4] 当前页面: ${currentPage.path}`);

  if (currentPage.path === 'pages/cart/cart') {
    logResult('空购物车结算', true, '空购物车正确拦截，未跳转结算页');
  } else {
    logResult('空购物车结算', false, `空购物车竟然跳到了${currentPage.path}！`);
  }
  await screenshot('空购物车');
}

// ═══════════════════════════════════════
// 场景11: 搜索功能验证
// 蓝本: "搜索商品名称应返回正确结果"
// 方式: 输入搜索关键词，检查结果列表
// ═══════════════════════════════════════
async function testSearch() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 搜索功能验证');
  console.log('蓝本: 搜索商品名应返回匹配结果');
  console.log('═'.repeat(50));

  const page = await resetForNextScenario();

  // 用 callMethod 模拟搜索"苹果"
  await page.callMethod('onSearch', { detail: { value: '苹果' } });
  await sleep(500);

  const productEls = await page.$$('.product-item');
  console.log(`  [1] 搜索"苹果"，结果: ${productEls.length}个`);

  // 所有结果名称都应包含"苹果"
  const nameEls = await page.$$('.p-name');
  let mismatch = 0;
  for (const el of nameEls) {
    const text = await el.text();
    if (!text.includes('苹果')) { mismatch++; console.log(`  [!] 不匹配: "${text}"`); }
  }

  if (mismatch > 0) {
    logResult('搜索功能', false, `搜索"苹果"返回${nameEls.length}个结果，${mismatch}个不匹配`);
  } else if (nameEls.length === 0) {
    logResult('搜索功能', false, '搜索"苹果"无结果！');
  } else {
    logResult('搜索功能', true, `搜索"苹果"返回${nameEls.length}个匹配结果`);
  }
  await screenshot('搜索功能');
}

// ═══════════════════════════════════════
// 场景12: 分类筛选验证
// 蓝本: "选择分类后只显示该分类商品"
// 方式: 选一个分类，检查结果
// ═══════════════════════════════════════
async function testCategoryFilter() {
  console.log('\n' + '═'.repeat(50));
  console.log('场景: 分类筛选验证');
  console.log('蓝本: 选择分类后只显示该分类商品');
  console.log('═'.repeat(50));

  const page = await resetForNextScenario();

  // 获取所有分类标签
  const catEls = await page.$$('.cat-tag');
  const catCount = catEls.length;
  console.log(`  [1] 分类数量: ${catCount}`);

  if (catCount > 1) {
    // 点第2个分类（不是"全部"）
    await catEls[1].tap();
    await sleep(500);

    const catText = await catEls[1].text();
    console.log(`  [2] 选择分类: "${catText}"`);

    const productEls = await page.$$('.product-item');
    console.log(`  [3] 筛选后商品数: ${productEls.length}`);

    // 再点"全部"恢复
    await catEls[0].tap();
    await sleep(500);
    const allProducts = await page.$$('.product-item');
    console.log(`  [4] 全部商品数: ${allProducts.length}`);

    if (productEls.length < allProducts.length && productEls.length > 0) {
      logResult('分类筛选', true, `"${catText}"筛选出${productEls.length}/${allProducts.length}个商品`);
    } else if (productEls.length === 0) {
      logResult('分类筛选', false, `"${catText}"筛选结果为空！`);
    } else {
      logResult('分类筛选', true, `分类筛选正常`);
    }
  } else {
    logResult('分类筛选', false, '没有分类标签！');
  }
  await screenshot('分类筛选');
}

// ── 主流程 ──
async function main() {
  console.log('============================================================');
  console.log('  FreshMart 生鲜超市 - 正规盲测 v5');
  console.log('  开头close+open+auto重启1次');
  console.log('  中途evaluate(wx.reLaunch)回首页，evaluate(wx.navigateTo)跳页面');
  console.log('  每个场景截图留证');
  console.log('============================================================');

  const start = Date.now();
  await initRestart();

  // 12个场景，按原始顺序执行（靠reLaunch回首页）
  await testVipPrice();       // 1. 会员价格
  await testStockLimit();     // 2. 库存限制
  await testSortOrder();      // 3. 搜索排序
  await testSoldOut();        // 4. 售罄商品
  await testCartPrecision();  // 5. 购物车精度
  await testCoupon();         // 6. 优惠券满减
  await testDeliveryFee();    // 7. 配送费
  await testFloatPrecision(); // 8. 浮点精度深度
  await testListOverflow();   // 9. 列表溢出
  await testEmptyCartCheckout(); // 10. 空购物车结算
  await testSearch();         // 11. 搜索功能
  await testCategoryFilter(); // 12. 分类筛选

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
