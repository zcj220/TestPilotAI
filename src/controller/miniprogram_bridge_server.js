/**
 * 微信小程序自动化桥接服务器（v9.0 - 自包含模式）
 *
 * 参照 run_blind_test.js 成功经验，启动时自己执行：
 *   cli close → cli open → cli auto --auto-port 9420 → automator.connect()
 * 然后启动 HTTP 服务器供 Python 调用。
 *
 * 用法：node miniprogram_bridge_server.js <projectPath> [wsPort] [httpPort]
 *   projectPath: 小程序项目绝对路径
 *   wsPort:      自动化WebSocket端口（默认9420）
 *   httpPort:    HTTP服务器端口（默认9421）
 *
 * 依赖：npm install miniprogram-automator
 */

const http = require('http');
const path = require('path');
const { execSync } = require('child_process');

const PROJECT_PATH = process.argv[2] || '';
const WS_PORT = parseInt(process.argv[3] || '9420');
const HTTP_PORT = parseInt(process.argv[4] || '9421');

// 自动检测CLI路径（兼容 Windows 和 macOS）
const CLI_CANDIDATES = [
  // macOS
  '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',
  '/Applications/开发工具/wechatwebdevtools.app/Contents/MacOS/cli',
  // Windows
  'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat',
  'C:\\Program Files\\Tencent\\微信web开发者工具\\cli.bat',
  'D:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat',
  'D:\\微信web开发者工具\\cli.bat',
];
let CLI_PATH = '';
const fs = require('fs');
for (const c of CLI_CANDIDATES) {
  if (fs.existsSync(c)) { CLI_PATH = c; break; }
}

let automator, miniProgram, currentPage;
let connected = false;

