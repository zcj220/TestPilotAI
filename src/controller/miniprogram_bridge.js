/**
 * 微信小程序自动化桥接脚本（v8.0）
 *
 * Python 通过子进程调用此脚本，与 miniprogram-automator SDK 通信。
 * 
 * 用法：node miniprogram_bridge.js '{"action":"connect","params":{...}}'
 * 输出：最后一行为 JSON 结果
 *
 * 依赖：npm install miniprogram-automator
 * 前提：微信开发者工具已打开"服务端口"
 */

const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

// 全局 automator 实例缓存文件（跨进程共享状态）
const STATE_FILE = path.join(__dirname, '.miniprogram_state.json');

function loadState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      return JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
    }
  } catch {}
  return {};
}

function saveState(state) {
  fs.writeFileSync(STATE_FILE, JSON.stringify(state), 'utf-8');
}

function output(obj) {
  console.log(JSON.stringify(obj));
}

async function main() {
  let automator, miniProgram, page;

  try {
    automator = require('miniprogram-automator');
  } catch {
    output({
      success: false,
      error: '未安装 miniprogram-automator。请执行: npm install miniprogram-automator',
    });
    return;
  }

  const input = JSON.parse(process.argv[2] || '{}');
  const { action, params } = input;

  try {
    switch (action) {
      case 'connect': {
        const { projectPath, devToolsPath } = params;
        miniProgram = await automator.launch({
          projectPath: projectPath,
          cliPath: devToolsPath,
        });
        page = await miniProgram.currentPage();
        saveState({ connected: true, projectPath });
        output({
          success: true,
          page: page ? page.path : '',
        });
        // 保持进程不退出（不行，单次调用模式）
        // 实际上每次调用都是新进程，需要重新连接
        await miniProgram.disconnect();
        break;
      }

      case 'disconnect': {
        saveState({});
        output({ success: true });
        break;
      }

      case 'navigateTo': {
        const state = loadState();
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        await miniProgram.navigateTo(params.url);
        page = await miniProgram.currentPage();
        output({
          success: true,
          page: page ? page.path : params.url,
        });
        await miniProgram.disconnect();
        break;
      }

      case 'tap': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        const tapEl = await page.$(params.selector);
        if (tapEl) {
          await tapEl.tap();
          output({ success: true });
        } else {
          output({ success: false, error: `元素未找到: ${params.selector}` });
        }
        await miniProgram.disconnect();
        break;
      }

      case 'input': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        const inputEl = await page.$(params.selector);
        if (inputEl) {
          await inputEl.input(params.text);
          output({ success: true });
        } else {
          output({ success: false, error: `元素未找到: ${params.selector}` });
        }
        await miniProgram.disconnect();
        break;
      }

      case 'screenshot': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        await page.screenshot({ path: params.path });
        output({ success: true, path: params.path });
        await miniProgram.disconnect();
        break;
      }

      case 'getWxml': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        const wxml = await page.data();
        output({ success: true, wxml: JSON.stringify(wxml, null, 2) });
        await miniProgram.disconnect();
        break;
      }

      case 'getText': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        const textEl = await page.$(params.selector);
        if (textEl) {
          const text = await textEl.text();
          output({ success: true, text });
        } else {
          output({ success: true, text: '' });
        }
        await miniProgram.disconnect();
        break;
      }

      case 'elementExists': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        const el = await page.$(params.selector);
        output({ success: true, exists: !!el });
        await miniProgram.disconnect();
        break;
      }

      case 'getCurrentPage': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        output({
          success: true,
          path: page ? page.path : '',
          query: page ? page.query : {},
        });
        await miniProgram.disconnect();
        break;
      }

      case 'callWxApi': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        const apiResult = await miniProgram.callWxMethod(params.method, params.params || {});
        output({ success: true, result: apiResult });
        await miniProgram.disconnect();
        break;
      }

      case 'mockWxApi': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        await miniProgram.mockWxMethod(params.method, params.result);
        output({ success: true });
        await miniProgram.disconnect();
        break;
      }

      case 'getAppData': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        // App globalData 通过 evaluate 获取
        const appData = await miniProgram.evaluate(() => {
          return getApp().globalData;
        });
        output({ success: true, data: appData });
        await miniProgram.disconnect();
        break;
      }

      case 'getPageData': {
        miniProgram = await automator.connect({
          wsEndpoint: 'ws://localhost:9420',
        });
        page = await miniProgram.currentPage();
        const pageData = await page.data();
        output({ success: true, data: pageData });
        await miniProgram.disconnect();
        break;
      }

      default:
        output({ success: false, error: `未知操作: ${action}` });
    }
  } catch (err) {
    output({ success: false, error: err.message || String(err) });
  }
}

main().catch(err => {
  output({ success: false, error: err.message || String(err) });
  process.exit(1);
});
