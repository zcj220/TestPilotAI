/**
 * 历史记录页
 *
 * 显示测试历史列表，点击可查看详情。
 */

import { useState, useEffect } from 'react';
import { History, ExternalLink, CheckCircle, XCircle, Clock, Bug, Loader2 } from 'lucide-react';
import { getHistory } from '../lib/engineClient';

interface HistoryItem {
  id?: string;
  url: string;
  test_name: string;
  pass_rate: number;
  bug_count: number;
  total_steps: number;
  passed_steps: number;
  failed_steps: number;
  duration_seconds: number;
  report_markdown: string;
  created_at?: string;
}

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<HistoryItem | null>(null);

  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getHistory(undefined, 20);
      setItems(data as HistoryItem[]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <History className="w-5 h-5 text-indigo-400" />
          历史记录
        </h1>
        <button
          onClick={loadHistory}
          className="text-xs text-gray-400 hover:text-white transition-colors"
        >
          刷新
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
        </div>
      )}

      {error && (
        <div className="text-sm text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg px-4 py-3">
          加载失败: {error}
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className="text-center py-20 text-gray-500">
          <History className="w-12 h-12 mx-auto mb-3 opacity-30" />
          <p>暂无测试记录</p>
          <p className="text-xs mt-1">完成第一次测试后这里将显示历史</p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧列表 */}
        <div className="space-y-2">
          {items.map((item, i) => (
            <button
              key={i}
              onClick={() => setSelected(item)}
              className={`w-full text-left p-4 rounded-xl border transition-colors ${
                selected === item
                  ? 'bg-indigo-500/10 border-indigo-500/30'
                  : 'bg-gray-900 border-gray-800 hover:border-gray-700'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <h3 className="text-sm font-medium text-white truncate pr-2">
                  {item.test_name || item.url}
                </h3>
                <span className={`text-xs font-bold shrink-0 ${
                  item.pass_rate >= 0.8 ? 'text-emerald-400' : 'text-red-400'
                }`}>
                  {(item.pass_rate * 100).toFixed(0)}%
                </span>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  <ExternalLink className="w-3 h-3" />
                  {item.url}
                </span>
              </div>
              <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
                <span className="flex items-center gap-1">
                  {item.pass_rate >= 0.8 ? (
                    <CheckCircle className="w-3 h-3 text-emerald-500" />
                  ) : (
                    <XCircle className="w-3 h-3 text-red-500" />
                  )}
                  {item.passed_steps}/{item.total_steps} 步骤
                </span>
                <span className="flex items-center gap-1">
                  <Bug className="w-3 h-3" />
                  {item.bug_count} Bug
                </span>
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {item.duration_seconds?.toFixed(1)}s
                </span>
              </div>
            </button>
          ))}
        </div>

        {/* 右侧详情 */}
        {selected && (
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-800">
              <h3 className="text-sm font-medium text-white">{selected.test_name}</h3>
              <p className="text-xs text-gray-500 mt-0.5">{selected.url}</p>
            </div>
            <pre className="p-4 text-xs text-gray-300 overflow-auto max-h-[60vh] whitespace-pre-wrap">
              {selected.report_markdown || '无报告内容'}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}
