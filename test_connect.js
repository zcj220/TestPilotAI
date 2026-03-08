/**
 * 诊断脚本：测试微信开发者工具自动化连接
 */
const { execSync } = require('child_process');
const automator = require('miniprogram-automator');

const CLI = 'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat';
const PROJECT = 'D:\\projects\\TestPilotAI\\miniprogram-demo';
const WS_PORT = 9420;

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  // 步骤1: close
  console.log('[1] cli close...');
  try { execSync(`"${CLI}" close --project "${PROJECT}"`, { timeout: 15000, stdio: 'pipe' }); } catch(e) {}
  console.log('[1] done');
  await sleep(3000);

  // 步骤2: open
  console.log('[2] cli open...');
  try {
    const r = execSync(`"${CLI}" open --project "${PROJECT}"`, { timeout: 15000, encoding: 'utf8', stdio: 'pipe' });
    console.log('[2] output:', r.trim());
  } catch(e) {
    console.log('[2] stderr:', (e.stderr || '').toString().substring(0, 300));
  }
  await sleep(3000);

  // 步骤3: auto --auto-port
  console.log('[3] cli auto --auto-port ' + WS_PORT + '...');
  try {
    const r = execSync(`"${CLI}" auto --project "${PROJECT}" --auto-port ${WS_PORT}`, { timeout: 15000, encoding: 'utf8', stdio: 'pipe' });
    console.log('[3] output:', r.trim());
  } catch(e) {
    console.log('[3] stderr:', (e.stderr || '').toString().substring(0, 300));
  }
  await sleep(3000);

  // 步骤4: 检查端口
  console.log('[4] 检查端口 ' + WS_PORT + '...');
  const net = require('net');
  const portOpen = await new Promise(resolve => {
    const s = net.createConnection(WS_PORT, '127.0.0.1');
    s.setTimeout(2000);
    s.on('connect', () => { s.destroy(); resolve(true); });
    s.on('error', () => resolve(false));
    s.on('timeout', () => { s.destroy(); resolve(false); });
  });
  console.log('[4] 端口 ' + WS_PORT + (portOpen ? ' 已打开' : ' 未打开'));

  // 步骤5: 尝试连接automator
  console.log('[5] 尝试连接 ws://localhost:' + WS_PORT + '...');
  for (let i = 0; i < 5; i++) {
    try {
      const mp = await Promise.race([
        automator.connect({ wsEndpoint: `ws://localhost:${WS_PORT}` }),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout 5s')), 5000))
      ]);
      const page = await mp.currentPage();
      console.log('[5] 连接成功! 页面:', page.path);
      await mp.disconnect();
      return;
    } catch(e) {
      console.log(`[5] 第${i+1}次失败: ${e.message}`);
      await sleep(3000);
    }
  }

  // 步骤6: 如果9420不行，扫描其他端口
  console.log('[6] 扫描其他端口...');
  try {
    const r = execSync('netstat -ano | findstr LISTENING | findstr 127.0.0.1', { encoding: 'utf8', timeout: 5000 });
    const ports = [];
    r.split('\n').forEach(line => {
      const m = line.match(/127\.0\.0\.1:(\d+)/);
      if (m) {
        const p = parseInt(m[1]);
        if (p > 9000 && p < 65535 && p !== 9421 && p !== 8900) ports.push(p);
      }
    });
    const unique = [...new Set(ports)].sort((a,b) => a-b);
    console.log('[6] 候选端口:', unique.join(', '));

    for (const port of unique.slice(0, 10)) {
      try {
        const mp = await Promise.race([
          automator.connect({ wsEndpoint: `ws://localhost:${port}` }),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), 3000))
        ]);
        const page = await mp.currentPage();
        console.log(`[6] 端口 ${port} 连接成功! 页面: ${page.path}`);
        await mp.disconnect();
        return;
      } catch(e) {
        // skip
      }
    }
    console.log('[6] 所有候选端口均失败');
  } catch(e) {
    console.log('[6] 扫描失败:', e.message);
  }
}

main().catch(e => console.error('Fatal:', e.message));
