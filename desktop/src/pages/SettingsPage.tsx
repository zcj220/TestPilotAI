/**
 * 设置页
 *
 * 配置引擎地址、WebSocket 地址、AI 思考深度、自动修复开关。
 */

import { useState, useEffect } from 'react';
import { Settings, Save, CheckCircle, Server, Wifi, BrainCircuit, Wrench, Smartphone, RefreshCw } from 'lucide-react';
import {
  loadSettings, saveSettings, checkHealth, type AppSettings, type HealthResponse,
  getMobileDevices, getAppiumStatus, type MobileDevice,
} from '../lib/engineClient';

const reasoningOptions = [
  { value: 'minimal', label: '极简' },
  { value: 'low', label: '低' },
  { value: 'medium', label: '中等' },
  { value: 'high', label: '深度' },
];

export default function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings>(loadSettings());
  const [saved, setSaved] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState('');
  const [checking, setChecking] = useState(false);

  // 手机设备状态
  const [devices, setDevices] = useState<MobileDevice[]>([]);
  const [devicesLoading, setDevicesLoading] = useState(false);
  const [appiumOk, setAppiumOk] = useState<boolean | null>(null);
  const [appiumMsg, setAppiumMsg] = useState('');

  const refreshMobile = async () => {
    setDevicesLoading(true);
    try {
      const [devRes, appRes] = await Promise.all([getMobileDevices(), getAppiumStatus()]);
      setDevices(devRes.devices);
      setAppiumOk(appRes.running);
      setAppiumMsg(appRes.message);
    } catch { /* ignore */ }
    finally { setDevicesLoading(false); }
  };

  const handleSave = () => {
    saveSettings(settings);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleCheck = async () => {
    setChecking(true);
    setHealthError('');
    setHealth(null);
    try {
      const h = await checkHealth();
      setHealth(h);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setHealthError(msg);
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    handleCheck();
    refreshMobile();
  }, []);

  const update = (key: keyof AppSettings, value: string | boolean) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="p-6 max-w-2xl space-y-6">
      <h1 className="text-xl font-bold text-white flex items-center gap-2">
        <Settings className="w-5 h-5 text-indigo-400" />
        设置
      </h1>

      {/* 引擎连接状态 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Server className="w-4 h-4 text-indigo-400" />
          引擎连接
        </h2>

        {health && (
          <div className="flex items-center gap-2 text-sm text-emerald-400 bg-emerald-400/10 border border-emerald-400/20 rounded-lg px-3 py-2">
            <CheckCircle className="w-4 h-4" />
            已连接 | v{health.version} | 沙箱={health.sandbox_count} | 浏览器={health.browser_ready ? '就绪' : '未启动'}
          </div>
        )}

        {healthError && (
          <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-3 py-2">
            连接失败: {healthError}
          </div>
        )}

        <div>
          <label className="text-xs text-gray-400 mb-1 block">引擎 HTTP 地址</label>
          <input
            type="text"
            value={settings.engineUrl}
            onChange={(e) => update('engineUrl', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
        </div>

        <div>
          <label className="text-xs text-gray-400 mb-1 block flex items-center gap-1">
            <Wifi className="w-3 h-3" />
            WebSocket 地址
          </label>
          <input
            type="text"
            value={settings.wsUrl}
            onChange={(e) => update('wsUrl', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          />
        </div>

        <button
          onClick={handleCheck}
          disabled={checking}
          className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          {checking ? '检测中...' : '重新检测连接'}
        </button>
      </div>

      {/* AI 配置 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <BrainCircuit className="w-4 h-4 text-indigo-400" />
          AI 配置
        </h2>

        <div>
          <label className="text-xs text-gray-400 mb-1 block">思考深度</label>
          <select
            value={settings.reasoningEffort}
            onChange={(e) => update('reasoningEffort', e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
          >
            {reasoningOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">越深度越准确，但耗时更长</p>
        </div>

        <div className="flex items-center gap-3">
          <input
            type="checkbox"
            id="settingsAutoRepair"
            checked={settings.autoRepair}
            onChange={(e) => update('autoRepair', e.target.checked)}
            className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-indigo-500"
          />
          <label htmlFor="settingsAutoRepair" className="text-sm text-gray-300 flex items-center gap-1">
            <Wrench className="w-3.5 h-3.5" />
            默认开启自动修复
          </label>
        </div>
      </div>

      {/* 手机测试环境 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h2 className="text-sm font-semibold text-gray-300 flex items-center gap-2">
          <Smartphone className="w-4 h-4 text-indigo-400" />
          手机测试环境
          <button onClick={refreshMobile} disabled={devicesLoading} className="ml-auto text-xs text-indigo-400 hover:text-indigo-300 flex items-center gap-1">
            <RefreshCw className={`w-3 h-3 ${devicesLoading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </h2>

        {/* Appium状态 */}
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-400">Appium Server</span>
          <span className={`text-xs px-2 py-0.5 rounded-full ${appiumOk ? 'bg-emerald-400/10 text-emerald-400' : 'bg-red-400/10 text-red-400'}`}>
            {appiumOk === null ? '检测中...' : appiumOk ? '✅ 运行中' : '❌ 未启动'}
          </span>
        </div>
        {!appiumOk && appiumMsg && (
          <p className="text-xs text-gray-500">{appiumMsg}</p>
        )}

        {/* 设备列表 */}
        {devices.length === 0 ? (
          <div className="text-xs text-gray-500 bg-gray-800 rounded-lg px-3 py-2">
            未检测到手机设备。请用USB连接手机并开启USB调试。
          </div>
        ) : (
          <div className="space-y-1.5">
            {devices.map((d) => (
              <div key={d.serial} className="flex items-center gap-2 text-xs bg-gray-800 rounded-lg px-3 py-2">
                <Smartphone className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-white font-mono">{d.serial}</span>
                {d.model && <span className="text-gray-400">({d.model})</span>}
                <span className="ml-auto text-emerald-400">{d.status}</span>
              </div>
            ))}
          </div>
        )}

        <p className="text-xs text-gray-500">
          安装: <code className="text-gray-400">npm install -g appium && appium driver install uiautomator2</code>
        </p>
      </div>

      {/* 保存按钮 */}
      <button
        onClick={handleSave}
        className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition-colors"
      >
        {saved ? (
          <>
            <CheckCircle className="w-4 h-4" />
            已保存
          </>
        ) : (
          <>
            <Save className="w-4 h-4" />
            保存设置
          </>
        )}
      </button>
    </div>
  );
}
