/**
 * 个人仪表盘页（v6.0）
 *
 * 登录后显示：用户信息、项目列表、用量统计、快速操作
 * 未登录时显示登录/注册表单
 */

import { useState, useEffect } from 'react';
import {
  User, LogOut, Plus, FolderOpen, Zap, TestTube,
  Loader2, Trash2, ExternalLink, Shield,
} from 'lucide-react';
import {
  getToken, getMe, authLogin, authRegister, authLogout,
  listProjects, createProject, deleteProject, getUsage,
  type UserInfo, type ProjectInfo, type UsageSummary,
} from '../lib/engineClient';

export default function DashboardPage() {
  const [user, setUser] = useState<UserInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { checkAuth(); }, []);

  const checkAuth = async () => {
    setLoading(true);
    if (!getToken()) { setLoading(false); return; }
    try {
      setUser(await getMe());
    } catch {
      setUser(null);
    } finally { setLoading(false); }
  };

  const handleLogout = () => { authLogout(); setUser(null); };

  if (loading) return (
    <div className="flex items-center justify-center h-full">
      <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
    </div>
  );

  if (!user) return <AuthForm onSuccess={setUser} />;

  return <LoggedInDashboard user={user} onLogout={handleLogout} />;
}

/* ── 登录/注册表单 ── */
function AuthForm({ onSuccess }: { onSuccess: (u: UserInfo) => void }) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setError(''); setLoading(true);
    try {
      const res = mode === 'login'
        ? await authLogin(email, password)
        : await authRegister(email, username, password);
      onSuccess(res.user);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setLoading(false); }
  };

  return (
    <div className="flex items-center justify-center h-full">
      <div className="w-96 bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5">
        <div className="text-center">
          <Shield className="w-10 h-10 text-indigo-400 mx-auto mb-2" />
          <h2 className="text-lg font-bold text-white">
            {mode === 'login' ? '登录' : '注册'}
          </h2>
          <p className="text-xs text-gray-500 mt-1">TestPilot AI 用户系统</p>
        </div>

        <div className="space-y-3">
          <input type="email" placeholder="邮箱" value={email} onChange={e => setEmail(e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 outline-none" />
          {mode === 'register' && (
            <input type="text" placeholder="用户名" value={username} onChange={e => setUsername(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 outline-none" />
          )}
          <input type="password" placeholder="密码" value={password} onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-500 focus:border-indigo-500 outline-none" />
        </div>

        {error && <div className="text-xs text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</div>}

        <button onClick={submit} disabled={loading}
          className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg disabled:opacity-50 transition-colors">
          {loading ? '处理中...' : mode === 'login' ? '登录' : '注册'}
        </button>

        <p className="text-xs text-center text-gray-500">
          {mode === 'login' ? '没有账号？' : '已有账号？'}
          <button onClick={() => { setMode(mode === 'login' ? 'register' : 'login'); setError(''); }}
            className="text-indigo-400 hover:underline ml-1">
            {mode === 'login' ? '注册' : '登录'}
          </button>
        </p>
      </div>
    </div>
  );
}

/* ── 已登录仪表盘 ── */
function LoggedInDashboard({ user, onLogout }: { user: UserInfo; onLogout: () => void }) {
  const [projects, setProjects] = useState<ProjectInfo[]>([]);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const [p, u] = await Promise.all([listProjects(), getUsage(30)]);
      setProjects(p); setUsage(u);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await createProject(newName.trim());
      setNewName('');
      await loadData();
    } catch { /* ignore */ }
    finally { setCreating(false); }
  };

  const handleDelete = async (id: number) => {
    try { await deleteProject(id); await loadData(); } catch { /* ignore */ }
  };

  const roleLabel: Record<string, string> = { free: '免费版', pro: '专业版', admin: '管理员' };

  return (
    <div className="p-6 space-y-6">
      {/* 顶栏 */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <User className="w-5 h-5 text-indigo-400" />
          个人仪表盘
        </h1>
        <div className="flex items-center gap-3">
          <span className="text-sm text-gray-400">{user.username}</span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-400 font-medium">
            {roleLabel[user.role] || user.role}
          </span>
          <button onClick={onLogout}
            className="flex items-center gap-1 text-xs text-gray-500 hover:text-red-400 transition-colors">
            <LogOut className="w-3.5 h-3.5" /> 登出
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-indigo-400" /></div>
      ) : (
        <>
          {/* 用量概览 */}
          {usage && (
            <div className="grid grid-cols-4 gap-3">
              <StatCard label="今日测试" value={`${usage.total_tests}`} sub={`上限 ${usage.quotas.max_tests_per_day}/天`} color="text-indigo-400" />
              <StatCard label="AI调用" value={`${usage.total_ai_calls}`} sub={`上限 ${usage.quotas.max_ai_calls_per_day}/天`} color="text-amber-400" />
              <StatCard label="项目数" value={`${projects.length}`} sub={`上限 ${usage.quotas.max_projects}`} color="text-emerald-400" />
              <StatCard label="存储" value={`${usage.quotas.storage_limit_mb}MB`} sub="配额" color="text-cyan-400" />
            </div>
          )}

          {/* 项目列表 */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
              <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
                <FolderOpen className="w-4 h-4" /> 我的项目
              </h3>
              <div className="flex items-center gap-2">
                <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="新项目名称"
                  onKeyDown={e => e.key === 'Enter' && handleCreate()}
                  className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-white placeholder-gray-500 w-40 outline-none focus:border-indigo-500" />
                <button onClick={handleCreate} disabled={creating || !newName.trim()}
                  className="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs rounded-lg disabled:opacity-40 transition-colors">
                  <Plus className="w-3.5 h-3.5" /> 创建
                </button>
              </div>
            </div>

            {projects.length === 0 ? (
              <div className="text-center py-10 text-gray-500 text-sm">
                <FolderOpen className="w-10 h-10 mx-auto mb-2 opacity-30" />
                暂无项目，创建第一个项目开始测试
              </div>
            ) : (
              <div className="divide-y divide-gray-800">
                {projects.map(p => (
                  <div key={p.id} className="flex items-center justify-between px-5 py-3 hover:bg-gray-800/50 transition-colors">
                    <div>
                      <div className="text-sm font-medium text-white">{p.name}</div>
                      <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                        {p.base_url && (
                          <span className="flex items-center gap-1">
                            <ExternalLink className="w-3 h-3" /> {p.base_url}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <TestTube className="w-3 h-3" /> {p.test_count} 次测试
                        </span>
                        <span className="flex items-center gap-1">
                          <Zap className="w-3 h-3" /> {(p.last_pass_rate * 100).toFixed(0)}% 通过率
                        </span>
                      </div>
                    </div>
                    <button onClick={() => handleDelete(p.id)}
                      className="text-gray-600 hover:text-red-400 transition-colors p-1">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function StatCard({ label, value, sub, color }: { label: string; value: string; sub: string; color: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3 text-center">
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
      <div className="text-xs text-gray-500 mt-0.5">{label}</div>
      <div className="text-[10px] text-gray-600 mt-1">{sub}</div>
    </div>
  );
}
