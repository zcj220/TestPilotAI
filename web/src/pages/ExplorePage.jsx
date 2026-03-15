import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { community } from '../lib/api';
import { useLocale } from '../context/LocaleContext';
import { PLATFORMS } from '../lib/constants';
import ExperienceCard from '../components/ExperienceCard';
import Pagination from '../components/Pagination';

export default function ExplorePage() {
  const { t } = useLocale();
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState({ items: [], total: 0, page: 1, pages: 0 });
  const [loading, setLoading] = useState(true);

  const platform = searchParams.get('platform') || '';
  const search = searchParams.get('search') || '';
  const sortBy = searchParams.get('sort_by') || 'created_at';
  const page = parseInt(searchParams.get('page') || '1', 10);

  useEffect(() => {
    setLoading(true);
    const params = { page, per_page: 20 };
    if (platform) params.platform = platform;
    if (search) params.search = search;
    if (sortBy) params.sort_by = sortBy;
    community.list(params)
      .then(r => setData(r || { items: [], total: 0, page: 1, pages: 0 }))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [platform, search, sortBy, page]);

  function updateParam(key, value) {
    const p = new URLSearchParams(searchParams);
    if (value) p.set(key, value); else p.delete(key);
    p.set('page', '1');
    setSearchParams(p);
  }

  const [searchInput, setSearchInput] = useState(search);

  const sortOptions = ['created_at', 'upvotes', 'views', 'adoption'];

  return (
    <div className="max-w-[1280px] mx-auto px-4 lg:px-8 py-6">
      <div className="border-b border-[#d1d9e0] pb-4 mb-4">
        <h1 className="text-xl font-semibold text-[#24292f]">{t('explore.title')}</h1>
        <p className="text-sm text-gray-500 mt-1">{t('explore.subtitle')}</p>
      </div>

      <form onSubmit={e => { e.preventDefault(); updateParam('search', searchInput); }} className="mb-4">
        <div className="flex">
          <input
            type="text"
            className="flex-1 px-3 py-2 text-sm bg-white border border-[#d1d9e0] rounded-l-md
              focus:ring-2 focus:ring-[#24292f] focus:border-[#24292f] outline-none"
            placeholder={t('explore.searchPlaceholder')}
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
          />
          <button type="submit" className="px-4 py-2 bg-[#f6f8fa] border border-l-0 border-[#d1d9e0] rounded-r-md
            hover:bg-[#ebeef1] text-gray-600 text-sm cursor-pointer flex items-center gap-1.5">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor"><path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 1 1-1.06 1.06l-3.04-3.04ZM11.5 7a4.499 4.499 0 1 0-8.997 0A4.499 4.499 0 0 0 11.5 7Z"/></svg>
            {t('explore.searchBtn')}
          </button>
        </div>
      </form>

      <div className="flex gap-3 mb-4">
        <select className="input-field w-40" value={platform} onChange={e => updateParam('platform', e.target.value)}>
          <option value="">{t('explore.allPlatforms')}</option>
          {PLATFORMS.map(p => <option key={p.value} value={p.value}>{t(`platform.${p.value}`)}</option>)}
        </select>
        <select className="input-field w-40" value={sortBy} onChange={e => updateParam('sort_by', e.target.value)}>
          {sortOptions.map(s => <option key={s} value={s}>{t(`sort.${s}`)}</option>)}
        </select>
      </div>

      {(platform || search) && (
        <div className="flex items-center gap-2 mb-4 text-sm">
          {platform && (
            <button onClick={() => updateParam('platform', '')} className="label bg-[#f6f8fa] text-gray-700 border border-[#d1d9e0] cursor-pointer hover:bg-[#ebeef1]">
              {t(`platform.${platform}`)} ✕
            </button>
          )}
          {search && (
            <button onClick={() => { updateParam('search', ''); setSearchInput(''); }} className="label bg-[#f6f8fa] text-gray-700 border border-[#d1d9e0] cursor-pointer hover:bg-[#ebeef1]">
              &quot;{search}&quot; ✕
            </button>
          )}
        </div>
      )}

      {loading ? (
        <div className="text-center py-16 text-gray-400 text-sm">{t('explore.loading')}</div>
      ) : data.items.length === 0 ? (
        <div className="text-center py-16 text-sm text-gray-500">{t('explore.noResults')}</div>
      ) : (
        <>
          <div className="text-xs text-gray-500 mb-2">{data.total} {t('explore.results')}</div>
          <div className="card">
            {data.items.map(exp => <ExperienceCard key={exp.id} exp={exp} />)}
          </div>
          <Pagination page={data.page} pages={data.pages} onPageChange={p => updateParam('page', String(p))} />
        </>
      )}
    </div>
  );
}
