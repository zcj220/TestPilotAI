import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../context/LocaleContext';

export default function Navbar() {
  const { user, logout } = useAuth();
  const { t, locale, setLocale } = useLocale();
  const navigate = useNavigate();

  return (
    <nav className="bg-[#f6f8fa] border-b border-[#d1d9e0] sticky top-0 z-50">
      <div className="max-w-[1280px] mx-auto px-4 lg:px-8">
        <div className="flex items-center h-12 gap-4">
          <Link to="/" className="flex items-center gap-2 text-[#24292f] no-underline hover:no-underline shrink-0">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5"/><path d="M8 12l2.5 2.5L16 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            <span className="font-semibold text-base">
              {locale === 'zh' ? '测试领航员 AI' : 'TestPilot AI'}
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-4 text-sm">
            <Link to="/explore" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.explore')}</Link>
            <Link to="/leaderboard" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.leaderboard')}</Link>
            <Link to="/pricing" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.pricing')}</Link>
            <Link to="/download" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.download')}</Link>
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-3 text-sm">
            {/* 语言切换 */}
            <button
              onClick={() => setLocale(locale === 'zh' ? 'en' : 'zh')}
              className="text-[#24292f] hover:text-black text-xs cursor-pointer px-1.5 py-0.5 rounded border border-[#d1d9e0] hover:bg-[#ebeef1]"
            >
              {locale === 'zh' ? 'EN' : '中文'}
            </button>

            {user ? (
              <>
                <Link to="/dashboard" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.dashboard')}</Link>
                <Link to={`/user/${user.id}`} className="text-[#24292f] hover:text-black no-underline hover:no-underline">{user.username}</Link>
                <button onClick={() => { logout(); navigate('/'); }} className="text-gray-400 hover:text-gray-600 text-sm cursor-pointer">{t('nav.logout')}</button>
              </>
            ) : (
              <>
                <Link to="/login" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.login')}</Link>
                <Link to="/login?tab=register" className="text-[#24292f] hover:text-black no-underline hover:no-underline">{t('nav.register')}</Link>
              </>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
