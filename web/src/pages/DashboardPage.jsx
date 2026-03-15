import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../context/LocaleContext';
import { profile, credits } from '../lib/api';
import ExperienceCard from '../components/ExperienceCard';

export default function DashboardPage() {
  const { user } = useAuth();
  const { t } = useLocale();
  const navigate = useNavigate();
  const [stats, setStats] = useState({});
  const [badges, setBadges] = useState([]);
  const [balance, setBalance] = useState(null);
  const [myExps, setMyExps] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) { navigate('/login'); return; }
    Promise.all([profile.get(user.id), credits.balance(), profile.contributions(user.id)])
      .then(([p, b, c]) => {
        setStats(p?.stats || {});
        setBadges(p?.badges || []);
        setBalance(b);
        setMyExps(c?.items || []);
      }).catch(() => {})
      .finally(() => setLoading(false));
  }, [user, navigate]);

  if (!user) return null;
  if (loading) return <div className="max-w-4xl mx-auto px-4 py-16 text-center text-sm text-gray-400">{t('common.loading')}</div>;

  return (
    <div className="max-w-4xl mx-auto px-4 lg:px-8 py-6">
      <div className="flex items-center justify-between border-b border-[#d1d9e0] pb-4 mb-6">
        <div>
          <h1 className="text-xl font-semibold text-[#24292f]">{user.username}</h1>
          <p className="text-sm text-gray-500">{t('dashboard.title')}</p>
        </div>
        <Link to={`/user/${user.id}`} className="btn-secondary text-xs no-underline hover:no-underline">{t('dashboard.viewPublic')}</Link>
      </div>

      <div className="grid grid-cols-5 gap-3 mb-6">
        {[
          { n: stats.total_shares || 0, l: t('stats.shares') },
          { n: stats.total_upvotes || 0, l: t('stats.upvotes') },
          { n: stats.total_adoptions || 0, l: t('stats.adoptions') },
          { n: stats.total_views || 0, l: t('stats.views') },
          { n: balance?.credits ?? 0, l: t('stats.credits') },
        ].map(s => (
          <div key={s.l} className="card text-center !py-3">
            <div className="text-lg font-semibold text-[#24292f]">{s.n}</div>
            <div className="text-xs text-gray-500">{s.l}</div>
          </div>
        ))}
      </div>

      {badges.length > 0 && (
        <div className="card mb-6">
          <h2 className="text-sm font-semibold text-[#24292f] mb-2">{t('dashboard.badges')}</h2>
          <div className="flex flex-wrap gap-2">
            {badges.map(b => (
              <span key={b.badge_type} className="label bg-[#f6f8fa] text-gray-700 border border-[#d1d9e0]">{b.icon} {b.badge_name}</span>
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-3 mb-6">
        <Link to="/share" className="card text-center !py-4 no-underline hover:no-underline hover:bg-[#f6f8fa]">
          <div className="text-sm font-medium text-[#24292f]">{t('dashboard.shareExp')}</div>
        </Link>
        <Link to="/explore" className="card text-center !py-4 no-underline hover:no-underline hover:bg-[#f6f8fa]">
          <div className="text-sm font-medium text-[#24292f]">{t('dashboard.searchSolution')}</div>
        </Link>
        <Link to="/leaderboard" className="card text-center !py-4 no-underline hover:no-underline hover:bg-[#f6f8fa]">
          <div className="text-sm font-medium text-[#24292f]">{t('leaderboard.title')}</div>
        </Link>
      </div>

      <h2 className="text-sm font-semibold text-[#24292f] mb-3">{t('dashboard.myShares')} ({myExps.length})</h2>
      {myExps.length === 0 ? (
        <div className="card text-center py-8">
          <p className="text-sm text-gray-400 mb-3">{t('dashboard.noShares')}</p>
          <Link to="/share" className="btn-primary no-underline hover:no-underline">{t('dashboard.firstShare')}</Link>
        </div>
      ) : (
        <div className="card">
          {myExps.slice(0, 10).map(exp => <ExperienceCard key={exp.id} exp={exp} />)}
        </div>
      )}
    </div>
  );
}
