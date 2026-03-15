import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { community } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { useLocale } from '../context/LocaleContext';
import { PLATFORM_MAP, DIFFICULTY_MAP } from '../lib/constants';

export default function ExperienceDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const { t, locale } = useLocale();
  const [exp, setExp] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    community.get(id)
      .then(r => setExp(r?.experience || null))
      .catch(() => setExp(null))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleVote(type) {
    if (!user) return;
    try {
      await community.vote(id, type);
      const r = await community.get(id);
      setExp(r?.experience || exp);
    } catch {}
  }

  if (loading) return <div className="max-w-3xl mx-auto px-4 py-16 text-center text-sm text-gray-400">{t('common.loading')}</div>;

  if (!exp) return (
    <div className="max-w-3xl mx-auto px-4 py-16 text-center">
      <p className="text-gray-500 text-sm">{t('detail.notFound')}</p>
      <Link to="/explore" className="text-sm mt-2 inline-block">{t('detail.back')}</Link>
    </div>
  );

  const platform = PLATFORM_MAP[exp.platform] || { label: exp.platform };
  const difficulty = DIFFICULTY_MAP[exp.difficulty] || DIFFICULTY_MAP.medium;

  return (
    <div className="max-w-3xl mx-auto px-4 lg:px-8 py-6">
      <div className="text-sm text-gray-500 mb-4">
        <Link to="/explore" className="hover:underline">{t('explore.title')}</Link>
        <span className="mx-1 text-gray-300">/</span>
        <span className="text-gray-700">{exp.title}</span>
      </div>

      <div className="border-b border-[#d1d9e0] pb-4 mb-5">
        <h1 className="text-xl font-semibold text-[#24292f] mb-3">{exp.title}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`label ${difficulty.color}`}>{t(`difficulty.${exp.difficulty}`)}</span>
          <span className="label bg-[#f6f8fa] text-gray-600 border border-[#d1d9e0]">{t(`platform.${exp.platform}`)}</span>
          {exp.framework && <span className="label bg-[#f6f8fa] text-gray-600 border border-[#d1d9e0]">{exp.framework}</span>}
          {exp.error_type && <span className="label bg-[#ffebe9] text-[#cf222e]">{exp.error_type}</span>}
          {(exp.tags || []).map(tag => (
            <span key={tag} className="label bg-[#f6f8fa] text-gray-500 border border-[#d1d9e0]">{tag}</span>
          ))}
        </div>
      </div>

      <section className="mb-6">
        <h2 className="text-sm font-semibold text-[#24292f] mb-2">{t('detail.problem')}</h2>
        <div className="text-sm text-gray-700 whitespace-pre-wrap bg-[#f6f8fa] border border-[#d1d9e0] rounded-md p-4">{exp.problem_desc}</div>
      </section>

      <section className="mb-6">
        <h2 className="text-sm font-semibold text-[#24292f] mb-2">{t('detail.solution')}</h2>
        <div className="text-sm text-gray-700 whitespace-pre-wrap bg-[#f6f8fa] border border-[#d1d9e0] rounded-md p-4">{exp.solution_desc}</div>
      </section>

      {exp.root_cause && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-[#24292f] mb-2">{t('detail.rootCause')}</h2>
          <div className="text-sm text-gray-700 whitespace-pre-wrap bg-[#f6f8fa] border border-[#d1d9e0] rounded-md p-4">{exp.root_cause}</div>
        </section>
      )}

      {exp.code_snippet && (
        <section className="mb-6">
          <h2 className="text-sm font-semibold text-[#24292f] mb-2">{t('detail.code')}</h2>
          <pre className="text-sm bg-[#24292f] text-[#e6edf3] p-4 rounded-md overflow-x-auto"><code>{exp.code_snippet}</code></pre>
        </section>
      )}

      <div className="flex items-center gap-2 py-4 border-t border-b border-[#d1d9e0] mb-4">
        <button onClick={() => handleVote('upvote')} disabled={!user}
          className="btn-secondary !text-xs flex items-center gap-1 disabled:opacity-40">
          👍 {exp.upvote_count}
        </button>
        <button onClick={() => handleVote('downvote')} disabled={!user}
          className="btn-secondary !text-xs flex items-center gap-1 disabled:opacity-40">
          👎 {exp.downvote_count}
        </button>
        <button onClick={() => handleVote('adopt')} disabled={!user}
          className="btn-secondary !text-xs flex items-center gap-1 !bg-[#dafbe1] !text-[#1a7f37] !border-[#aceebb] disabled:opacity-40">
          ✅ {t('detail.adopt')} {exp.adoption_count}
        </button>
        <span className="ml-auto text-xs text-gray-400">
          {exp.view_count} {t('detail.views')} · {exp.created_at ? new Date(exp.created_at).toLocaleDateString(locale === 'zh' ? 'zh-CN' : 'en-US') : ''}
        </span>
      </div>

      <div className="text-sm">
        <Link to={`/user/${exp.user_id}`}>{t('detail.authorPage')}</Link>
      </div>
    </div>
  );
}
