import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { community } from '../lib/api';
import { useLocale } from '../context/LocaleContext';
import ExperienceCard from '../components/ExperienceCard';

const STATS_INITIAL = { total_experiences: 0, total_contributors: 0, total_adoptions: 0 };
const PLUGIN_VERSION = '1.0.0';
const DESKTOP_VERSION = '1.0.0';

export default function HomePage() {
  const { t } = useLocale();
  const [trending, setTrending] = useState([]);
  const [stats, setStats] = useState(STATS_INITIAL);

  useEffect(() => {
    community.trending(8).then(r => setTrending(r?.items || [])).catch(() => {});
    community.stats().then(r => setStats(r || STATS_INITIAL)).catch(() => {});
  }, []);

  return (
    <div>
      <section className="bg-[#f6f8fa] border-b border-[#d1d9e0]">
        <div className="max-w-[1280px] mx-auto px-4 lg:px-8 py-12 lg:py-16 text-center">
          <h1 className="text-2xl lg:text-4xl font-bold tracking-tight text-[#24292f]">{t('home.title')}</h1>
          <p className="mt-3 text-sm text-gray-500 max-w-2xl mx-auto">{t('home.subtitle')}</p>
          <div className="mt-6 flex gap-3 justify-center flex-wrap">
            <Link to="/explore" className="btn-primary no-underline hover:no-underline">{t('home.browse')}</Link>
            <Link to="/login?tab=register" className="btn-secondary no-underline hover:no-underline">{t('home.join')}</Link>
          </div>
        </div>
      </section>

      <section className="border-b border-[#d1d9e0]">
        <div className="max-w-[1280px] mx-auto px-4 lg:px-8 py-6 flex justify-center gap-12 text-center">
          <div>
            <div className="text-2xl font-bold text-[#24292f]">{stats.total_experiences}</div>
            <div className="text-xs text-gray-500 mt-0.5">{t('stats.experiences')}</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-[#24292f]">{stats.total_contributors}</div>
            <div className="text-xs text-gray-500 mt-0.5">{t('stats.contributors')}</div>
          </div>
          <div>
            <div className="text-2xl font-bold text-[#24292f]">{stats.total_adoptions}</div>
            <div className="text-xs text-gray-500 mt-0.5">{t('stats.adoptions')}</div>
          </div>
        </div>
      </section>

      <div className="max-w-[1280px] mx-auto px-4 lg:px-8 py-10">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-[#24292f]">{t('home.trending')}</h2>
              <Link to="/explore" className="text-xs">{t('home.viewAll')}</Link>
            </div>
            <div className="card">
              {trending.length > 0 ? (
                trending.map(exp => <ExperienceCard key={exp.id} exp={exp} />)
              ) : (
                <p className="text-gray-400 text-sm py-8 text-center">{t('home.noExp')}</p>
              )}
            </div>
          </div>
          <div className="space-y-4">
            <div className="card">
              <h3 className="font-semibold text-sm mb-3 text-[#24292f]">{t('home.quickStart')}</h3>
              <ul className="space-y-2 text-sm">
                <li><Link to="/explore">{t('home.search')}</Link></li>
                <li><Link to="/share">{t('home.share')}</Link></li>
                <li><Link to="/leaderboard">{t('home.viewLeaderboard')}</Link></li>
              </ul>
            </div>
            <div className="card">
              <h3 className="font-semibold text-sm mb-3 text-[#24292f]">{t('home.platforms')}</h3>
              <div className="flex flex-wrap gap-2">
                {['web', 'android', 'ios', 'miniprogram', 'desktop'].map(p => (
                  <span key={p} className="label bg-[#f6f8fa] text-gray-600 border border-[#d1d9e0]">{t(`platform.${p}`)}</span>
                ))}
              </div>
            </div>
            <div className="card">
              <h3 className="font-semibold text-sm mb-2 text-[#24292f]">{t('home.about')}</h3>
              <p className="text-xs text-gray-500 leading-relaxed">{t('home.aboutDesc')}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
