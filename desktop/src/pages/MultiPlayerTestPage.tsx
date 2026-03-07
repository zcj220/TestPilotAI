/**
 * 多端协同测试页（v9.0 Phase1+Phase2）
 *
 * 功能：创建房间/添加玩家/网格截图/时序轴/AI扮演/录制回放/跨端一致性
 */

import { useState, useEffect, useRef } from 'react';
import {
  Users, Plus, Play, Square, Camera, Trash2, RefreshCw,
  Loader2, Clock, Gamepad2, Zap, Bot, Circle, CircleStop,
  Download, CheckCircle2, AlertTriangle, Shield, Gauge,
} from 'lucide-react';
import { request } from '../lib/engineClient';

interface PlayerInfo {
  status: string;
  platform: string;
  screenshots: number;
  last_error: string;
}

interface RoomStatus {
  running: boolean;
  player_count: number;
  elapsed: number;
  players: Record<string, PlayerInfo>;
  timeline_count: number;
}

interface TimelineEntry {
  player: string;
  action: string;
  detail: string;
  offset: number;
  duration: number;
  success: boolean;
}

const PLATFORM_OPTIONS = [
  { value: 'web', label: 'Web' },
  { value: 'android', label: 'Android' },
  { value: 'desktop', label: '桌面' },
  { value: 'miniprogram', label: '小程序' },
];

const STATUS_COLORS: Record<string, string> = {
  idle: 'text-gray-500',
  connecting: 'text-yellow-400',
  ready: 'text-green-400',
  executing: 'text-blue-400',
  waiting: 'text-purple-400',
  done: 'text-emerald-400',
  error: 'text-red-400',
  disconnected: 'text-gray-600',
};

