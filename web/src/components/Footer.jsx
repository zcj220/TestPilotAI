import { Link } from 'react-router-dom';
import { useLocale } from '../context/LocaleContext';

export default function Footer() {
  const { t } = useLocale();
  return (
    <footer className="border-t border-[#d1d9e0] mt-auto">
      <div className="max-w-[1280px] mx-auto px-4 lg:px-8 py-10">
        <div className="flex flex-col md:flex-row justify-between gap-8 text-sm text-gray-500">
          <div className="flex items-center gap-2">
            <span className="text-gray-400">© 2026 TestPilot AI</span>
          </div>
          <div className="flex flex-wrap gap-6">
            <Link to="/explore" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.explore')}</Link>
            <Link to="/pricing" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.pricing')}</Link>
            <Link to="/leaderboard" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.leaderboard')}</Link>
            <a href="https://github.com" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">GitHub</a>
          </div>
        </div>
      </div>
    </footer>
  );
}
