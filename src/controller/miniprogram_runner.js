/**
 * 小程序蓝本执行器 v1.0
 *
 * 参照 run_blind_test.js 成功经验，一次性执行：
 *   close → open → auto → connect → 执行蓝本步骤 → 输出JSON结果
 *
 * 用法：node miniprogram_runner.js <stepsJsonFile>
 *   stepsJsonFile: 包含测试步骤的JSON文件路径
 *
 * 输入JSON格式：
 *   {
 *     "project_path": "D:/projects/xxx/miniprogram-demo",
 *     "ws_port": 9420,
 *     "steps": [
 *       { "action": "navigate", "value": "/pages/index/index" },
 *       { "action": "click", "target": "#product-1 .btn-primary" },
 *       { "action": "screenshot", "description": "截图" },
 *       { "action": "assert_text", "target": "#vipBadge", "expected": "会员" }
 *     ]
 *   }
 *
 * 输出：JSON到stdout（Python读取解析）
 */

const automator = require('miniprogram-automator');
const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// ── 读取输入 ──
const stepsFile = process.argv[2];
if (!stepsFile || !fs.existsSync(stepsFile)) {
  console.error(JSON.stringify({ success: false, error: '请指定步骤JSON文件路径' }));
  process.exit(1);
}

const rawContent = fs.readFileSync(stepsFile, 'utf8').replace(/^\uFEFF/, '');
const input = JSON.parse(rawContent);
const PROJECT_PATH = input.project_path || '';
const WS_PORT = input.ws_port || 9420;
const steps = input.steps || [];

// 自动检测CLI路径
const CLI_CANDIDATES = [
  'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat',
  'C:\\Program Files\\Tencent\\微信web开发者工具\\cli.bat',
];
let CLI_PATH = '';
for (const c of CLI_CANDIDATES) {
  if (fs.existsSync(c)) { CLI_PATH = c; break; }
}

const SCREENSHOT_DIR = path.join(path.dirname(stepsFile), 'screenshots');
if (!fs.existsSync(SCREENSHOT_DIR)) fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
let mp = null;

// ── 跟 run_blind_test.js 一模一样的初始化 ──
function runCli(cmd) {
  try {
    execSync(`"${CLI_PATH}" ${cmd}`, { encoding: 'utf8', timeout: 15000, stdio: 'pipe' });
  } catch (e) {
    // close 失败可忽略
  }
}