export default function MultiPlayerTestPage() {
  const [status, setStatus] = useState<RoomStatus | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [newPlayerId, setNewPlayerId] = useState('');
  const [newPlatform, setNewPlatform] = useState('web');
  const [log, setLog] = useState<string[]>([]);
  const [view, setView] = useState<'grid' | 'timeline' | 'ai' | 'record' | 'consistency'>('grid');
  const [aiStrategy, setAiStrategy] = useState('normal');
  const [aiPlayerId, setAiPlayerId] = useState('');
  const [aiReport, setAiReport] = useState<any>(null);
  const [recording, setRecording] = useState(false);
  const [replayStatus, setReplayStatus] = useState<any>(null);
  const [consistencyResult, setConsistencyResult] = useState<any>(null);
  const [consistencySummary, setConsistencySummary] = useState<any>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const addLog = (msg: string) =>
    setLog(prev => [`[${new Date().toLocaleTimeString()}] ${msg}`, ...prev].slice(0, 80));

  const fetchStatus = async () => {
    try {
      const res = await request<RoomStatus>('GET', '/api/v1/multiplayer/room/status');
      setStatus(res);
    } catch { /* ignore */ }
  };

  const fetchTimeline = async () => {
    try {
      const res = await request<{ timeline: TimelineEntry[] }>('GET', '/api/v1/multiplayer/room/timeline');
      setTimeline(res.timeline);
    } catch { /* ignore */ }
  };

  useEffect(() => {
    fetchStatus();
    pollRef.current = setInterval(() => { fetchStatus(); fetchTimeline(); }, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const createRoom = async () => {
    setLoading(true);
    try {
      await request('POST', '/api/v1/multiplayer/room/create');
      addLog('房间已创建');
      await fetchStatus();
    } catch (e: unknown) { addLog(`创建失败: ${e}`); }
    finally { setLoading(false); }
  };

  const addPlayer = async () => {
    if (!newPlayerId) return;
    try {
      const res = await request<{ player_count: number }>('POST', '/api/v1/multiplayer/room/player', {
        player_id: newPlayerId, platform: newPlatform,
      });
      addLog(`玩家 ${newPlayerId} 已加入 (${newPlatform})，当前 ${res.player_count} 人`);
      setNewPlayerId('');
      await fetchStatus();
    } catch (e: unknown) { addLog(`添加失败: ${e}`); }
  };

  const removePlayer = async (pid: string) => {
    try {
      await request('DELETE', `/api/v1/multiplayer/room/player/${pid}`);
      addLog(`已移除 ${pid}`);
      await fetchStatus();
    } catch (e: unknown) { addLog(`移除失败: ${e}`); }
  };

  const startTest = async () => {
    try {
      await request('POST', '/api/v1/multiplayer/room/start');
      addLog('测试开始');
      await fetchStatus();
    } catch (e: unknown) { addLog(`启动失败: ${e}`); }
  };

  const stopTest = async () => {
    try {
      const res = await request<{ elapsed: number }>('POST', '/api/v1/multiplayer/room/stop');
      addLog(`测试停止，用时 ${res.elapsed}s`);
      await fetchStatus();
    } catch (e: unknown) { addLog(`停止失败: ${e}`); }
  };

  const screenshotAll = async () => {
    try {
      const res = await request<{ count: number }>('POST', '/api/v1/multiplayer/room/screenshot-all');
      addLog(`全员截图完成: ${res.count} 张`);
    } catch (e: unknown) { addLog(`截图失败: ${e}`); }
  };

  const destroyRoom = async () => {
    try {
      await request('DELETE', '/api/v1/multiplayer/room');
      addLog('房间已销毁');
      await fetchStatus();
    } catch (e: unknown) { addLog(`销毁失败: ${e}`); }
  };

  // ── Phase2: AI 扮演 ──
  const startAI = async (pid: string) => {
    try {
      const res = await request<{ strategy: string }>('POST', `/api/v1/multiplayer/ai/start/${pid}`, {
        strategy: aiStrategy, max_actions: 30, action_delay: 0.5,
      });
      addLog(`AI 扮演 ${pid} 已启动 (${res.strategy})`);
    } catch (e: unknown) { addLog(`AI启动失败: ${e}`); }
  };

  const stopAI = async (pid: string) => {
    try {
      const res = await request<{ actions_done: number }>('POST', `/api/v1/multiplayer/ai/stop/${pid}`);
      addLog(`AI 扮演 ${pid} 已停止，执行 ${res.actions_done} 次`);
    } catch (e: unknown) { addLog(`AI停止失败: ${e}`); }
  };

  const fetchAIReport = async (pid: string) => {
    try {
      const res = await request<any>('GET', `/api/v1/multiplayer/ai/report/${pid}`);
      setAiReport(res);
      setAiPlayerId(pid);
      addLog(`AI报告: ${pid} 共${res.total_actions}次操作，置信度${res.avg_confidence}`);
    } catch (e: unknown) { addLog(`获取AI报告失败: ${e}`); }
  };

  // ── Phase2: 录制回放 ──
  const startRecording = async () => {
    try {
      await request('POST', '/api/v1/multiplayer/record/start');
      setRecording(true);
      addLog('录制开始');
    } catch (e: unknown) { addLog(`录制失败: ${e}`); }
  };

  const stopRecording = async () => {
    try {
      const res = await request<{ actions: number; duration: number }>('POST', '/api/v1/multiplayer/record/stop');
      setRecording(false);
      addLog(`录制停止: ${res.actions} 个操作, ${res.duration}s`);
    } catch (e: unknown) { addLog(`停止录制失败: ${e}`); }
  };

  const exportRecording = async () => {
    try {
      const res = await request<any>('GET', '/api/v1/multiplayer/record/export');
      const blob = new Blob([JSON.stringify(res, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = 'recording.json'; a.click();
      addLog('蓝本已导出');
    } catch (e: unknown) { addLog(`导出失败: ${e}`); }
  };

  const startReplay = async (speed: number = 1.0) => {
    try {
      const res = await request<{ total_actions: number }>('POST', '/api/v1/multiplayer/replay/start', { speed });
      addLog(`回放开始: ${res.total_actions} 个操作, ${speed}x 速度`);
    } catch (e: unknown) { addLog(`回放失败: ${e}`); }
  };

  const stopReplay = async () => {
    try {
      const res = await request<any>('POST', '/api/v1/multiplayer/replay/stop');
      setReplayStatus(res);
      addLog(`回放停止: ${res.progress}%`);
    } catch (e: unknown) { addLog(`停止回放失败: ${e}`); }
  };

  const fetchReplayStatus = async () => {
    try {
      const res = await request<any>('GET', '/api/v1/multiplayer/replay/status');
      setReplayStatus(res);
    } catch { /* ignore */ }
  };

  // ── Phase2: 一致性检查 ──
  const runConsistencyCheck = async () => {
    try {
      const res = await request<any>('POST', '/api/v1/multiplayer/consistency/check');
      setConsistencyResult(res);
      addLog(`一致性检查: ${res.consistent ? '通过' : '不一致'} | 得分 ${res.score}`);
    } catch (e: unknown) { addLog(`一致性检查失败: ${e}`); }
  };

  const fetchConsistencySummary = async () => {
    try {
      const res = await request<any>('GET', '/api/v1/multiplayer/consistency/summary');
      setConsistencySummary(res);
    } catch { /* ignore */ }
  };

  const players = status?.players ? Object.entries(status.players) : [];
  const gridCols = players.length <= 2 ? 'grid-cols-2' : 'grid-cols-2';

  return (
    <div className="p-6 space-y-4 h-full overflow-y-auto">
      {/* 标题 */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Gamepad2 className="w-5 h-5 text-amber-400" /> 多端协同测试
        </h1>
        <div className="flex items-center gap-2">
          {status?.running && (
            <span className="text-xs text-emerald-400 bg-emerald-400/10 px-2 py-1 rounded flex items-center gap-1">
              <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
              运行中 {status.elapsed.toFixed(1)}s
            </span>
          )}
          <span className="text-xs text-gray-500">
            {status?.player_count ?? 0} / 8 玩家
          </span>
        </div>
      </div>

      {/* 控制面板 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
        <div className="flex gap-2 flex-wrap">
          <button onClick={createRoom} disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-500 text-white text-xs rounded-lg transition-colors disabled:opacity-40">
            {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
            新建房间
          </button>
          <button onClick={startTest}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white text-xs rounded-lg transition-colors">
            <Play className="w-3.5 h-3.5" /> 开始测试
          </button>
          <button onClick={stopTest}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600/80 hover:bg-red-500 text-white text-xs rounded-lg transition-colors">
            <Square className="w-3.5 h-3.5" /> 停止
          </button>
          <button onClick={screenshotAll}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-cyan-600 hover:bg-cyan-500 text-white text-xs rounded-lg transition-colors">
            <Camera className="w-3.5 h-3.5" /> 全员截图
          </button>
          <button onClick={destroyRoom}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded-lg transition-colors">
            <Trash2 className="w-3.5 h-3.5" /> 销毁房间
          </button>
          <button onClick={() => { fetchStatus(); fetchTimeline(); }}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded-lg transition-colors">
            <RefreshCw className="w-3.5 h-3.5" /> 刷新
          </button>
        </div>

        {/* 添加玩家 */}
        <div className="flex gap-2 items-center">
          <input value={newPlayerId} onChange={e => setNewPlayerId(e.target.value)}
            placeholder="玩家ID (如 player1)"
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 outline-none focus:border-amber-500" />
          <select value={newPlatform} onChange={e => setNewPlatform(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white outline-none">
            {PLATFORM_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
          </select>
          <button onClick={addPlayer} disabled={!newPlayerId}
            className="flex items-center gap-1 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white text-xs rounded-lg disabled:opacity-40">
            <Users className="w-3.5 h-3.5" /> 加入
          </button>
        </div>
      </div>

      {/* 视图切换 */}
      <div className="flex gap-1 bg-gray-900 border border-gray-800 rounded-lg p-1 w-fit">
        {([
          ['grid', '网格视图'],
          ['timeline', '时序轴'],
          ['ai', 'AI 扮演'],
          ['record', '录制回放'],
          ['consistency', '一致性'],
        ] as const).map(([key, label]) => (
          <button key={key} onClick={() => setView(key)}
            className={`px-3 py-1 text-xs rounded ${view === key ? 'bg-amber-600 text-white' : 'text-gray-400 hover:text-white'}`}>
            {label}
          </button>
        ))}
      </div>

      {/* 网格视图 */}
      {view === 'grid' && (
        <div className={`grid ${gridCols} gap-3`}>
          {players.length === 0 ? (
            <div className="col-span-2 text-center py-12 text-gray-600 text-sm">
              点击「新建房间」并添加玩家开始测试
            </div>
          ) : players.map(([pid, info]) => (
            <div key={pid} className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800">
                <div className="flex items-center gap-2">
                  <Gamepad2 className="w-4 h-4 text-amber-400" />
                  <span className="text-sm font-medium text-white">{pid}</span>
                  <span className="text-xs text-gray-500">{info.platform}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs ${STATUS_COLORS[info.status] ?? 'text-gray-500'}`}>
                    {info.status}
                  </span>
                  <button onClick={() => removePlayer(pid)} className="text-gray-600 hover:text-red-400">
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
              <div className="p-3 min-h-[120px] flex items-center justify-center">
                <div className="text-center text-gray-600 text-xs">
                  <Camera className="w-8 h-8 mx-auto mb-2 opacity-30" />
                  截图: {info.screenshots} 张
                  {info.last_error && (
                    <div className="text-red-400 mt-1 text-xs">{info.last_error}</div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* 时序轴视图 */}
      {view === 'timeline' && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Clock className="w-4 h-4 text-amber-400" />
            <span className="text-sm font-medium text-white">操作时序轴</span>
            <span className="text-xs text-gray-500">{timeline.length} 个事件</span>
          </div>
          {timeline.length === 0 ? (
            <div className="text-center py-8 text-gray-600 text-sm">暂无操作记录</div>
          ) : (
            <div className="space-y-1 max-h-[300px] overflow-y-auto">
              {timeline.map((e, i) => (
                <div key={i} className="flex items-center gap-3 text-xs font-mono py-1">
                  <span className="text-gray-500 w-16 text-right">{e.offset.toFixed(2)}s</span>
                  <span className="text-amber-400 w-20">{e.player}</span>
                  <span className={e.success ? 'text-green-400' : 'text-red-400'}>
                    {e.action}
                  </span>
                  <span className="text-gray-600 flex-1 truncate">{e.detail}</span>
                  <span className="text-gray-500 w-14 text-right">{e.duration.toFixed(3)}s</span>
                  {e.success
                    ? <Zap className="w-3 h-3 text-green-500" />
                    : <span className="text-red-500 text-xs">✗</span>
                  }
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* AI 扮演视图 */}
      {view === 'ai' && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Bot className="w-4 h-4 text-violet-400" />
            <span className="text-sm font-medium text-white">AI 自动扮演</span>
          </div>
          <div className="flex gap-2 items-center">
            <span className="text-xs text-gray-400">策略:</span>
            <select value={aiStrategy} onChange={e => setAiStrategy(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded-lg px-2 py-1 text-xs text-white outline-none">
              <option value="normal">正常操作</option>
              <option value="random">随机点击</option>
              <option value="boundary">边界测试</option>
              <option value="explorer">探索模式</option>
            </select>
          </div>
          {players.length === 0 ? (
            <div className="text-center py-6 text-gray-600 text-sm">请先添加玩家</div>
          ) : (
            <div className="space-y-2">
              {players.map(([pid]) => (
                <div key={pid} className="flex items-center justify-between bg-gray-800/50 rounded-lg px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Bot className="w-3.5 h-3.5 text-violet-400" />
                    <span className="text-sm text-white">{pid}</span>
                  </div>
                  <div className="flex gap-1.5">
                    <button onClick={() => startAI(pid)}
                      className="px-2 py-1 bg-violet-600 hover:bg-violet-500 text-white text-xs rounded transition-colors">
                      启动AI
                    </button>
                    <button onClick={() => stopAI(pid)}
                      className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded transition-colors">
                      停止
                    </button>
                    <button onClick={() => fetchAIReport(pid)}
                      className="px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded transition-colors">
                      报告
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          {aiReport && aiPlayerId && (
            <div className="bg-gray-800/50 rounded-lg p-3 space-y-2">
              <div className="text-xs text-gray-400">AI 报告: <span className="text-amber-400">{aiPlayerId}</span></div>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-lg font-bold text-white">{aiReport.total_actions}</div>
                  <div className="text-xs text-gray-500">总操作</div>
                </div>
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-lg font-bold text-violet-400">{aiReport.strategy}</div>
                  <div className="text-xs text-gray-500">策略</div>
                </div>
                <div className="bg-gray-800 rounded p-2">
                  <div className="text-lg font-bold text-amber-400">{aiReport.avg_confidence}</div>
                  <div className="text-xs text-gray-500">置信度</div>
                </div>
              </div>
              {aiReport.history?.length > 0 && (
                <div className="max-h-32 overflow-y-auto space-y-0.5">
                  {aiReport.history.map((h: any, i: number) => (
                    <div key={i} className="text-xs font-mono text-gray-500">
                      <span className="text-violet-400">{h.action}</span> {h.reason}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* 录制回放视图 */}
      {view === 'record' && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">
          <div className="flex items-center gap-2 mb-2">
            <Circle className="w-4 h-4 text-red-400" />
            <span className="text-sm font-medium text-white">录制与回放</span>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-gray-800/50 rounded-lg p-3 space-y-2">
              <div className="text-xs text-gray-400 font-medium">录制</div>
              <div className="flex gap-1.5">
                <button onClick={startRecording} disabled={recording}
                  className="flex items-center gap-1 px-2 py-1 bg-red-600 hover:bg-red-500 text-white text-xs rounded disabled:opacity-40">
                  <Circle className="w-3 h-3" /> {recording ? '录制中...' : '开始录制'}
                </button>
                <button onClick={stopRecording} disabled={!recording}
                  className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded disabled:opacity-40">
                  <CircleStop className="w-3 h-3" /> 停止
                </button>
                <button onClick={exportRecording}
                  className="flex items-center gap-1 px-2 py-1 bg-cyan-600 hover:bg-cyan-500 text-white text-xs rounded">
                  <Download className="w-3 h-3" /> 导出蓝本
                </button>
              </div>
              {recording && (
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 bg-red-500 rounded-full animate-pulse" />
                  <span className="text-xs text-red-400">正在录制操作...</span>
                </div>
              )}
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3 space-y-2">
              <div className="text-xs text-gray-400 font-medium">回放</div>
              <div className="flex gap-1.5">
                <button onClick={() => startReplay(1.0)}
                  className="flex items-center gap-1 px-2 py-1 bg-green-600 hover:bg-green-500 text-white text-xs rounded">
                  <Play className="w-3 h-3" /> 1x
                </button>
                <button onClick={() => startReplay(2.0)}
                  className="flex items-center gap-1 px-2 py-1 bg-green-600 hover:bg-green-500 text-white text-xs rounded">
                  <Play className="w-3 h-3" /> 2x
                </button>
                <button onClick={() => startReplay(4.0)}
                  className="flex items-center gap-1 px-2 py-1 bg-green-600 hover:bg-green-500 text-white text-xs rounded">
                  <Play className="w-3 h-3" /> 4x
                </button>
                <button onClick={stopReplay}
                  className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded">
                  <Square className="w-3 h-3" /> 停止
                </button>
                <button onClick={fetchReplayStatus}
                  className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded">
                  <RefreshCw className="w-3 h-3" />
                </button>
              </div>
              {replayStatus && (
                <div className="space-y-1">
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>{replayStatus.replaying ? '回放中' : '已停止'}</span>
                    <span>{replayStatus.current}/{replayStatus.total} ({replayStatus.progress}%)</span>
                  </div>
                  <div className="w-full bg-gray-700 rounded-full h-1.5">
                    <div className="bg-green-500 h-1.5 rounded-full transition-all"
                      style={{ width: `${replayStatus.progress}%` }} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 一致性检查视图 */}
      {view === 'consistency' && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-emerald-400" />
              <span className="text-sm font-medium text-white">跨端一致性检查</span>
            </div>
            <div className="flex gap-1.5">
              <button onClick={runConsistencyCheck}
                className="flex items-center gap-1 px-2 py-1 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded">
                <CheckCircle2 className="w-3 h-3" /> 执行检查
              </button>
              <button onClick={fetchConsistencySummary}
                className="flex items-center gap-1 px-2 py-1 bg-gray-700 hover:bg-gray-600 text-white text-xs rounded">
                <Gauge className="w-3 h-3" /> 历史摘要
              </button>
            </div>
          </div>
          {consistencyResult && (
            <div className={`rounded-lg p-4 border ${consistencyResult.consistent ? 'border-emerald-700 bg-emerald-900/20' : 'border-red-700 bg-red-900/20'}`}>
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  {consistencyResult.consistent
                    ? <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    : <AlertTriangle className="w-5 h-5 text-red-400" />
                  }
                  <span className={`text-sm font-medium ${consistencyResult.consistent ? 'text-emerald-400' : 'text-red-400'}`}>
                    {consistencyResult.consistent ? '所有端一致' : '发现不一致'}
                  </span>
                </div>
                <div className="text-right">
                  <div className={`text-2xl font-bold ${consistencyResult.score >= 80 ? 'text-emerald-400' : consistencyResult.score >= 50 ? 'text-amber-400' : 'text-red-400'}`}>
                    {consistencyResult.score}
                  </div>
                  <div className="text-xs text-gray-500">一致性得分</div>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="bg-gray-800/50 rounded p-2">
                  <div className="text-white font-medium">{consistencyResult.player_count}</div>
                  <div className="text-gray-500">检查端数</div>
                </div>
                <div className="bg-gray-800/50 rounded p-2">
                  <div className="text-white font-medium">{consistencyResult.diff_count}</div>
                  <div className="text-gray-500">差异数</div>
                </div>
                <div className="bg-gray-800/50 rounded p-2">
                  <div className="text-white font-medium">{consistencyResult.captures?.length ?? 0}</div>
                  <div className="text-gray-500">截图数</div>
                </div>
              </div>
              {consistencyResult.diffs?.length > 0 && (
                <div className="mt-3 space-y-1">
                  <div className="text-xs text-gray-400 font-medium">差异详情:</div>
                  {consistencyResult.diffs.map((d: any, i: number) => (
                    <div key={i} className="flex items-center gap-2 text-xs bg-gray-800/50 rounded px-2 py-1">
                      <span className={d.severity === 'critical' ? 'text-red-400' : 'text-amber-400'}>
                        {d.severity}
                      </span>
                      <span className="text-gray-400">{d.player_a} vs {d.player_b}</span>
                      <span className="text-gray-500 truncate">{d.field}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {consistencySummary && (
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-xs text-gray-400 mb-2">历史检查摘要</div>
              <div className="grid grid-cols-4 gap-2 text-center text-xs">
                <div><span className="text-white font-medium">{consistencySummary.total_checks}</span><div className="text-gray-500">总检查</div></div>
                <div><span className="text-emerald-400 font-medium">{consistencySummary.consistent_count}</span><div className="text-gray-500">通过</div></div>
                <div><span className="text-red-400 font-medium">{consistencySummary.inconsistent_count}</span><div className="text-gray-500">不一致</div></div>
                <div><span className="text-amber-400 font-medium">{consistencySummary.avg_score}</span><div className="text-gray-500">平均分</div></div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 日志 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-2 border-b border-gray-800 text-xs text-gray-500 font-medium">操作日志</div>
        <div className="p-3 max-h-36 overflow-y-auto">
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
