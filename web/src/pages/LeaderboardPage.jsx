import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useLocale } from '../context/LocaleContext';
import { community } from '../lib/api';

export default function LeaderboardPage() {
  const { t } = useLocale();
  const [leaders, setLeaders] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    community.leaderboard(50)
      .then(r => setLeaders(r?.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="max-w-3xl mx-auto px-4 lg:px-8 py-6">
      <div className="border-b border-[#d1d9e0] pb-4 mb-4">
        <h1 className="text-xl font-semibold text-[#24292f]">{t('leaderboard.title')}</h1>
        <p className="text-sm text-gray-500 mt-1">{t('leaderboard.subtitle')}</p>
      </div>

      {loading ? (
        <div className="text-center py-16 text-sm text-gray-400">{t('common.loading')}</div>
      ) : leaders.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-500">{t('leaderboard.noData')}</div>
      ) : (
        <div className="card !p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#d1d9e0] bg-[#f6f8fa] text-left text-xs text-gray-500">
                <th className="py-2 px-4 font-medium w-12">#</th>
                <th className="py-2 px-4 font-medium">{t('leaderboard.user')}</th>
                <th className="py-2 px-4 font-medium text-right">{t('stats.shares')}</th>
                <th className="py-2 px-4 font-medium text-right">{t('stats.upvotes')}</th>
                <th className="py-2 px-4 font-medium text-right">{t('stats.adoptions')}</th>
              </tr>
            </thead>
            <tbody>
              {leaders.map((l, i) => (
                <tr key={l.user_id} className="border-b border-[#d1d9e0] last:border-b-0 hover:bg-[#f6f8fa]">
                  <td className="py-2.5 px-4 text-gray-400 font-medium">{i + 1}</td>
                  <td className="py-2.5 px-4">
                    <Link to={`/user/${l.user_id}`} className="font-medium">
                      {l.display_name || l.username}
                    </Link>
                  </td>
                  <td className="py-2.5 px-4 text-right text-gray-600">{l.share_count}</td>
                  <td className="py-2.5 px-4 text-right text-gray-600">{l.total_upvotes}</td>
                  <td className="py-2.5 px-4 text-right text-gray-600">{l.total_adoptions}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
