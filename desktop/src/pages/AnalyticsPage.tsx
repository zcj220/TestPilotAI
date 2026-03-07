/**
 * 报告分析页（v5.2）
 *
 * 可视化展示：通过率趋势、Bug热力图、截图时间线、历史对比、HTML导出
 */

import { useState, useEffect } from 'react';
import {
  BarChart3, TrendingUp, Bug, FileDown, GitCompare,
  Loader2, ChevronDown, ChevronRight,
  CheckCircle, XCircle, AlertTriangle,
} from 'lucide-react';
import {
  getPassRateTrend, getBugHeatmap, getHistory, compareReports, getExportHtmlUrl,
  type TrendData, type HeatmapData, type CompareData,
} from '../lib/engineClient';

type Tab = 'trend' | 'heatmap' | 'compare';

export default function AnalyticsPage() {
  const [tab, setTab] = useState<Tab>('trend');

  const tabs: { key: Tab; label: string; icon: typeof TrendingUp }[] = [
    { key: 'trend', label: '通过率趋势', icon: TrendingUp },
    { key: 'heatmap', label: 'Bug热力图', icon: Bug },
    { key: 'compare', label: '历史对比', icon: GitCompare },
  ];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <BarChart3 className="w-5 h-5 text-indigo-400" />
          报告分析
        </h1>
      </div>

      {/* Tab切换 */}
      <div className="flex gap-1 bg-gray-900 rounded-lg p-1">
        {tabs.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm transition-colors flex-1 justify-center ${
              tab === key
                ? 'bg-indigo-500/20 text-indigo-400 font-medium'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === 'trend' && <TrendPanel />}
      {tab === 'heatmap' && <HeatmapPanel />}
      {tab === 'compare' && <ComparePanel />}
    </div>
  );
}

