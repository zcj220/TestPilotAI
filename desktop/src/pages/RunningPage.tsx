/**
 * 实时测试面板
 *
 * 显示 WebSocket 实时日志、进度条和测试结果概览。
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Activity, Bug, CheckCircle, Wrench, Clock, Coins, Monitor, Pause, Play, Square, SkipForward, Gauge, Terminal } from 'lucide-react';
import { onProgress, connectWs, sendWsControl, controlTest, getTestStatus, type WsMessage, type TestReportResponse, type TestStatus } from '../lib/engineClient';

interface LiveScreenshot {
  available: boolean;
  timestamp?: number;
  image_base64?: string;
  message?: string;
}

interface LogEntry {
  time: string;
  type: string;
  message: string;
  level: 'info' | 'success' | 'warn' | 'error';
}

interface TermLogEntry {
  timestamp: number;
  level: 'stdout' | 'stderr' | 'system';
  content: string;
}

const levelColors: Record<string, string> = {
  info: 'text-gray-400',
  success: 'text-emerald-400',
  warn: 'text-amber-400',
  error: 'text-red-400',
};

const typeToLevel: Record<string, LogEntry['level']> = {
  step_start: 'info',
  step_done: 'success',
  bug_found: 'warn',
  repair_start: 'info',
  repair_done: 'success',
  test_done: 'success',
  error: 'error',
  log: 'info',
};

const DELAY_OPTIONS = [
  { label: '实时', value: 0 },
  { label: '0.5s', value: 0.5 },
  { label: '1s', value: 1 },
  { label: '3s', value: 3 },
];

export default function RunningPage() {
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [termLogs, setTermLogs] = useState<TermLogEntry[]>([]);
  const [logTab, setLogTab] = useState<'test' | 'terminal'>('test');
  const [report, setReport] = useState<TestReportResponse | null>(null);
  const [screenshot, setScreenshot] = useState<LiveScreenshot | null>(null);
  const [testState, setTestState] = useState<TestStatus | null>(null);
  const [stepDelay, setStepDelay] = useState(0);
  const logEndRef = useRef<HTMLDivElement>(null);
  const termEndRef = useRef<HTMLDivElement>(null);

  // 从 sessionStorage 读取最新报告
  useEffect(() => {
    const raw = sessionStorage.getItem('latest-report');
    if (raw) {
      try { setReport(JSON.parse(raw)); } catch { /* 忽略 */ }
    }
  }, []);

  // 初始获取测试状态
  useEffect(() => {
    getTestStatus().then(setTestState).catch(() => {});
  }, []);

  // 监听 WebSocket 进度
  useEffect(() => {
    connectWs();
    const unsub = onProgress((msg: WsMessage) => {
      // v2.0：截图推送
      if (msg.type === 'screenshot') {
        setScreenshot({
          available: true,
          image_base64: msg.data.image_base64 as string,
        });
        return;
      }

      // v2.0：状态变化
      if (msg.type === 'state_change') {
        setTestState(msg.data as unknown as TestStatus);
        return;
      }

      // v2.0：终端日志
      if (msg.type === 'terminal_log') {
        setTermLogs((prev) => {
          const next = [...prev, msg.data as unknown as TermLogEntry];
          return next.length > 500 ? next.slice(-500) : next;
        });
        return;
      }

      const now = new Date().toLocaleTimeString('zh-CN', { hour12: false });
      const text = typeof msg.data?.message === 'string'
        ? msg.data.message as string
        : msg.type;
      const entry: LogEntry = {
        time: now,
        type: msg.type,
        message: text,
        level: typeToLevel[msg.type] || 'info',
      };
      setLogs((prev) => [...prev, entry]);

      // 如果是 test_done，尝试更新报告
      if (msg.type === 'test_done') {
        const raw = sessionStorage.getItem('latest-report');
        if (raw) {
          try { setReport(JSON.parse(raw)); } catch { /* 忽略 */ }
        }
      }
    });
    return unsub;
  }, []);

  // 实时截图轮询（降级方案：WebSocket截图推送不可用时回退）
  useEffect(() => {
    const fetchScreenshot = async () => {
      try {
        const resp = await fetch('/api/v1/live/screenshot');
        if (resp.ok) {
          const data = await resp.json();
          setScreenshot(data);
        }
      } catch { /* 引擎未启动 */ }
    };
    fetchScreenshot();
    const timer = setInterval(fetchScreenshot, 5000);
    return () => clearInterval(timer);
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // v2.0：控制操作
  const handleControl = useCallback(async (action: string) => {
    try {
      const resp = await controlTest(action, action === 'set_delay' ? stepDelay : undefined);
      setTestState((prev) => prev ? { ...prev, state: resp.state as TestStatus['state'] } : prev);
    } catch (err) {
      console.error('控制命令失败:', err);
    }
  }, [stepDelay]);

  const handleDelayChange = useCallback((val: number) => {
    setStepDelay(val);
    sendWsControl('set_delay', { seconds: val });
  }, []);

  const isRunning = testState?.state === 'running';
  const isPaused = testState?.state === 'paused';
  const isActive = isRunning || isPaused;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Activity className="w-5 h-5 text-indigo-400" />
          测试面板
        </h1>
        {/* v2.0：状态指示器 */}
        {testState && (
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
              testState.state === 'running' ? 'bg-emerald-500/20 text-emerald-400' :
              testState.state === 'paused' ? 'bg-amber-500/20 text-amber-400' :
              testState.state === 'stopped' ? 'bg-red-500/20 text-red-400' :
              'bg-gray-500/20 text-gray-400'
            }`}>
              <span className={`w-2 h-2 rounded-full ${
                testState.state === 'running' ? 'bg-emerald-400 animate-pulse' :
                testState.state === 'paused' ? 'bg-amber-400' :
                testState.state === 'stopped' ? 'bg-red-400' :
                'bg-gray-400'
              }`} />
              {testState.state === 'running' ? '运行中' :
               testState.state === 'paused' ? '已暂停' :
               testState.state === 'stopped' ? '已停止' : '空闲'}
            </span>
            {isActive && testState.total_steps > 0 && (
              <span className="text-xs text-gray-400">
                {testState.current_step}/{testState.total_steps}
              </span>
            )}
          </div>
        )}
      </div>

      {/* v2.0：控制面板 */}
      {isActive && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-3 flex-wrap">
            {/* 暂停/继续 */}
            {isRunning ? (
              <button
                onClick={() => handleControl('pause')}
                className="flex items-center gap-1.5 px-3 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Pause className="w-4 h-4" /> 暂停
              </button>
            ) : (
              <button
                onClick={() => handleControl('resume')}
                className="flex items-center gap-1.5 px-3 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-medium rounded-lg transition-colors"
              >
                <Play className="w-4 h-4" /> 继续
              </button>
            )}

            {/* 停止 */}
            <button
              onClick={() => handleControl('stop')}
              className="flex items-center gap-1.5 px-3 py-2 bg-red-600 hover:bg-red-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Square className="w-4 h-4" /> 停止
            </button>

            {/* 单步模式 */}
            <button
              onClick={() => handleControl(testState?.step_mode ? 'step_mode_off' : 'step_mode_on')}
              className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                testState?.step_mode
                  ? 'bg-indigo-600 hover:bg-indigo-500 text-white'
                  : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              <SkipForward className="w-4 h-4" />
              {testState?.step_mode ? '单步:开' : '单步:关'}
            </button>

            {/* 分隔线 */}
            <div className="w-px h-8 bg-gray-700" />

            {/* 观看速度 */}
            <div className="flex items-center gap-2">
              <Gauge className="w-4 h-4 text-gray-400" />
              <span className="text-xs text-gray-400">速度:</span>
              {DELAY_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  onClick={() => handleDelayChange(opt.value)}
                  className={`px-2 py-1 text-xs rounded transition-colors ${
                    stepDelay === opt.value
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-700 text-gray-400 hover:bg-gray-600'
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>

            {/* 当前步骤描述 */}
            {testState?.description && (
              <>
                <div className="w-px h-8 bg-gray-700" />
                <span className="text-xs text-gray-400 truncate max-w-xs">
                  {testState.description}
                </span>
              </>
            )}
          </div>

          {/* 进度条 */}
          {testState && testState.total_steps > 0 && (
            <div className="mt-3">
              <div className="w-full bg-gray-800 rounded-full h-1.5">
                <div
                  className={`h-1.5 rounded-full transition-all duration-300 ${
                    isPaused ? 'bg-amber-500' : 'bg-indigo-500'
                  }`}
                  style={{ width: `${(testState.current_step / testState.total_steps) * 100}%` }}
                />
              </div>
            </div>
          )}
        </div>
      )}

      {/* 结果概览卡片 */}
      {report && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            icon={<CheckCircle className="w-5 h-5 text-emerald-400" />}
            label="通过率"
            value={`${(report.pass_rate * 100).toFixed(0)}%`}
            color={report.pass_rate >= 0.8 ? 'text-emerald-400' : 'text-red-400'}
          />
          <StatCard
            icon={<Activity className="w-5 h-5 text-blue-400" />}
            label="步骤"
            value={`${report.passed_steps}/${report.total_steps}`}
            color="text-blue-400"
          />
          <StatCard
            icon={<Bug className="w-5 h-5 text-amber-400" />}
            label="Bug"
            value={String(report.bug_count)}
            color={report.bug_count === 0 ? 'text-emerald-400' : 'text-amber-400'}
          />
          <StatCard
            icon={<Clock className="w-5 h-5 text-gray-400" />}
            label="耗时"
            value={`${report.duration_seconds.toFixed(1)}s`}
            color="text-gray-300"
          />
          {report.fixed_bug_count != null && (
            <StatCard
              icon={<Wrench className="w-5 h-5 text-indigo-400" />}
              label="自动修复"
              value={`${report.fixed_bug_count} 个`}
              color="text-indigo-400"
            />
          )}
          {report.credits_used != null && (
            <StatCard
              icon={<Coins className="w-5 h-5 text-yellow-400" />}
              label="积分消耗"
              value={`${report.credits_used}`}
              color="text-yellow-400"
            />
          )}
        </div>
      )}

      {/* 实时观看 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 flex items-center gap-2">
          <Monitor className="w-4 h-4 text-indigo-400" />
          <span className="text-sm font-medium text-gray-300">实时画面</span>
          <span className="text-xs text-gray-500 ml-auto">实时推送</span>
        </div>
        <div className="p-4 flex items-center justify-center min-h-48">
          {screenshot?.available && screenshot.image_base64 ? (
            <img
              src={`data:image/png;base64,${screenshot.image_base64}`}
              alt="浏览器实时截图"
              className="max-w-full max-h-72 rounded-lg border border-gray-700"
            />
          ) : (
            <div className="text-center text-gray-500">
              <Monitor className="w-10 h-10 mx-auto mb-2 opacity-30" />
              <p className="text-sm">等待测试启动后显示实时画面</p>
              <p className="text-xs mt-1">后续版本将集成 VNC 实时直播</p>
            </div>
          )}
        </div>
      </div>

      {/* 日志面板（双Tab） */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center gap-1">
            <button
              onClick={() => setLogTab('test')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                logTab === 'test'
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`}
            >
              <Activity className="w-3.5 h-3.5" />
              测试日志
              {logs.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-black/30 rounded text-[10px]">{logs.length}</span>
              )}
            </button>
            <button
              onClick={() => setLogTab('terminal')}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                logTab === 'terminal'
                  ? 'bg-indigo-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              }`}
            >
              <Terminal className="w-3.5 h-3.5" />
              应用终端
              {termLogs.length > 0 && (
                <span className="ml-1 px-1.5 py-0.5 bg-black/30 rounded text-[10px]">{termLogs.length}</span>
              )}
            </button>
          </div>
        </div>
        <div className="h-96 overflow-y-auto p-4 font-mono text-xs space-y-0.5">
          {logTab === 'test' ? (
            <>
              {logs.length === 0 ? (
                <p className="text-gray-500">等待测试开始...</p>
              ) : (
                logs.map((entry, i) => (
                  <div key={i} className={`${levelColors[entry.level]}`}>
                    <span className="text-gray-600">[{entry.time}]</span>{' '}
                    {entry.message}
                  </div>
                ))
              )}
              <div ref={logEndRef} />
            </>
          ) : (
            <>
              {termLogs.length === 0 ? (
                <p className="text-gray-500">应用终端日志为空（使用 testpilot run 启动应用后显示）</p>
              ) : (
                termLogs.map((entry, i) => (
                  <div key={i} className={
                    entry.level === 'stderr' ? 'text-red-400' :
                    entry.level === 'system' ? 'text-yellow-400' :
                    'text-gray-300'
                  }>
                    <span className="text-gray-600">
                      [{new Date(entry.timestamp * 1000).toLocaleTimeString('zh-CN', { hour12: false })}]
                    </span>{' '}
                    {entry.content}
                  </div>
                ))
              )}
              <div ref={termEndRef} />
            </>
          )}
        </div>
      </div>

      {/* Markdown 报告预览 */}
      {report?.report_markdown && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-gray-800">
            <span className="text-sm font-medium text-gray-300">测试报告</span>
          </div>
          <pre className="p-4 text-xs text-gray-300 overflow-auto max-h-80 whitespace-pre-wrap">
            {report.report_markdown}
          </pre>
        </div>
      )}
    </div>
  );
}

function StatCard({
  icon, label, value, color,
}: {
  icon: React.ReactNode; label: string; value: string; color: string;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-xs text-gray-400">{label}</span>
      </div>
      <p className={`text-2xl font-bold ${color}`}>{value}</p>
    </div>
  );
}
