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

  // 策略3: quit彻底杀进程 → open → auto（跟手动修复流程一致）
  console.log('[策略3] cli quit 彻底杀进程后重启...');
  runCli('quit');
  await sleep(5000);
  console.log('[策略3] cli open...');
  runCli(`open --project "${PROJECT_PATH}"`);
  await sleep(8000);
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
        // 用 evaluate(wx.reLaunch) —— 跟 run_blind_test.js 一样，不用SDK方法
        const url = step.value || '';
        await mp.evaluate(`wx.reLaunch({ url: '${url}' })`);
        await sleep(1500);
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
        // 通用JS执行：蓝本里写evaluate表达式，执行器执行
        // value里是JS代码，可以访问 getApp()、wx.xxx 等
        const code = step.value || '';
        const evalResult = await mp.evaluate(code);
        // 如果有expected，对比返回值
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
        // 读取元素文本，存入结果data字段
        const el = await page.$(step.target);
        const text = el ? await el.text() : '';
        // 如果有expected，做断言
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
        // wx.navigateTo（不清空页面栈，跟reLaunch不同）
        const url = step.value || '';
        await mp.evaluate(`wx.navigateTo({ url: '${url}' })`);
        await sleep(1500);
        break;
      }
      case 'reset_state': {
        // 重置全局状态（场景间清理）
        const code = step.value || "const g=getApp().globalData; g.cart=[]; g.coupon=null; g.address=''; g.deliveryType=''; g.isVip=true;";
        await mp.evaluate(code);
        // reLaunch回首页
        await mp.evaluate("wx.reLaunch({ url: '/pages/index/index' })");
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

  // 执行所有步骤
  for (let i = 0; i < steps.length; i++) {
    const result = await executeStep(steps[i], i + 1);
    results.push(result);
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
