/**
 * 自动发现微信开发者工具的WebSocket端口
 * 扫描 wechatdevtools 进程监听的所有端口，逐个尝试 miniprogram-automator 连接
 *
 * 用法: node auto_find_port.js
 * 输出: 成功连接的端口号（纯数字），或 "FAIL"
 */
const { execSync } = require('child_process');
const automator = require('miniprogram-automator');

async function findPort() {
  // 1. 找到 wechatdevtools 进程的 PID
  let pids = [];
  try {
    const out = execSync('tasklist /FI "IMAGENAME eq wechatdevtools.exe" /FO CSV /NH', { encoding: 'utf8' });
    const lines = out.trim().split('\n');
    for (const line of lines) {
      const match = line.match(/"wechatdevtools\.exe","(\d+)"/i);
      if (match) pids.push(match[1]);
    }
  } catch (e) {}

  if (pids.length === 0) {
    console.error('未找到微信开发者工具进程');
    console.log('FAIL');
    return;
  }

  // 2. 找到这些 PID 监听的端口
  const ports = new Set();
  try {
    const out = execSync('netstat -ano', { encoding: 'utf8' });
    for (const line of out.split('\n')) {
      if (!line.includes('LISTENING')) continue;
      for (const pid of pids) {
        if (line.trim().endsWith(pid)) {
          const match = line.match(/127\.0\.0\.1:(\d+)/);
          if (match) ports.add(parseInt(match[1]));
        }
      }
    }
  } catch (e) {}

  if (ports.size === 0) {
    console.error('未找到监听端口');
    console.log('FAIL');
    return;
  }

  // 3. 逐个尝试连接
  const sortedPorts = [...ports].sort((a, b) => a - b);
  console.error(`发现 ${sortedPorts.length} 个候选端口: ${sortedPorts.join(', ')}`);

  for (const port of sortedPorts) {
    try {
      const mp = await automator.connect({
        wsEndpoint: `ws://localhost:${port}`,
      });
      const page = await mp.currentPage();
      console.error(`端口 ${port} 连接成功，当前页面: ${page.path}`);
      await mp.disconnect();
      // 输出纯数字端口号到 stdout
      console.log(port);
      return;
    } catch (e) {
      // 连接失败，继续下一个
    }
  }

  console.error('所有端口尝试失败');
  console.log('FAIL');
}

findPort().catch(e => {
  console.error('错误:', e.message);
  console.log('FAIL');
});
