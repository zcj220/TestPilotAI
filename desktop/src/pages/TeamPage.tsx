/**
 * 团队协作页（v6.1）
 *
 * 功能：团队列表/创建/加入/成员管理/项目共享/团队看板
 */

import { useState, useEffect } from 'react';
import {
  Users, Plus, Copy, Loader2, Trash2, UserPlus,
  BarChart3, FolderOpen, RefreshCw, LogIn,
} from 'lucide-react';
import { getToken } from '../lib/engineClient';

// ── 类型 ──

interface TeamInfo {
  id: number; name: string; description: string; owner_id: number;
  my_role: string; member_count: number; invite_code: string; created_at: string;
}

interface MemberInfo {
  user_id: number; username: string; email: string; role: string; joined_at: string;
}

interface TeamDashboard {
  team_name: string; member_count: number; project_count: number;
  total_tests: number; total_bugs: number; avg_pass_rate: number;
  members: MemberInfo[];
  projects: { id: number; name: string; test_count: number; last_pass_rate: number; total_bugs_found: number }[];
}

// ── API helpers (inline to avoid large engineClient edit) ──

async function teamApi<T>(method: string, path: string, body?: unknown): Promise<T> {
  const base = ((window as unknown) as Record<string, unknown>).__ENGINE_URL__ || 'http://localhost:8900';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(`${base}/api/v1${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
  return resp.json() as Promise<T>;
}

export default function TeamPage() {
  const [teams, setTeams] = useState<TeamInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [joinCode, setJoinCode] = useState('');
  const [error, setError] = useState('');

  const isLoggedIn = !!getToken();

  useEffect(() => { if (isLoggedIn) loadTeams(); else setLoading(false); }, []);

  const loadTeams = async () => {
    setLoading(true);
    try { setTeams(await teamApi<TeamInfo[]>('GET', '/teams')); } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const handleCreate = async () => {
    if (!newName.trim()) return;
    setError('');
    try {
      await teamApi('POST', '/teams', { name: newName.trim() });
      setNewName(''); await loadTeams();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  };

  const handleJoin = async () => {
    if (!joinCode.trim()) return;
    setError('');
    try {
      await teamApi('POST', '/teams/join', { invite_code: joinCode.trim() });
      setJoinCode(''); await loadTeams();
    } catch (e: unknown) { setError(e instanceof Error ? e.message : String(e)); }
  };

  if (!isLoggedIn) return (
    <div className="flex items-center justify-center h-full text-gray-500 text-sm">
      <div className="text-center">
        <Users className="w-12 h-12 mx-auto mb-3 opacity-30" />
        请先在「个人中心」登录后使用团队功能
      </div>
    </div>
  );

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <Users className="w-5 h-5 text-violet-400" /> 团队协作
        </h1>
      </div>

      {/* 创建 + 加入 */}
      <div className="flex gap-3">
        <div className="flex items-center gap-2 flex-1">
          <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="新团队名称"
            onKeyDown={e => e.key === 'Enter' && handleCreate()}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 flex-1 outline-none focus:border-violet-500" />
          <button onClick={handleCreate} disabled={!newName.trim()}
            className="flex items-center gap-1 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg disabled:opacity-40 transition-colors">
            <Plus className="w-4 h-4" /> 创建
          </button>
        </div>
        <div className="flex items-center gap-2">
          <input value={joinCode} onChange={e => setJoinCode(e.target.value)} placeholder="邀请码"
            onKeyDown={e => e.key === 'Enter' && handleJoin()}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 w-52 outline-none focus:border-violet-500" />
          <button onClick={handleJoin} disabled={!joinCode.trim()}
            className="flex items-center gap-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded-lg disabled:opacity-40 transition-colors">
            <LogIn className="w-4 h-4" /> 加入
          </button>
        </div>
      </div>

      {error && <div className="text-xs text-red-400 bg-red-400/10 rounded-lg px-3 py-2">{error}</div>}

      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-6 h-6 animate-spin text-violet-400" /></div>
      ) : teams.length === 0 ? (
        <div className="text-center py-16 text-gray-500 text-sm">
          <Users className="w-12 h-12 mx-auto mb-3 opacity-20" />
          暂无团队，创建或通过邀请码加入一个
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-4">
          {teams.map(t => (
            <button key={t.id} onClick={() => setSelected(t.id === selected ? null : t.id)}
              className={`text-left bg-gray-900 border rounded-xl p-4 transition-colors ${t.id === selected ? 'border-violet-500' : 'border-gray-800 hover:border-gray-700'}`}>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium text-white">{t.name}</span>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-400">{t.my_role}</span>
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-500">
                <span><Users className="w-3 h-3 inline mr-1" />{t.member_count} 人</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {selected && <TeamDetail teamId={selected} onRefresh={loadTeams} />}
    </div>
  );
}

/* ── 团队详情面板 ── */
function TeamDetail({ teamId, onRefresh }: { teamId: number; onRefresh: () => void }) {
  const [data, setData] = useState<TeamDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [inviteCode, setInviteCode] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => { load(); }, [teamId]);

  const load = async () => {
    setLoading(true);
    try {
      const d = await teamApi<TeamDashboard>('GET', `/teams/${teamId}/dashboard`);
      setData(d);
      const teams = await teamApi<TeamInfo[]>('GET', '/teams');
      const t = teams.find(t => t.id === teamId);
      if (t) setInviteCode(t.invite_code);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  };

  const copyCode = () => {
    navigator.clipboard.writeText(inviteCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerate = async () => {
    try {
      const res = await teamApi<{ invite_code: string }>('POST', `/teams/${teamId}/regenerate-invite`);
      setInviteCode(res.invite_code);
    } catch { /* ignore */ }
  };

  const handleDelete = async () => {
    try {
      await teamApi('DELETE', `/teams/${teamId}`);
      onRefresh();
    } catch { /* ignore */ }
  };

  const handleRemove = async (userId: number) => {
    try {
      await teamApi('POST', `/teams/${teamId}/members/remove?user_id=${userId}`);
      await load();
    } catch { /* ignore */ }
  };

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="w-5 h-5 animate-spin text-violet-400" /></div>;
  if (!data) return null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      {/* 头部 */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800">
        <h3 className="text-sm font-medium text-white flex items-center gap-2">
          <BarChart3 className="w-4 h-4 text-violet-400" /> {data.team_name} 看板
        </h3>
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500 bg-gray-800 rounded px-2 py-1 font-mono">{inviteCode}</span>
          <button onClick={copyCode} className="text-gray-500 hover:text-violet-400 transition-colors p-1">
            <Copy className="w-3.5 h-3.5" />
          </button>
          {copied && <span className="text-[10px] text-emerald-400">已复制</span>}
          <button onClick={handleRegenerate} className="text-gray-500 hover:text-amber-400 transition-colors p-1" title="重新生成邀请码">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button onClick={handleDelete} className="text-gray-600 hover:text-red-400 transition-colors p-1" title="删除团队">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-4 gap-3 px-5 py-4">
        <MiniStat label="成员" value={String(data.member_count)} color="text-violet-400" />
        <MiniStat label="项目" value={String(data.project_count)} color="text-emerald-400" />
        <MiniStat label="测试总数" value={String(data.total_tests)} color="text-amber-400" />
        <MiniStat label="平均通过率" value={`${(data.avg_pass_rate * 100).toFixed(0)}%`} color="text-cyan-400" />
      </div>

      {/* 成员列表 */}
      <div className="px-5 pb-4">
        <h4 className="text-xs text-gray-500 font-medium mb-2 flex items-center gap-1">
          <UserPlus className="w-3 h-3" /> 成员
        </h4>
        <div className="space-y-1">
          {data.members.map(m => (
            <div key={m.user_id} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-gray-800/50 transition-colors">
              <div className="flex items-center gap-2">
                <span className="text-sm text-white">{m.username}</span>
                <span className="text-[10px] text-gray-500">{m.email}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${m.role === 'admin' ? 'bg-amber-500/20 text-amber-400' : m.role === 'viewer' ? 'bg-gray-700 text-gray-400' : 'bg-violet-500/15 text-violet-400'}`}>
                  {m.role}
                </span>
              </div>
              {m.role !== 'admin' && (
                <button onClick={() => handleRemove(m.user_id)} className="text-gray-600 hover:text-red-400 transition-colors">
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 项目列表 */}
      {data.projects.length > 0 && (
        <div className="px-5 pb-4">
          <h4 className="text-xs text-gray-500 font-medium mb-2 flex items-center gap-1">
            <FolderOpen className="w-3 h-3" /> 共享项目
          </h4>
          <div className="space-y-1">
            {data.projects.map(p => (
              <div key={p.id} className="flex items-center justify-between py-1.5 px-3 rounded-lg hover:bg-gray-800/50">
                <span className="text-sm text-white">{p.name}</span>
                <div className="flex items-center gap-3 text-xs text-gray-500">
                  <span>{p.test_count} 次测试</span>
                  <span>{(p.last_pass_rate * 100).toFixed(0)}% 通过</span>
                  <span>{p.total_bugs_found} Bug</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="bg-gray-800/50 rounded-lg px-3 py-2 text-center">
      <div className={`text-lg font-bold ${color}`}>{value}</div>
      <div className="text-[10px] text-gray-500">{label}</div>
    </div>
  );
}