async function ensureConnected() {
  if (connected && miniProgram) {
    try {
      currentPage = await miniProgram.currentPage();
      return true;
    } catch (e) {
      connected = false;
      miniProgram = null;
    }
  }

  try {
    automator = require('miniprogram-automator');
    // 加超时！参考test_connect.js用Promise.race，避免永远挂住
    miniProgram = await Promise.race([
      automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` }),
      new Promise((_, rej) => setTimeout(() => rej(new Error('automator连接超时(8秒)')), 8000)),
    ]);
    currentPage = await miniProgram.currentPage();
    connected = true;
    console.log(`[OK] 已连接到 ws://localhost:${WS_PORT}`);
    console.log(`[OK] 当前页面: ${currentPage ? currentPage.path : '未知'}`);
    return true;
  } catch (e) {
    console.error(`[ERR] 连接失败: ${e.message}`);
    connected = false;
    miniProgram = null;
    return false;
  }
}

async function handleAction(action, params) {
  if (!connected && action !== 'connect') {
    const ok = await ensureConnected();
    if (!ok) return { success: false, error: '未连接到开发者工具' };
  }

  try {
    switch (action) {
      case 'connect': {
        const ok = await ensureConnected();
        if (ok) {
          return { success: true, page: currentPage ? currentPage.path : '' };
        }
        return { success: false, error: '连接失败' };
      }

      case 'disconnect': {
        if (miniProgram) {
          await miniProgram.disconnect();
        }
        connected = false;
        miniProgram = null;
        return { success: true };
      }

      case 'navigateTo': {
        // 使用evaluate调用原生wx.navigateTo（SDK方法会超时！64ms vs 10秒）
        await miniProgram.evaluate(`wx.navigateTo({ url: '${params.url}' })`);
        await new Promise(r => setTimeout(r, 1500));
        currentPage = await miniProgram.currentPage();
        return { success: true, page: currentPage ? currentPage.path : params.url };
      }

      case 'reLaunch': {
        // 使用evaluate调用原生wx.reLaunch（SDK方法会超时！41ms vs 10秒）
        // reLaunch会清空页面栈，回到指定页面
        await miniProgram.evaluate(`wx.reLaunch({ url: '${params.url}' })`);
        await new Promise(r => setTimeout(r, 1500));
        currentPage = await miniProgram.currentPage();
        return { success: true, page: currentPage ? currentPage.path : params.url };
      }

      case 'tap': {
        currentPage = await miniProgram.currentPage();
        const tapEl = await currentPage.$(params.selector);
        if (tapEl) {
          await tapEl.tap();
          return { success: true };
        }
        return { success: false, error: `元素未找到: ${params.selector}` };
      }

      case 'input': {
        currentPage = await miniProgram.currentPage();
        const inputEl = await currentPage.$(params.selector);
        if (inputEl) {
          await inputEl.input(params.text);
          return { success: true };
        }
        return { success: false, error: `元素未找到: ${params.selector}` };
      }

      case 'screenshot': {
        currentPage = await miniProgram.currentPage();
        await currentPage.screenshot({ path: params.path });
        return { success: true, path: params.path };
      }

      case 'getText': {
        currentPage = await miniProgram.currentPage();
        const textEl = await currentPage.$(params.selector);
        if (textEl) {
          const text = await textEl.text();
          return { success: true, text };
        }
        return { success: true, text: '' };
      }

      case 'elementExists': {
        currentPage = await miniProgram.currentPage();
        const el = await currentPage.$(params.selector);
        return { success: true, exists: !!el };
      }

      case 'getCurrentPage': {
        currentPage = await miniProgram.currentPage();
        return {
          success: true,
          path: currentPage ? currentPage.path : '',
          query: currentPage ? currentPage.query : {},
        };
      }

      case 'getWxml': {
        currentPage = await miniProgram.currentPage();
        // 用 $$('*') 遍历元素树，拼成结构化信息（page.data() 只返回数据对象，不是 WXML）
        const allEls = await currentPage.$$('view, button, input, text, picker, switch, image, navigator, scroll-view, swiper, form, label, checkbox, radio, slider, textarea');
        const tree = [];
        const limit = 50;
        for (let i = 0; i < Math.min(allEls.length, limit); i++) {
          const el = allEls[i];
          const tag = await el.tagName().catch(() => '');
          const cls = await el.attribute('class').catch(() => '');
          const txt = await el.text().catch(() => '');
          const ph = await el.attribute('placeholder').catch(() => '');
          tree.push({ tag, class: cls || '', text: (txt || '').slice(0, 30), placeholder: ph || '' });
        }
        return { success: true, wxml: JSON.stringify(tree, null, 2) };
      }

      case 'listElements': {
        // 列出页面可交互元素（供 AI 诊断使用）
        currentPage = await miniProgram.currentPage();
        const interactiveTags = 'button, input, textarea, picker, switch, navigator, view[bindtap], view[catchtap]';
        const iEls = await currentPage.$$(interactiveTags).catch(() => []);
        // 兜底：如果事件选择器不支持，用基础标签
        const els = (iEls && iEls.length > 0) ? iEls
          : await currentPage.$$('button, input, textarea, picker, switch, navigator').catch(() => []);
        const items = [];
        const max = 30;
        for (let i = 0; i < Math.min(els.length, max); i++) {
          const el = els[i];
          const tag = await el.tagName().catch(() => '');
          const cls = await el.attribute('class').catch(() => '');
          const text = await el.text().catch(() => '');
          const ph = await el.attribute('placeholder').catch(() => '');
          if (tag) items.push({ tag, class: cls || '', text: (text || '').slice(0, 30), placeholder: ph || '' });
        }
        return { success: true, elements: items };
      }

      case 'getPageData': {
        currentPage = await miniProgram.currentPage();
        const pageData = await currentPage.data();
        return { success: true, data: pageData };
      }

      case 'getAppData': {
        const appData = await miniProgram.evaluate(() => {
          return getApp().globalData;
        });
        return { success: true, data: appData };
      }

      case 'evaluate': {
        const evalResult = await miniProgram.evaluate(new Function(params.code));
        return { success: true, result: evalResult };
      }

      case 'navigateBack': {
        // 使用evaluate调用原生wx.navigateBack（SDK方法会超时！25ms vs 10秒）
        await miniProgram.evaluate(`wx.navigateBack()`);
        await new Promise(r => setTimeout(r, 1500));
        currentPage = await miniProgram.currentPage();
        return { success: true, page: currentPage ? currentPage.path : '' };
      }

      case 'setPageData': {
        currentPage = await miniProgram.currentPage();
        await currentPage.setData(params.data);
        return { success: true };
      }

      case 'ping': {
        return { success: true, connected, port: WS_PORT };
      }

      default:
        return { success: false, error: `未知操作: ${action}` };
    }
  } catch (e) {
    console.error(`[ERR] ${action}: ${e.message}`);
    // 如果操作失败，尝试重新连接
    if (e.message.includes('disconnect') || e.message.includes('closed')) {
      connected = false;
      miniProgram = null;
    }
    return { success: false, error: e.message };
  }
}

const server = http.createServer(async (req, res) => {
  if (req.method !== 'POST') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ success: true, message: 'MiniProgram Bridge Server', connected, port: WS_PORT }));
    return;
  }

  let body = '';
  req.on('data', chunk => { body += chunk; });
  req.on('end', async () => {
    try {
      const { action, params } = JSON.parse(body);
      console.log(`[CMD] ${action}`, params ? JSON.stringify(params).substring(0, 80) : '');
      const result = await handleAction(action, params || {});
      console.log(`[RES] ${action}: ${result.success ? 'OK' : 'FAIL'}`);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result));
    } catch (e) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ success: false, error: e.message }));
    }
  });
});

