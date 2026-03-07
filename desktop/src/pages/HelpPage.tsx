/**
 * 帮助页面（v1.0）
 *
 * 应用内帮助文档和引导教程。
 */

import { HelpCircle, Zap, Bug, Wrench, Monitor, Coins, BookOpen, ExternalLink } from 'lucide-react';

const sections = [
  {
    icon: Zap,
    title: '快速开始',
    content: [
      '1. 确保 Python 引擎已启动（poetry run python main.py）',
      '2. 确保 Docker Desktop 已运行',
      '3. 在「开始测试」页面填写被测应用 URL',
      '4. 点击「开始测试」，AI 将自动操作浏览器执行测试',
      '5. 在「测试面板」查看实时进度和结果',
    ],
  },
  {
    icon: Bug,
    title: 'Bug 检测',
    content: [
      'AI 在每个步骤执行后截图，通过视觉分析检测异常',
      'Bug 按严重程度分为：critical / high / medium / low',
      '阻塞性 Bug 会停止后续测试，非阻塞性 Bug 继续执行',
      '所有 Bug 会汇总到测试报告中',
    ],
  },
  {
    icon: Wrench,
    title: '自动修复',
    content: [
      '勾选「发现 Bug 后自动修复」并填写项目根目录',
      'AI 将分析 Bug 原因，生成代码修复补丁',
      '补丁会自动应用并重新测试验证',
      '修复失败会自动回滚，不会破坏你的代码',
    ],
  },
  {
    icon: Monitor,
    title: '实时观看',
    content: [
      '测试面板中的「实时画面」区域显示浏览器截图',
      '截图每 3 秒自动刷新',
      '后续版本将集成 VNC 实时直播模式',
    ],
  },
  {
    icon: Coins,
    title: '积分计量',
    content: [
      '每次操作消耗不同积分：生成脚本 1 分，执行步骤 1 分/步，修复 Bug 3 分/个',
      '典型 20 步测试 + 修复 3 个 Bug ≈ 33 积分',
      '免费版：50 积分/月 | 基础版：19元/月 500 积分',
      '专业版：59元/月 2000 积分 | 团队版：199元/月 10000 积分',
    ],
  },
  {
    icon: BookOpen,
    title: 'API 使用',
    content: [
      'GET  /api/v1/health — 健康检查',
      'POST /api/v1/test/run — 启动测试',
      'GET  /api/v1/memory/history — 查询历史',
      'GET  /api/v1/memory/stats — 记忆统计',
      'GET  /api/v1/live/screenshot — 获取实时截图',
      'WS   /ws — WebSocket 实时进度',
    ],
  },
];

export default function HelpPage() {
  return (
    <div className="p-6 max-w-3xl space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-white flex items-center gap-2">
          <HelpCircle className="w-5 h-5 text-indigo-400" />
          帮助文档
        </h1>
        <span className="text-xs text-gray-500">TestPilot AI v1.0</span>
      </div>

      <div className="bg-indigo-500/10 border border-indigo-500/20 rounded-xl p-4">
        <p className="text-sm text-indigo-300">
          TestPilot AI 是 AI 驱动的自动化测试机器人。它像人类一样操作你的应用界面，
          自动发现 Bug，自动修复代码，并生成详细的测试报告。
        </p>
      </div>

      <div className="space-y-4">
        {sections.map(({ icon: Icon, title, content }) => (
          <details
            key={title}
            className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden group"
          >
            <summary className="px-5 py-4 cursor-pointer flex items-center gap-3 hover:bg-gray-800/50 transition-colors">
              <Icon className="w-4 h-4 text-indigo-400 shrink-0" />
              <span className="text-sm font-medium text-white">{title}</span>
            </summary>
            <div className="px-5 pb-4 space-y-1.5">
              {content.map((line, i) => (
                <p key={i} className="text-xs text-gray-400 leading-relaxed pl-7">
                  {line}
                </p>
              ))}
            </div>
          </details>
        ))}
      </div>

      <div className="text-center pt-4">
        <a
          href="https://github.com"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-indigo-400 transition-colors"
        >
          <ExternalLink className="w-3 h-3" />
          完整文档
        </a>
      </div>
    </div>
  );
}
