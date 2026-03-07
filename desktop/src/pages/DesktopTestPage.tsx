/**
 * 桌面应用测试页（v7.0）
 *
 * 功能：枚举窗口/创建会话/点击/输入/截图/UI树/AI分析
 */

import { useState, useEffect } from 'react';
import {
  Monitor, Play, MousePointer, Type, Camera,
  Code2, Loader2, RefreshCw, Zap, X,
} from 'lucide-react';
import { request } from '../lib/engineClient';

interface WinInfo { hwnd: number; title: string; class_name: string; pid: number; }
interface SessionInfo { session_id: string; hwnd: number; }

export default function DesktopTestPage() {
  const [windows, setWindows] = useState<WinInfo[]>([]);
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [screenshot, setScreenshot] = useState('');
  const [uiTree, setUiTree] = useState('');
  const [selector, setSelector] = useState('');
  const [inputText, setInputText] = useState('');
  const [log, setLog] = useState<string[]>([]);

  const addLog = (msg: string) => setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 50));

  const refreshWindows = async () => {
    setLoading(true);
    try {
      const res = await request<{ windows: WinInfo[] }>('GET', '/api/v1/desktop/windows');
      setWindows(res.windows || []);
      addLog(`发现 ${res.windows?.length || 0} 个窗口`);
    } catch (e: unknown) { addLog(`枚举窗口失败: ${e}`); }
    finally { setLoading(false); }
  };

  useEffect(() => { refreshWindows(); }, []);

  const connect = async (win: WinInfo) => {
    setLoading(true);
    try {
      const res = await request<{ session_id: string; hwnd: number }>('POST', '/api/v1/desktop/session/create', {
        target_title: win.title, target_pid: win.pid,
      });
      setSession({ session_id: res.session_id, hwnd: res.hwnd });
      addLog(`已连接: ${win.title} (hwnd=${res.hwnd})`);
    } catch (e: unknown) { addLog(`连接失败: ${e}`); }
    finally { setLoading(false); }
  };

  const disconnect = async () => {
    if (!session) return;
    try {
      await request('DELETE', `/api/v1/desktop/session/${session.session_id}`);
      addLog('会话已关闭');
    } catch { /* ignore */ }
    setSession(null); setScreenshot(''); setUiTree('');
  };

  const doTap = async () => {
    if (!session || !selector) return;
    try {
      await request('POST', `/api/v1/desktop/session/${session.session_id}/tap`, { selector });
      addLog(`点击: ${selector}`);
    } catch (e: unknown) { addLog(`点击失败: ${e}`); }
  };

  const doInput = async () => {
    if (!session || !selector) return;
    try {
      await request('POST', `/api/v1/desktop/session/${session.session_id}/input`, { selector, text: inputText });
      addLog(`输入: ${selector} -> "${inputText}"`);
    } catch (e: unknown) { addLog(`输入失败: ${e}`); }
  };

  const doScreenshot = async () => {
    if (!session) return;
    try {
      const res = await request<{ base64: string; path: string }>('GET', `/api/v1/desktop/session/${session.session_id}/screenshot?name=manual`);
      setScreenshot(res.base64);
      addLog(`截图完成: ${res.path}`);
    } catch (e: unknown) { addLog(`截图失败: ${e}`); }
  };

  const doSource = async () => {
    if (!session) return;
    try {
      const res = await request<{ source: string }>('GET', `/api/v1/desktop/session/${session.session_id}/source`);
      setUiTree(res.source);
      addLog('UI树已获取');
    } catch (e: unknown) { addLog(`获取UI树失败: ${e}`); }
  };

  const doAnalyze = async () => {
    if (!session) return;
    setLoading(true);
    try {
      const res = await request<{ analysis: string; screenshot_base64: string }>('POST', `/api/v1/desktop/session/${session.session_id}/analyze`);
      setScreenshot(res.screenshot_base64);
      addLog(`AI分析: ${res.analysis?.slice(0, 100)}...`);
    } catch (e: unknown) { addLog(`AI分析失败: ${e}`); }
    finally { setLoading(false); }
  };

  return (
    <div className="p-6 space-y-4 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Monitor className="w-5 h-5 text-blue-400" /> 桌面应用测试
        </h1>
        <div className="flex items-center gap-2">
          {session && (
            <span className="text-xs text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded">
              已连接 hwnd={session.hwnd}
            </span>
          )}
          <button onClick={refreshWindows} className="text-gray-500 hover:text-blue-400 transition-colors p-1">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {!session ? (
        /* ── 窗口列表 ── */
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-800 text-sm text-gray-400 font-medium">
            选择要测试的窗口
          </div>
          {loading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-blue-400" /></div>
          ) : windows.length === 0 ? (
            <div className="text-center py-10 text-gray-500 text-sm">未发现可用窗口</div>
          ) : (
            <div className="divide-y divide-gray-800 max-h-80 overflow-y-auto">
              {windows.map(w => (
                <button key={w.hwnd} onClick={() => connect(w)}
                  className="w-full flex items-center justify-between px-5 py-2.5 hover:bg-gray-800/50 transition-colors text-left">
                  <div>
                    <div className="text-sm text-white">{w.title}</div>
                    <div className="text-xs text-gray-500">Class: {w.class_name} | PID: {w.pid}</div>
                  </div>
                  <Play className="w-4 h-4 text-gray-600" />
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        /* ── 操作面板 ── */
        <>
          <div className="flex items-center gap-2">
            <input value={selector} onChange={e => setSelector(e.target.value)} placeholder="选择器 (name:XX / automationid:XX / point:X,Y)"
              className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500" />
            <input value={inputText} onChange={e => setInputText(e.target.value)} placeholder="输入文本"
              className="w-40 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 outline-none focus:border-blue-500" />
          </div>
          <div className="flex gap-2 flex-wrap">
            <Btn icon={<MousePointer className="w-3.5 h-3.5" />} label="点击" onClick={doTap} color="bg-blue-600 hover:bg-blue-500" />
            <Btn icon={<Type className="w-3.5 h-3.5" />} label="输入" onClick={doInput} color="bg-violet-600 hover:bg-violet-500" />
            <Btn icon={<Camera className="w-3.5 h-3.5" />} label="截图" onClick={doScreenshot} color="bg-amber-600 hover:bg-amber-500" />
            <Btn icon={<Code2 className="w-3.5 h-3.5" />} label="UI树" onClick={doSource} color="bg-cyan-600 hover:bg-cyan-500" />
            <Btn icon={<Zap className="w-3.5 h-3.5" />} label="AI分析" onClick={doAnalyze} color="bg-emerald-600 hover:bg-emerald-500" disabled={loading} />
            <Btn icon={<X className="w-3.5 h-3.5" />} label="断开" onClick={disconnect} color="bg-red-600/80 hover:bg-red-500" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* 截图预览 */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">截图预览</div>
              <div className="p-2 min-h-[200px] flex items-center justify-center">
                {screenshot ? (
                  <img src={`data:image/bmp;base64,${screenshot}`} alt="截图" className="max-w-full max-h-[300px] rounded" />
                ) : (
                  <span className="text-gray-600 text-xs">点击「截图」按钮</span>
                )}
              </div>
            </div>
            {/* UI 树 */}
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">UI 树</div>
              <pre className="p-3 text-xs text-gray-400 max-h-[320px] overflow-auto font-mono whitespace-pre-wrap">
                {uiTree || '点击「UI树」按钮获取窗口控件结构'}
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

function Btn({ icon, label, onClick, color, disabled }: {
  icon: React.ReactNode; label: string; onClick: () => void; color: string; disabled?: boolean;
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className={`flex items-center gap-1.5 px-3 py-1.5 ${color} text-white text-xs rounded-lg disabled:opacity-40 transition-colors`}>
      {icon} {label}
    </button>
  );
}
