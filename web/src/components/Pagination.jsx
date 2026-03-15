import { useLocale } from '../context/LocaleContext';

export default function Pagination({ page, pages, onPageChange }) {
  const { t } = useLocale();
  if (pages <= 1) return null;

  const items = [];
  const start = Math.max(1, page - 2);
  const end = Math.min(pages, page + 2);
  if (start > 1) { items.push(1); if (start > 2) items.push('...'); }
  for (let i = start; i <= end; i++) items.push(i);
  if (end < pages) { if (end < pages - 1) items.push('...'); items.push(pages); }

  return (
    <div className="flex items-center justify-center gap-1 mt-6 text-sm">
      <button onClick={() => onPageChange(page - 1)} disabled={page <= 1}
        className="px-3 py-1 rounded-md border border-[#d1d9e0] text-[#24292f] hover:bg-[#f6f8fa] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer">
        {t('common.prev')}
      </button>
      {items.map((item, i) =>
        item === '...' ? <span key={`d${i}`} className="px-1 text-gray-400">…</span> : (
          <button key={item} onClick={() => onPageChange(item)}
            className={`w-8 h-8 rounded-md border text-sm cursor-pointer ${
              item === page ? 'bg-[#24292f] text-white border-[#24292f]' : 'border-[#d1d9e0] text-[#24292f] hover:bg-[#f6f8fa]'
            }`}>{item}</button>
        )
      )}
      <button onClick={() => onPageChange(page + 1)} disabled={page >= pages}
        className="px-3 py-1 rounded-md border border-[#d1d9e0] text-[#24292f] hover:bg-[#f6f8fa] disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer">
        {t('common.next')}
      </button>
    </div>
  );
}