async function tryConnect() {
  mp = await Promise.race([
    automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` }),
    new Promise((_, rej) => setTimeout(() => rej(new Error('超时5秒')), 5000)),
  ]);
  const page = await mp.currentPage();
  return page.path;
}

async function initConnect() {
  if (!CLI_PATH) throw new Error('未找到微信开发者工具CLI');
  if (!PROJECT_PATH) throw new Error('未指定项目路径');

  // 策略1: 先直接连（如果模拟器已开且auto已启动，0秒就能连上）
  try {
    const p = await tryConnect();
    console.log('[策略1] 直接连接成功，页面: ' + p);
    return p;
  } catch (e) {
    console.log('[策略1] 直接连接失败: ' + e.message);
  }

  // 策略2: 只执行auto（不close不open，避免模拟器崩溃）
  console.log('[策略2] 执行 cli auto...');
  runCli(`auto --project "${PROJECT_PATH}" --auto-port ${WS_PORT}`);
  await sleep(3000);
  for (let i = 0; i < 3; i++) {
    try {
      const p = await tryConnect();
      console.log('[策略2] auto后连接成功，页面: ' + p);
      return p;
    } catch (e) {
      if (i < 2) await sleep(3000);
    }
  }

  // 策略3: 强杀所有进程 → open → auto（最终手段）
  console.log('[策略3] 强杀所有微信开发者工具进程...');
  try {
    execSync('taskkill /F /IM wechatdevtools.exe /T', { encoding: 'utf8', timeout: 10000, stdio: 'pipe' });
  } catch (e) {}
  try {
    execSync('taskkill /F /IM WeChatAppEx.exe /T', { encoding: 'utf8', timeout: 10000, stdio: 'pipe' });
  } catch (e) {}
  await sleep(5000);
  console.log('[策略3] cli open...');
  runCli(`open --project "${PROJECT_PATH}"`);
  await sleep(10000);
  console.log('[策略3] cli auto...');
  runCli(`auto --project "${PROJECT_PATH}" --auto-port ${WS_PORT}`);
  await sleep(3000);
  for (let i = 0; i < 5; i++) {
    try {
      const p = await tryConnect();
      console.log('[策略3] 重启后连接成功，页面: ' + p);
      return p;
    } catch (e) {
      console.log('[策略3] 重试 ' + (i+1) + '/5: ' + e.message);
      if (i < 4) await sleep(3000);
    }
  }
  throw new Error('所有策略均失败。请确认: 1)微信开发者工具已安装 2)设置→安全设置→已开启服务端口');
}

// ── 执行单个步骤 ──
async function executeStep(step, stepNum) {
  const start = Date.now();
  const page = await mp.currentPage();

  try {
    switch (step.action) {
      case 'navigate': {
        // 用 new Function + evaluate，跟 run_blind_test.js 传箭头函数一样
        const navUrl = step.value || '';
        await mp.evaluate(new Function('wx.reLaunch({ url: "' + navUrl + '" })'));
        await sleep(2000);
        break;
      }
      case 'click': {
        const el = await page.$(step.target);
        if (!el) throw new Error(`元素未找到: ${step.target}`);
        await el.tap();
        await sleep(500);
        break;
      }
      case 'fill': {
        const el = await page.$(step.target);
        if (!el) throw new Error(`元素未找到: ${step.target}`);
        await el.input(step.value || '');
        await sleep(300);
        break;
      }
      case 'screenshot': {
        const filename = `step${String(stepNum).padStart(2, '0')}_screenshot.png`;
        const filepath = path.join(SCREENSHOT_DIR, filename);
        await mp.screenshot({ path: filepath });
        return { step: stepNum, action: step.action, status: 'passed', duration: (Date.now() - start) / 1000, screenshot: filepath, description: step.description || '' };
      }
      case 'assert_text': {
        const el = await page.$(step.target);
        const text = el ? await el.text() : '';
        if (step.expected && !text.includes(step.expected)) {
          throw new Error(`断言失败: 预期"${step.expected}"，实际"${text}"`);
        }
        break;
      }
      case 'wait': {
        await sleep(step.timeout_ms || parseInt(step.value) || 2000);
        break;
      }
      case 'scroll': {
        const scrollTop = parseInt(step.value) || 400;
        await mp.evaluate(`wx.pageScrollTo({ scrollTop: ${scrollTop} })`);
        await sleep(500);
        break;
      }
      case 'evaluate': {
        // 小程序端执行：用 new Function 构造函数传给 evaluate
        // 这样能支持 const/let/var 声明语句和复杂逻辑
        var code = step.value || '';
        const evalFn = new Function(code);
        const evalResult = await mp.evaluate(evalFn);
        if (step.expected !== undefined && step.expected !== '') {
          const actual = JSON.stringify(evalResult);
          const expect = String(step.expected);
          if (!actual.includes(expect)) {
            throw new Error(`evaluate断言失败: 预期包含"${expect}"，实际="${actual}"`);
          }
        }
        await sleep(parseInt(step.wait_ms) || 500);
        return { step: stepNum, action: step.action, status: 'passed', duration: (Date.now() - start) / 1000, description: step.description || '', data: evalResult };
      }
      case 'page_query': {
        // Node端执行：用page.$和page.$$查询元素并做验证
        // target=选择器，value=要做的操作（text/count/texts）
        const selector = step.target || '';
        const op = step.value || 'text';
        let result;
        if (op === 'count') {
          const els = await page.$$(selector);
          result = els.length;
        } else if (op === 'texts') {
          const els = await page.$$(selector);
          const texts = [];
          for (const el of els) { texts.push(await el.text()); }
          result = texts;
        } else {
          const el = await page.$(selector);
          result = el ? await el.text() : '';
        }
        if (step.expected !== undefined && step.expected !== '') {
          const actual = JSON.stringify(result);
          if (!actual.includes(String(step.expected))) {
            throw new Error(`查询断言失败: "${selector}"的${op}="${actual}"不包含"${step.expected}"`);
          }
        }
        return { step: stepNum, action: step.action, status: 'passed', duration: (Date.now() - start) / 1000, description: step.description || '', data: result };
      }
      case 'call_method': {
        // 调用页面方法：target=方法名，value=JSON参数
        const method = step.target || '';
        let args = {};
        try { args = JSON.parse(step.value || '{}'); } catch(e) {}
        await page.callMethod(method, args);
        await sleep(parseInt(step.wait_ms) || 500);
        break;
      }
      case 'read_text': {
        // 读取元素文本（带重试），存入结果data字段
        let text = '';
        for (let r = 0; r < 3; r++) {
          const el = await page.$(step.target);
          text = el ? await el.text() : '';
          if (text) break;
          if (r < 2) await sleep(1000);
        }
        if (step.expected !== undefined && step.expected !== '') {
          if (!text.includes(step.expected)) {
            throw new Error(`文本断言失败: "${step.target}"的文本"${text}"不包含"${step.expected}"`);
          }
        }
        return { step: stepNum, action: step.action, status: 'passed', duration: (Date.now() - start) / 1000, description: step.description || '', data: text };
      }
      case 'tap_multiple': {
        // 连续点击：target=选择器，value=次数，wait_ms=每次间隔
        const selector = step.target || '';
        const times = parseInt(step.value) || 1;
        const interval = parseInt(step.wait_ms) || 150;
        const els = await page.$$(selector);
        if (!els || els.length === 0) throw new Error(`元素未找到: ${selector}`);
        for (let t = 0; t < times; t++) {
          await els[0].tap();
          await sleep(interval);
        }
        await sleep(300);
        break;
      }
      case 'assert_compare': {
        // 数值比较断言：target=选择器读数值，value=比较表达式如"<=10"
        const el = await page.$(step.target);
        const text = el ? await el.text() : '0';
        const num = parseFloat(text.replace(/[^0-9.\-]/g, ''));
        const expr = step.value || '';
        const match = expr.match(/^([<>=!]+)\s*([\d.]+)$/);
        if (!match) throw new Error(`无效比较表达式: "${expr}"`);
        const op = match[1];
        const expected = parseFloat(match[2]);
        let ok = false;
        switch(op) {
          case '==': ok = Math.abs(num - expected) < 0.01; break;
          case '!=': ok = Math.abs(num - expected) >= 0.01; break;
          case '<': ok = num < expected; break;
          case '<=': ok = num <= expected; break;
          case '>': ok = num > expected; break;
          case '>=': ok = num >= expected; break;
          default: throw new Error(`不支持的比较运算符: ${op}`);
        }
        if (!ok) throw new Error(`数值断言失败: ${num} ${op} ${expected} 为false`);
        return { step: stepNum, action: step.action, status: 'passed', duration: (Date.now() - start) / 1000, description: step.description || '', data: { actual: num, expected, op } };
      }
      case 'navigate_to': {
        // wx.navigateTo（不清空页面栈）—— 用new Function
        const navToUrl = step.value || '';
        await mp.evaluate(new Function('wx.navigateTo({ url: "' + navToUrl + '" })'));
        await sleep(1500);
        break;
      }
      case 'reset_state': {
        // 重置全局状态（场景间清理）—— 用 new Function 传函数给 evaluate
        await mp.evaluate(new Function(
          'var g = getApp().globalData;' +
          'g.cart = []; g.coupon = null; g.address = ""; g.deliveryType = ""; g.isVip = true;'
        ));
        // reLaunch回首页（不调callMethod，避免SDK超时）
        await mp.evaluate(new Function('wx.reLaunch({ url: "/pages/index/index" })'));
        await sleep(2000);
        break;
      }
      default:
        break;
    }
    return { step: stepNum, action: step.action, status: 'passed', duration: (Date.now() - start) / 1000, description: step.description || '' };
  } catch (e) {
    return { step: stepNum, action: step.action, status: 'failed', duration: (Date.now() - start) / 1000, error: e.message, description: step.description || '' };
  }
}

// ── 主流程 ──
async function main() {
  const totalStart = Date.now();
  const results = [];

  // 初始化连接
  const initPage = await initConnect();

  // 执行所有步骤（逐步输出进度到stderr，Python端实时读取）
  for (let i = 0; i < steps.length; i++) {
    const stepDesc = steps[i].description || steps[i].action;
    process.stderr.write(`[PROGRESS] ${i+1}/${steps.length} ${stepDesc}\n`);
    const result = await executeStep(steps[i], i + 1);
    results.push(result);
    const icon = result.status === 'passed' ? '✅' : '❌';
    process.stderr.write(`[STEP] ${icon} #${i+1} ${result.status} ${stepDesc} (${result.duration.toFixed(1)}s)\n`);
  }

  // 断开连接
  try { await mp.disconnect(); } catch (e) {}

  const totalDuration = (Date.now() - totalStart) / 1000;
  const passed = results.filter(r => r.status === 'passed').length;
  const failed = results.length - passed;

  // 输出JSON结果到stdout（Python读取）
  const output = {
    success: true,
    init_page: initPage,
    total_steps: results.length,
    passed,
    failed,
    duration: totalDuration,
    results,
  };
  console.log(JSON.stringify(output));
}

main().catch(e => {
  console.log(JSON.stringify({ success: false, error: e.message }));
  process.exit(1);
});