// ═══ 参照 run_blind_test.js 的启动流程 ═══
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

function runCli(cmd) {
  try {
    const r = execSync(`"${CLI_PATH}" ${cmd}`, { timeout: 15000, encoding: 'utf8', stdio: 'pipe' });
    console.log(`[CLI] ${cmd.split(' ')[0]} 完成`);
    return r;
  } catch (e) {
    console.log(`[CLI] ${cmd.split(' ')[0]} 失败（可忽略）: ${(e.message || '').substring(0, 80)}`);
    return '';
  }
}

async function initAndConnect() {
  if (!CLI_PATH) {
    console.error('[ERR] 未找到微信开发者工具CLI');
    return;
  }
  if (!PROJECT_PATH) {
    console.log('[WARN] 未指定项目路径，跳过自动启动，等待手动connect');
    return;
  }

  console.log(`[INIT] 项目: ${PROJECT_PATH}`);
  console.log(`[INIT] CLI: ${CLI_PATH}`);
  console.log(`[INIT] 端口: ${WS_PORT}`);

  // 跟 run_blind_test.js 一模一样的流程
  console.log('[1/4] cli close...');
  runCli(`close --project "${PROJECT_PATH}"`);
  await sleep(3000);

  console.log('[2/4] cli open...');
  runCli(`open --project "${PROJECT_PATH}"`);
  await sleep(5000);

  console.log('[3/4] cli auto --auto-port ' + WS_PORT + '...');
  runCli(`auto --project "${PROJECT_PATH}" --auto-port ${WS_PORT}`);
  await sleep(3000);

  // 跟 run_blind_test.js 一样：重试连接
  console.log('[4/4] 连接automator...');
  for (let i = 0; i < 5; i++) {
    const ok = await ensureConnected();
    if (ok) {
      console.log(`[OK] 连接成功（第${i + 1}次）`);
      return;
    }
    console.log(`[RETRY] 第${i + 1}次失败，等3秒...`);
    await sleep(3000);
  }
  console.error('[FAIL] 5次连接均失败，等待手动connect');
}

server.listen(HTTP_PORT, '127.0.0.1', () => {
  console.log('========================================');
  console.log('  小程序自动化桥接服务器 v9.0');
  console.log(`  HTTP 端口: ${HTTP_PORT}`);
  console.log(`  WebSocket 端口: ${WS_PORT}`);
  console.log('========================================');
  // 启动后自动执行 close→open→auto→connect
  initAndConnect().catch(e => console.error('[ERR] 初始化失败:', e.message));
});
