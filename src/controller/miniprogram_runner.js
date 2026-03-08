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

const input = JSON.parse(fs.readFileSync(stepsFile, 'utf8'));
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

  // 策略3: open+auto（不做close！close会破坏模拟器状态）
  console.log('[策略3] 执行 open + auto（不close）...');
  runCli(`open --project "${PROJECT_PATH}"`);
  await sleep(5000);
  runCli(`auto --project "${PROJECT_PATH}" --auto-port ${WS_PORT}`);
  await sleep(3000);
  for (let i = 0; i < 5; i++) {
    try {
      const p = await tryConnect();
      console.log('[策略3] open+auto后连接成功，页面: ' + p);
      return p;
    } catch (e) {
      if (i < 4) await sleep(3000);
    }
  }
  throw new Error('所有策略均失败。请手动在开发者工具中点编译(Ctrl+B)后重试');
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
        await sleep(step.timeout_ms || 2000);
        break;
      }
      case 'scroll': {
        await mp.evaluate('wx.pageScrollTo({ scrollTop: 400 })');
        await sleep(500);
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