/* ── 通过率趋势 ── */
function TrendPanel() {
  const [data, setData] = useState<TrendData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);
  const load = async () => {
    setLoading(true); setError('');
    try { setData(await getPassRateTrend(undefined, 30)); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  };

  if (loading) return <Loading />;
  if (error) return <ErrorMsg msg={error} />;
  if (!data || data.count === 0) return <Empty msg="暂无测试数据，完成测试后这里将展示趋势" />;

  const maxRate = 1;
  const chartH = 200;
  const barW = Math.max(20, Math.min(60, 700 / data.count));

  return (
    <div className="space-y-4">
      {/* 概览统计 */}
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="测试次数" value={String(data.count)} color="text-indigo-400" />
        <StatCard label="最新通过率" value={`${(data.pass_rates[data.count - 1] * 100).toFixed(0)}%`}
          color={data.pass_rates[data.count - 1] >= 0.8 ? 'text-emerald-400' : 'text-red-400'} />
        <StatCard label="平均通过率"
          value={`${(data.pass_rates.reduce((a, b) => a + b, 0) / data.count * 100).toFixed(0)}%`}
          color="text-amber-400" />
        <StatCard label="总Bug数" value={String(data.bug_counts.reduce((a, b) => a + b, 0))} color="text-red-400" />
      </div>

      {/* 柱状图 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-medium text-gray-300 mb-4">通过率趋势</h3>
        <div className="flex items-end gap-1 overflow-x-auto pb-2" style={{ height: chartH + 40 }}>
          {data.pass_rates.map((rate, i) => {
            const h = (rate / maxRate) * chartH;
            const color = rate >= 0.8 ? 'bg-emerald-500' : rate >= 0.5 ? 'bg-amber-500' : 'bg-red-500';
            return (
              <div key={i} className="flex flex-col items-center shrink-0" style={{ width: barW }}>
                <div className="text-[10px] text-gray-500 mb-1">{(rate * 100).toFixed(0)}%</div>
                <div className={`${color} rounded-t-sm w-3/4 transition-all hover:opacity-80`}
                  style={{ height: Math.max(2, h) }}
                  title={`${data.test_names[i]}\n${data.labels[i]}\n通过率: ${(rate*100).toFixed(1)}%\nBug: ${data.bug_counts[i]}`}
                />
                <div className="text-[9px] text-gray-600 mt-1 truncate w-full text-center">
                  {data.labels[i]}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Bug数量趋势 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-medium text-gray-300 mb-4">Bug数量趋势</h3>
        <div className="flex items-end gap-1 overflow-x-auto pb-2" style={{ height: 120 + 40 }}>
          {data.bug_counts.map((count, i) => {
            const maxBug = Math.max(...data.bug_counts, 1);
            const h = (count / maxBug) * 120;
            return (
              <div key={i} className="flex flex-col items-center shrink-0" style={{ width: barW }}>
                <div className="text-[10px] text-gray-500 mb-1">{count}</div>
                <div className="bg-red-500/70 rounded-t-sm w-3/4"
                  style={{ height: Math.max(count > 0 ? 4 : 0, h) }}
                  title={`${data.test_names[i]}: ${count} Bug`}
                />
                <div className="text-[9px] text-gray-600 mt-1 truncate w-full text-center">
                  {data.labels[i]}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── Bug热力图 ── */
function HeatmapPanel() {
  const [data, setData] = useState<HeatmapData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { load(); }, []);
  const load = async () => {
    setLoading(true); setError('');
    try { setData(await getBugHeatmap(undefined, 100)); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  };

  if (loading) return <Loading />;
  if (error) return <ErrorMsg msg={error} />;
  if (!data || data.total_bugs === 0) return <Empty msg="暂无Bug数据" />;

  const sevColors: Record<string, string> = {
    critical: 'bg-red-600', major: 'bg-orange-500', minor: 'bg-amber-500', unknown: 'bg-gray-500',
  };

  return (
    <div className="space-y-4">
      {/* 概览 */}
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="总Bug数" value={String(data.total_bugs)} color="text-red-400" />
        <StatCard label="涉及页面" value={String(data.by_page.length)} color="text-indigo-400" />
        <StatCard label="Bug类别" value={String(data.by_category.length)} color="text-amber-400" />
      </div>

      {/* 严重程度分布 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-medium text-gray-300 mb-4">严重程度分布</h3>
        <div className="flex gap-4">
          {Object.entries(data.by_severity).map(([sev, count]) => (
            <div key={sev} className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-sm ${sevColors[sev] || 'bg-gray-500'}`} />
              <span className="text-sm text-gray-300 capitalize">{sev}</span>
              <span className="text-sm font-bold text-white">{count}</span>
            </div>
          ))}
        </div>
        {/* 条形图 */}
        <div className="mt-4 space-y-2">
          {Object.entries(data.by_severity).map(([sev, count]) => {
            const pct = data.total_bugs > 0 ? (count / data.total_bugs) * 100 : 0;
            return (
              <div key={sev} className="flex items-center gap-3">
                <span className="text-xs text-gray-400 w-16 capitalize">{sev}</span>
                <div className="flex-1 bg-gray-800 rounded-full h-4 overflow-hidden">
                  <div className={`h-full rounded-full ${sevColors[sev] || 'bg-gray-500'}`}
                    style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs text-gray-400 w-10 text-right">{pct.toFixed(0)}%</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 页面Bug排行 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h3 className="text-sm font-medium text-gray-300 mb-4">页面Bug排行</h3>
        <div className="space-y-2">
          {data.by_page.map((item, i) => {
            const pct = data.total_bugs > 0 ? (item.count / data.total_bugs) * 100 : 0;
            return (
              <div key={i} className="flex items-center gap-3">
                <span className="text-xs text-gray-400 truncate w-48" title={item.url}>{item.url}</span>
                <div className="flex-1 bg-gray-800 rounded-full h-3 overflow-hidden">
                  <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                </div>
                <span className="text-xs font-medium text-white w-8 text-right">{item.count}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 问题位置排行 */}
      {data.by_location.length > 0 && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h3 className="text-sm font-medium text-gray-300 mb-4">高频问题位置</h3>
          <div className="space-y-2">
            {data.by_location.map((item, i) => (
              <div key={i} className="flex items-center justify-between py-1.5 px-3 bg-gray-800/50 rounded-lg">
                <code className="text-xs text-amber-300">{item.location}</code>
                <span className="text-xs font-bold text-red-400">{item.count} 次</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── 历史对比 ── */
function ComparePanel() {
  const [history, setHistory] = useState<{ id: number; test_name: string; pass_rate: number; created_at: string }[]>([]);
  const [idA, setIdA] = useState<number | null>(null);
  const [idB, setIdB] = useState<number | null>(null);
  const [result, setResult] = useState<CompareData | null>(null);
  const [loading, setLoading] = useState(false);
  const [histLoading, setHistLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => { loadHist(); }, []);

  const loadHist = async () => {
    setHistLoading(true);
    try {
      const data = await getHistory(undefined, 50) as { id: number; test_name: string; pass_rate: number; created_at: string }[];
      setHistory(data);
      if (data.length >= 2) {
        setIdA(data[1].id);
        setIdB(data[0].id);
      }
    } catch { /* ignore */ }
    finally { setHistLoading(false); }
  };

  const doCompare = async () => {
    if (idA === null || idB === null) return;
    setLoading(true); setError(''); setResult(null);
    try { setResult(await compareReports(idA, idB)); }
    catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setLoading(false); }
  };

  if (histLoading) return <Loading />;

  return (
    <div className="space-y-4">
      {/* 选择器 */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
        <h3 className="text-sm font-medium text-gray-300">选择两次测试进行对比</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-xs text-gray-500 mb-1 block">测试A（较早）</label>
            <select value={idA ?? ''} onChange={e => setIdA(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200">
              <option value="">选择...</option>
              {history.map(h => (
                <option key={h.id} value={h.id}>
                  #{h.id} {h.test_name} ({(h.pass_rate * 100).toFixed(0)}%) - {h.created_at?.slice(0, 16)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">测试B（较新）</label>
            <select value={idB ?? ''} onChange={e => setIdB(Number(e.target.value))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-200">
              <option value="">选择...</option>
              {history.map(h => (
                <option key={h.id} value={h.id}>
                  #{h.id} {h.test_name} ({(h.pass_rate * 100).toFixed(0)}%) - {h.created_at?.slice(0, 16)}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={doCompare} disabled={!idA || !idB || loading}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm rounded-lg disabled:opacity-40 transition-colors">
            {loading ? '对比中...' : '开始对比'}
          </button>
          {idB && (
            <a href={getExportHtmlUrl(idB)} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-1.5 px-4 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded-lg transition-colors">
              <FileDown className="w-4 h-4" />
              导出HTML报告
            </a>
          )}
        </div>
      </div>

      {error && <ErrorMsg msg={error} />}

      {/* 对比结果 */}
      {result && !result.error && (
        <div className="space-y-4">
          {/* 概览指标 */}
          <div className={`p-4 rounded-xl border ${result.improved ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-red-500/5 border-red-500/20'}`}>
            <div className="flex items-center gap-2 mb-3">
              {result.improved ? (
                <TrendingUp className="w-5 h-5 text-emerald-400" />
              ) : (
                <AlertTriangle className="w-5 h-5 text-red-400" />
              )}
              <span className={`text-sm font-medium ${result.improved ? 'text-emerald-400' : 'text-red-400'}`}>
                {result.improved ? '质量提升' : '质量下降'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <div className="text-xs text-gray-500">通过率变化</div>
                <div className={`text-lg font-bold ${(result.summary.pass_rate_change as number) > 0 ? 'text-emerald-400' : (result.summary.pass_rate_change as number) < 0 ? 'text-red-400' : 'text-gray-400'}`}>
                  {(result.summary.pass_rate_change as number) > 0 ? '+' : ''}{((result.summary.pass_rate_change as number) * 100).toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">Bug数量变化</div>
                <div className={`text-lg font-bold ${(result.summary.bug_count_change as number) < 0 ? 'text-emerald-400' : (result.summary.bug_count_change as number) > 0 ? 'text-red-400' : 'text-gray-400'}`}>
                  {(result.summary.bug_count_change as number) > 0 ? '+' : ''}{result.summary.bug_count_change as number}
                </div>
              </div>
              <div>
                <div className="text-xs text-gray-500">通过率</div>
                <div className="text-sm text-gray-300">
                  {((result.summary.pass_rate_a as number) * 100).toFixed(0)}% → {((result.summary.pass_rate_b as number) * 100).toFixed(0)}%
                </div>
              </div>
            </div>
          </div>

          {/* Bug变化列表 */}
          <BugList title="已修复的Bug" bugs={result.fixed_bugs} icon={<CheckCircle className="w-4 h-4 text-emerald-400" />} emptyMsg="无" />
          <BugList title="新增的Bug" bugs={result.new_bugs} icon={<XCircle className="w-4 h-4 text-red-400" />} emptyMsg="无新增Bug" />
          <BugList title="持续存在的Bug" bugs={result.persistent_bugs} icon={<AlertTriangle className="w-4 h-4 text-amber-400" />} emptyMsg="无" />
        </div>
      )}
    </div>
  );
}

/* ── 共用组件 ── */

function StatCard({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-1">{label}</div>
    </div>
  );
}

function BugList({ title, bugs, icon, emptyMsg }: {
  title: string; bugs: Record<string, unknown>[]; icon: React.ReactElement; emptyMsg: string;
}) {
  const [open, setOpen] = useState(true);
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 hover:bg-gray-800/50 transition-colors">
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        {icon}
        {title} ({bugs.length})
      </button>
      {open && (
        <div className="px-4 pb-3 space-y-2">
          {bugs.length === 0 ? (
            <div className="text-xs text-gray-500 py-2">{emptyMsg}</div>
          ) : bugs.map((b, i) => (
            <div key={i} className="flex items-start gap-2 py-2 border-t border-gray-800/50">
              <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase ${
                b.severity === 'critical' ? 'bg-red-600/20 text-red-400'
                : b.severity === 'major' ? 'bg-orange-500/20 text-orange-400'
                : 'bg-amber-500/20 text-amber-400'
              }`}>{String(b.severity ?? '')}</span>
              <div>
                <div className="text-sm text-gray-200">{String(b.title ?? '')}</div>
                {b.description ? <div className="text-xs text-gray-500 mt-0.5">{String(b.description)}</div> : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Loading() {
  return (
    <div className="flex items-center justify-center py-20">
      <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
    </div>
  );
}

function ErrorMsg({ msg }: { msg: string }) {
  return (
    <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
      加载失败: {msg}
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return (
    <div className="text-center py-20 text-gray-500">
      <BarChart3 className="w-12 h-12 mx-auto mb-3 opacity-30" />
      <p>{msg}</p>
    </div>
  );
}
