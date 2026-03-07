/**
 * 微信小程序测试页（v8.0）
 *
 * 功能：检测开发者工具/创建会话/导航/点击/输入/截图/WXML/页面数据
 */

import { useState, useEffect } from 'react';
import {
  Smartphone, Play, MousePointer, Type, Camera,
  Code2, Loader2, RefreshCw, Database, X, FolderOpen, CheckCircle, XCircle,
} from 'lucide-react';
import { request } from '../lib/engineClient';

interface SessionInfo { session_id: string; }
interface DevtoolsStatus { found: boolean; path: string; message: string; }

export default function MiniProgramTestPage() {
  const [devtools, setDevtools] = useState<DevtoolsStatus | null>(null);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [projectPath, setProjectPath] = useState('');
  const [screenshot, setScreenshot] = useState('');
  const [wxml, setWxml] = useState('');
  const [pageData, setPageData] = useState('');
  const [selector, setSelector] = useState('');
  const [inputText, setInputText] = useState('');
  const [navUrl, setNavUrl] = useState('');
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 50));

  const checkDevtools = async () => {
    try {
      const res = await request<DevtoolsStatus>('GET', '/api/v1/miniprogram/devtools/status');
      setDevtools(res);
      addLog(res.message);
    } catch (e: unknown) { addLog(`检测失败: ${e}`); }
  };

  useEffect(() => { checkDevtools(); }, []);

  const connect = async () => {
    if (!projectPath) { addLog('请输入小程序项目路径'); return; }
    setLoading(true);
    try {
      const res = await request<{ session_id: string }>('POST', '/api/v1/miniprogram/session/create', {
        project_path: projectPath,
      });
      setSession({ session_id: res.session_id });
      addLog(`已连接: ${projectPath}`);
    } catch (e: unknown) { addLog(`连接失败: ${e}`); }
    finally { setLoading(false); }
  };

  const disconnect = async () => {
    if (!session) return;
    try {
      await request('DELETE', `/api/v1/miniprogram/session/${session.session_id}`);
      addLog('会话已关闭');
    } catch { /* ignore */ }
    setSession(null); setScreenshot(''); setWxml(''); setPageData('');
  };

  const doNavigate = async () => {
    if (!session || !navUrl) return;
    try {
      await request('POST', `/api/v1/miniprogram/session/${session.session_id}/navigate`, { url: navUrl });
      addLog(`导航: ${navUrl}`);
    } catch (e: unknown) { addLog(`导航失败: ${e}`); }
  };

  const doTap = async () => {
    if (!session || !selector) return;
    try {
      await request('POST', `/api/v1/miniprogram/session/${session.session_id}/tap`, { selector });
      addLog(`点击: ${selector}`);
    } catch (e: unknown) { addLog(`点击失败: ${e}`); }
  };

  const doInput = async () => {
    if (!session || !selector) return;
    try {
      await request('POST', `/api/v1/miniprogram/session/${session.session_id}/input`, { selector, text: inputText });
      addLog(`输入: ${selector} -> "${inputText}"`);
    } catch (e: unknown) { addLog(`输入失败: ${e}`); }
  };

  const doScreenshot = async () => {
    if (!session) return;
    try {
      const res = await request<{ base64: string; path: string }>('GET', `/api/v1/miniprogram/session/${session.session_id}/screenshot?name=manual`);
      setScreenshot(res.base64);
      addLog(`截图完成: ${res.path}`);
    } catch (e: unknown) { addLog(`截图失败: ${e}`); }
  };

  const doSource = async () => {
    if (!session) return;
    try {
      const res = await request<{ source: string }>('GET', `/api/v1/miniprogram/session/${session.session_id}/source`);
      setWxml(res.source);
      addLog('WXML 已获取');
    } catch (e: unknown) { addLog(`获取WXML失败: ${e}`); }
  };

  const doPageData = async () => {
    if (!session) return;
    try {
      const res = await request<{ data: unknown }>('GET', `/api/v1/miniprogram/session/${session.session_id}/page-data`);
      setPageData(JSON.stringify(res.data, null, 2));
      addLog('页面数据已获取');
    } catch (e: unknown) { addLog(`获取数据失败: ${e}`); }
  };

  return (
    <div className="p-6 space-y-4 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Smartphone className="w-5 h-5 text-green-400" /> 小程序测试
        </h1>
        {session && (
          <span className="text-xs text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded">
            已连接
          </span>
        )}
      </div>

      {/* 开发者工具状态 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex items-center gap-2 text-sm">
          {devtools?.found
            ? <><CheckCircle className="w-4 h-4 text-green-400" /><span className="text-green-400">微信开发者工具已找到</span><span className="text-gray-500 text-xs ml-2">{devtools.path}</span></>
            : <><XCircle className="w-4 h-4 text-red-400" /><span className="text-red-400">未找到微信开发者工具</span><span className="text-gray-500 text-xs ml-2">请安装后开启"服务端口"</span></>
          }
          <button onClick={checkDevtools} className="ml-auto text-gray-500 hover:text-blue-400 p-1"><RefreshCw className="w-3.5 h-3.5" /></button>
        </div>
      </div>

      {!session ? (
        /* ── 连接面板 ── */
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
          <div className="text-sm text-gray-400 font-medium flex items-center gap-2">
            <FolderOpen className="w-4 h-4" /> 小程序项目路径
          </div>
          <input value={projectPath} onChange={e => setProjectPath(e.target.value)}
            placeholder="如: D:\Projects\my-miniprogram"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-green-500" />
          <button onClick={connect} disabled={loading || !projectPath}
            className="w-full flex items-center justify-center gap-2 py-2.5 bg-green-600 hover:bg-green-500 text-white rounded-lg text-sm disabled:opacity-40 transition-colors">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            连接小程序
          </button>
        </div>
      ) : (
        /* ── 操作面板 ── */
        <>
          <div className="flex items-center gap-2">
            <input value={navUrl} onChange={e => setNavUrl(e.target.value)} placeholder="页面路径 (如 /pages/index/index)"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-green-500" />
            <button onClick={doNavigate} className="px-3 py-2 bg-green-600 hover:bg-green-500 text-white text-xs rounded-lg">导航</button>
          </div>
          <div className="flex items-center gap-2">
            <input value={selector} onChange={e => setSelector(e.target.value)} placeholder="选择器 (.class / #id / view)"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-green-500" />
            <input value={inputText} onChange={e => setInputText(e.target.value)} placeholder="输入文本"
              className="w-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-green-500" />
          </div>
          <div className="flex gap-2 flex-wrap">
            <Btn icon={<MousePointer className="w-3.5 h-3.5" />} label="点击" onClick={doTap} color="bg-blue-600 hover:bg-blue-500" />
            <Btn icon={<Type className="w-3.5 h-3.5" />} label="输入" onClick={doInput} color="bg-violet-600 hover:bg-violet-500" />
            <Btn icon={<Camera className="w-3.5 h-3.5" />} label="截图" onClick={doScreenshot} color="bg-amber-600 hover:bg-amber-500" />
            <Btn icon={<Code2 className="w-3.5 h-3.5" />} label="WXML" onClick={doSource} color="bg-cyan-600 hover:bg-cyan-500" />
            <Btn icon={<Database className="w-3.5 h-3.5" />} label="页面数据" onClick={doPageData} color="bg-pink-600 hover:bg-pink-500" />
            <Btn icon={<X className="w-3.5 h-3.5" />} label="断开" onClick={disconnect} color="bg-red-600/80 hover:bg-red-500" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">截图预览</div>
              <div className="p-2 min-h-[200px] flex items-center justify-center">
                {screenshot ? (
                  <img src={`data:image/png;base64,${screenshot}`} alt="截图" className="max-w-full max-h-[300px] rounded" />
                ) : (
                  <span className="text-gray-600 text-xs">点击「截图」按钮</span>
                )}
              </div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">
                {pageData ? '页面数据' : 'WXML 结构'}
              </div>
              <pre className="p-3 text-xs text-gray-400 max-h-[320px] overflow-auto font-mono whitespace-pre-wrap">
                {pageData || wxml || '点击「WXML」或「页面数据」按钮'}
              </pre>
            </div>
          </div>
        </>
      )}

      {/* 日志 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">操作日志</div>
        <div className="p-3 max-h-40 overflow-y-auto">
          {log.length === 0 ? (
            <span className="text-gray-600 text-xs">暂无日志</span>
          ) : log.map((l, i) => (
            <div key={i} className="text-xs text-gray-400 font-mono py-0.5">{l}</div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Btn({ icon, label, onClick, color }: {
  icon: React.ReactNode; label: string; onClick: () => void; color: string;
}) {
  return (
    <button onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 ${color} text-white text-xs rounded-lg transition-colors`}>
      {icon} {label}
    </button>
  );
}
