/**
 * 测试配置页（首页）
 * v5.0: 新增手机测试Tab
 */

import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Play, Loader2, Globe, FileText, Target, FolderOpen, Smartphone, Monitor, Camera, Unplug, Plug, RefreshCw, Scan } from 'lucide-react';
import {
  startTest, loadSettings, type TestReportResponse,
  getMobileDevices, getAppiumStatus, createMobileSession, closeMobileSession,
  mobileScreenshot, mobileAnalyze,
  type MobileDevice, type MobileSession,
} from '../lib/engineClient';

const focusOptions = [
  '核心功能',
  '用户注册登录',
  '表单验证',
  '页面导航',
  '数据展示',
];

export default function TestPage() {
  const navigate = useNavigate();
  const [tab, setTab] = useState<'web' | 'mobile'>('web');

  // ── Web测试状态 ──
  const [url, setUrl] = useState('');
  const [description, setDescription] = useState('');
  const [focus, setFocus] = useState('核心功能');
  const [autoRepair, setAutoRepair] = useState(false);
  const [projectPath, setProjectPath] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // ── 手机测试状态 ──
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [selectedSerial, setSelectedSerial] = useState('');
  const [appiumOk, setAppiumOk] = useState<boolean | null>(null);
  const [session, setSession] = useState<MobileSession | null>(null);
  const [sessionLoading, setSessionLoading] = useState(false);
  const [mobileError, setMobileError] = useState('');
  const [screenshotB64, setScreenshotB64] = useState('');
  const [screenshotLoading, setScreenshotLoading] = useState(false);
  const [analyzeResult, setAnalyzeResult] = useState('');
  const [analyzeLoading, setAnalyzeLoading] = useState(false);

  // 切到手机Tab时自动刷新设备列表
  useEffect(() => {
    if (tab === 'mobile') { refreshDevices(); checkAppium(); }
  }, [tab]);

  const refreshDevices = async () => {
    setDevicesLoading(true);
    try {
      const res = await getMobileDevices();
      setDevices(res.devices);
      if (res.devices.length > 0 && !selectedSerial) {
        setSelectedSerial(res.devices[0].serial);
      }
      if (res.error) setMobileError(res.error);
    } catch (e: unknown) {
      setMobileError(e instanceof Error ? e.message : String(e));
    } finally {
      setDevicesLoading(false);
    }
  };

  const checkAppium = async () => {
    try {
      const res = await getAppiumStatus();
      setAppiumOk(res.running);
    } catch { setAppiumOk(false); }
  };

  const handleConnect = async () => {
    if (!selectedSerial) return;
    setSessionLoading(true); setMobileError('');
    try {
      const s = await createMobileSession({ device_name: selectedSerial });
      setSession(s);
    } catch (e: unknown) {
      setMobileError(e instanceof Error ? e.message : String(e));
    } finally {
      setSessionLoading(false);
    }
  };

  const handleDisconnect = async () => {
    if (!session) return;
    try {
      await closeMobileSession(session.session_id);
    } catch { /* ignore */ }
    setSession(null); setScreenshotB64(''); setAnalyzeResult('');
  };

  const handleMobileScreenshot = async () => {
    if (!session) return;
    setScreenshotLoading(true);
    try {
      const res = await mobileScreenshot(session.session_id);
      setScreenshotB64(res.image_base64);
    } catch (e: unknown) {
      setMobileError(e instanceof Error ? e.message : String(e));
    } finally {
      setScreenshotLoading(false);
    }
  };

  const handleMobileAnalyze = async () => {
    if (!session) return;
    setAnalyzeLoading(true); setAnalyzeResult('');
    try {
      const res = await mobileAnalyze(session.session_id);
      setScreenshotB64(res.screenshot_base64);
      setAnalyzeResult(res.analysis);
    } catch (e: unknown) {
      setMobileError(e instanceof Error ? e.message : String(e));
    } finally {
      setAnalyzeLoading(false);
    }
  };

  const handleStart = async () => {
    if (!url.trim()) {
      setError('请输入被测应用 URL');
      return;
    }
    setError('');
    setLoading(true);

    const settings = loadSettings();

    try {
      const report: TestReportResponse = await startTest({
        url: url.trim(),
        description,
        focus,
        reasoning_effort: settings.reasoningEffort,
        auto_repair: autoRepair,
        project_path: projectPath,
      });

      // 存储最新报告，跳转到测试面板
      sessionStorage.setItem('latest-report', JSON.stringify(report));
      navigate('/running');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen p-8">
      <div className="w-full max-w-lg space-y-6">
        {/* 标题 */}
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-bold text-white">开始新测试</h1>
          <p className="text-sm text-gray-400">
            AI 将像人类一样操作你的应用，自动发现并修复 Bug
          </p>
        </div>

        {/* Tab切换: Web / 手机 */}
        <div className="flex gap-1 bg-gray-800/50 rounded-lg p-1">
          <button
            onClick={() => setTab('web')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === 'web' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Monitor className="w-4 h-4" />
            Web 测试
          </button>
          <button
            onClick={() => setTab('mobile')}
            className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-md text-sm font-medium transition-colors ${
              tab === 'mobile' ? 'bg-indigo-600 text-white' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Smartphone className="w-4 h-4" />
            手机测试
          </button>
        </div>

        {/* ── Web测试表单 ── */}
        {tab === 'web' && (
        <div className="space-y-4 bg-gray-900 border border-gray-800 rounded-xl p-6">
          {/* URL */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
              <Globe className="w-4 h-4 text-indigo-400" />
              被测应用 URL
            </label>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="http://localhost:3000"
              className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500"
            />
          </div>

          {/* 描述 */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
              <FileText className="w-4 h-4 text-indigo-400" />
              应用描述
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="电商网站、管理后台、博客系统..."
              className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500"
            />
          </div>

          {/* 测试重点 */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
              <Target className="w-4 h-4 text-indigo-400" />
              测试重点
            </label>
            <select
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500"
            >
              {focusOptions.map((opt) => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          </div>

          {/* 自动修复 */}
          <div className="flex items-center gap-3 py-1">
            <input
              type="checkbox"
              id="autoRepair"
              checked={autoRepair}
              onChange={(e) => setAutoRepair(e.target.checked)}
              className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-indigo-500 focus:ring-indigo-500"
            />
            <label htmlFor="autoRepair" className="text-sm text-gray-300">
              发现 Bug 后自动修复（v0.4）
            </label>
          </div>

          {/* 项目路径（自动修复时显示） */}
          {autoRepair && (
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
                <FolderOpen className="w-4 h-4 text-indigo-400" />
                项目根目录
              </label>
              <input
                type="text"
                value={projectPath}
                onChange={(e) => setProjectPath(e.target.value)}
                placeholder="D:\projects\my-app"
                className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500"
              />
            </div>
          )}

          {/* 错误提示 */}
          {error && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
              {error}
            </div>
          )}

          {/* 开始按钮 */}
          <button
            onClick={handleStart}
            disabled={loading}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                测试执行中...
              </>
            ) : (
              <>
                <Play className="w-4 h-4" />
                开始测试
              </>
            )}
          </button>
        </div>
        )}

        {/* ── 手机测试面板 ── */}
        {tab === 'mobile' && (
        <div className="space-y-4 bg-gray-900 border border-gray-800 rounded-xl p-6">
          {/* Appium状态 */}
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-400">Appium Server</span>
            <span className={`text-xs px-2 py-0.5 rounded-full ${appiumOk ? 'bg-emerald-400/10 text-emerald-400' : 'bg-red-400/10 text-red-400'}`}>
              {appiumOk === null ? '检测中...' : appiumOk ? '运行中' : '未启动'}
            </span>
          </div>

          {/* 设备列表 */}
          <div>
            <label className="flex items-center gap-2 text-sm font-medium text-gray-300 mb-1.5">
              <Smartphone className="w-4 h-4 text-indigo-400" />
              选择设备
              <button onClick={refreshDevices} disabled={devicesLoading} className="ml-auto text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
                <RefreshCw className={`w-3 h-3 ${devicesLoading ? 'animate-spin' : ''}`} />
                刷新
              </button>
            </label>
            {devices.length === 0 ? (
              <div className="text-sm text-gray-500 bg-gray-800 rounded-lg px-3 py-2.5">
                {devicesLoading ? '扫描设备中...' : '未检测到设备。请用USB连接手机并开启USB调试。'}
              </div>
            ) : (
              <select
                value={selectedSerial}
                onChange={(e) => setSelectedSerial(e.target.value)}
                className="w-full px-3 py-2.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              >
                {devices.map((d) => (
                  <option key={d.serial} value={d.serial}>
                    {d.serial}{d.model ? ` (${d.model})` : ''}
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* 连接/断开 */}
          {!session ? (
            <button
              onClick={handleConnect}
              disabled={sessionLoading || devices.length === 0 || !appiumOk}
              className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-colors"
            >
              {sessionLoading ? (
                <><Loader2 className="w-4 h-4 animate-spin" />连接中...</>
              ) : (
                <><Plug className="w-4 h-4" />连接设备</>
              )}
            </button>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between bg-emerald-400/10 border border-emerald-400/20 rounded-lg px-3 py-2">
                <span className="text-sm text-emerald-400">已连接: {session.session_id}</span>
                <button onClick={handleDisconnect} className="text-xs text-red-400 hover:text-red-300 flex items-center gap-1">
                  <Unplug className="w-3 h-3" />断开
                </button>
              </div>

              {/* 操作按钮 */}
              <div className="flex gap-2">
                <button
                  onClick={handleMobileScreenshot}
                  disabled={screenshotLoading}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-gray-700 hover:bg-gray-600 disabled:opacity-50 text-sm text-white rounded-lg transition-colors"
                >
                  {screenshotLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5" />}
                  截图
                </button>
                <button
                  onClick={handleMobileAnalyze}
                  disabled={analyzeLoading}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-sm text-white rounded-lg transition-colors"
                >
                  {analyzeLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Scan className="w-3.5 h-3.5" />}
                  AI分析
                </button>
              </div>

              {/* 截图预览 */}
              {screenshotB64 && (
                <div className="rounded-lg overflow-hidden border border-gray-700">
                  <img
                    src={`data:image/png;base64,${screenshotB64}`}
                    alt="手机截图"
                    className="w-full h-auto max-h-80 object-contain bg-black"
                  />
                </div>
              )}

              {/* AI分析结果 */}
              {analyzeResult && (
                <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
                  <h3 className="text-xs font-semibold text-indigo-400 mb-1">AI 分析结果</h3>
                  <p className="text-sm text-gray-300 whitespace-pre-wrap">{analyzeResult}</p>
                </div>
              )}
            </div>
          )}

          {/* 错误提示 */}
          {mobileError && (
            <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
              {mobileError}
            </div>
          )}
        </div>
        )}
      </div>
    </div>
  );
}
