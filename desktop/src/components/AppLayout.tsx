/**
 * 应用主布局：左侧导航 + 右侧内容区
 */

import { NavLink, Outlet } from 'react-router-dom';
import {
  Play,
  History,
  Settings,
  Activity,
  BrainCircuit,
  HelpCircle,
  BarChart3,
  User,
  Users,
  Monitor,
  Smartphone,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: Play, label: '开始测试' },
  { to: '/running', icon: Activity, label: '测试面板' },
  { to: '/desktop-test', icon: Monitor, label: '桌面测试' },
  { to: '/miniprogram-test', icon: Smartphone, label: '小程序测试' },
  { to: '/multiplayer-test', icon: Users, label: '多端协同' },
  { to: '/history', icon: History, label: '历史记录' },
  { to: '/analytics', icon: BarChart3, label: '报告分析' },
  { to: '/dashboard', icon: User, label: '个人中心' },
  { to: '/team', icon: Users, label: '团队协作' },
  { to: '/settings', icon: Settings, label: '设置' },
  { to: '/help', icon: HelpCircle, label: '帮助' },
];

export default function AppLayout() {
  return (
    <div className="flex h-screen bg-gray-950 text-gray-100">
      {/* 左侧导航 */}
      <aside className="w-56 flex flex-col border-r border-gray-800 bg-gray-900">
        {/* Logo */}
        <div className="flex items-center gap-2 px-4 py-5 border-b border-gray-800">
          <BrainCircuit className="w-7 h-7 text-indigo-400" />
          <div>
            <h1 className="text-sm font-bold text-white leading-tight">TestPilot AI</h1>
            <span className="text-[10px] text-gray-500">v1.0.0</span>
          </div>
        </div>

        {/* 导航链接 */}
        <nav className="flex-1 py-3 space-y-0.5 px-2">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-indigo-500/15 text-indigo-400 font-medium'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* 底部引擎状态 */}
        <div className="px-4 py-3 border-t border-gray-800 text-xs text-gray-500">
          引擎: 127.0.0.1:8900
        </div>
      </aside>

      {/* 右侧内容区 */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
