import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { profile } from '../lib/api';
import { useLocale } from '../context/LocaleContext';
import ExperienceCard from '../components/ExperienceCard';

export default function UserProfilePage() {
  const { userId } = useParams();
  const { t } = useLocale();
  const [data, setData] = useState(null);
  const [contributions, setContributions] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([profile.get(userId), profile.contributions(userId)])
      .then(([p, c]) => { setData(p); setContributions(c?.items || []); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) return <div className="max-w-4xl mx-auto px-4 py-16 text-center text-sm text-gray-400">{t('common.loading')}</div>;
  if (!data) return <div className="max-w-4xl mx-auto px-4 py-16 text-center text-sm text-gray-500">{t('profile.notFound')}</div>;

  const { profile: p, badges, stats } = data;
  const platforms = stats?.platform_breakdown || {};

  return (
    <div className="max-w-4xl mx-auto px-4 lg:px-8 py-6">
      <div className="flex items-start gap-4 pb-4 border-b border-[#d1d9e0] mb-6">
        <div className="w-16 h-16 rounded-full bg-[#f6f8fa] border border-[#d1d9e0] flex items-center justify-center text-xl font-bold text-[#24292f] shrink-0">
          {(p.display_name || '?')[0].toUpperCase()}
        </div>
        <div>
          <h1 className="text-xl font-semibold text-[#24292f]">{p.display_name || `User ${userId}`}</h1>
          {p.bio && <p className="text-sm text-gray-500 mt-1">{p.bio}</p>}
          {(p.expertise_tags || []).length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {p.expertise_tags.map(tag => <span key={tag} className="label bg-[#f6f8fa] text-gray-600 border border-[#d1d9e0]">{tag}</span>)}
            </div>
          )}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-6">
        {[
          { n: stats?.total_shares || 0, l: t('stats.shares') },
          { n: stats?.total_upvotes || 0, l: t('stats.upvotes') },
          { n: stats?.total_adoptions || 0, l: t('stats.adoptions') },
          { n: stats?.total_views || 0, l: t('stats.views') },
        ].map(s => (
          <div key={s.l} className="card text-center !py-3">
            <div className="text-lg font-semibold text-[#24292f]">{s.n}</div>
            <div className="text-xs text-gray-500">{s.l}</div>
          </div>
        ))}
      </div>

      {badges?.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-sm font-semibold text-[#24292f] mb-3">{t('profile.badges')}</h2>
          <div className="flex flex-wrap gap-2">
            {badges.map(b => (
              <span key={b.badge_type} className="label bg-[#f6f8fa] text-gray-700 border border-[#d1d9e0]" title={b.condition}>
                {b.icon} {b.badge_name}
              </span>
            ))}
          </div>
        </div>
      )}

      {Object.keys(platforms).length > 0 && (
        <div className="card mb-6">
          <h2 className="text-sm font-semibold text-[#24292f] mb-3">{t('profile.platformDist')}</h2>
          <div className="space-y-2">
            {Object.entries(platforms).map(([plat, count]) => {
              const max = Math.max(...Object.values(platforms));
              return (
                <div key={plat} className="flex items-center gap-3 text-sm">
                  <span className="w-16 text-gray-600 capitalize">{plat}</span>
                  <div className="flex-1 bg-[#f6f8fa] rounded-full h-2">
                    <div className="bg-[#24292f] h-2 rounded-full" style={{ width: `${max > 0 ? (count / max) * 100 : 0}%` }} />
                  </div>
                  <span className="text-gray-400 w-6 text-right text-xs">{count}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <h2 className="text-sm font-semibold text-[#24292f] mb-3">{t('profile.contributions')} ({contributions.length})</h2>
      {contributions.length === 0 ? (
        <div className="card text-center py-8 text-sm text-gray-400">{t('profile.noShares')}</div>
      ) : (
        <div className="card">
          {contributions.map(exp => <ExperienceCard key={exp.id} exp={exp} />)}
        </div>
      )}
    </div>
  );
}
