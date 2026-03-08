/**
 * 微信小程序自动化桥接服务器（v8.1 - 长连接模式）
 *
 * 启动 HTTP 服务器，保持与微信开发者工具的 WebSocket 连接。
 * Python 通过 HTTP 请求发送命令，避免每次操作都重新连接。
 *
 * 用法：node miniprogram_bridge_server.js <wsPort> [httpPort]
 *   wsPort:   微信开发者工具的 WebSocket 端口（如 60427）
 *   httpPort: HTTP 服务器端口（默认 9421）
 *
 * 依赖：npm install miniprogram-automator
 */

const http = require('http');
const path = require('path');

const WS_PORT = parseInt(process.argv[2] || '9420');
const HTTP_PORT = parseInt(process.argv[3] || '9421');

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
    miniProgram = await automator.connect({
      wsEndpoint: `ws://localhost:${WS_PORT}`,
    });
    currentPage = await miniProgram.currentPage();
    connected = true;
    console.log(`[OK] 已连接到 ws://localhost:${WS_PORT}`);
    console.log(`[OK] 当前页面: ${currentPage ? currentPage.path : '未知'}`);
    return true;
  } catch (e) {
    console.error(`[ERR] 连接失败: ${e.message}`);
    connected = false;
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
        const wxml = await currentPage.data();
        return { success: true, wxml: JSON.stringify(wxml, null, 2) };
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

server.listen(HTTP_PORT, '127.0.0.1', async () => {
  console.log('========================================');
  console.log('  小程序自动化桥接服务器 v8.1');
  console.log(`  HTTP 端口: ${HTTP_PORT}`);
  console.log(`  WebSocket 端口: ${WS_PORT}`);
  console.log('========================================');

  // 启动时自动连接
  await ensureConnected();
});
