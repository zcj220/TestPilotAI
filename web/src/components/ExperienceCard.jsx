import { Link } from 'react-router-dom';
import { useLocale } from '../context/LocaleContext';
import { PLATFORM_MAP, DIFFICULTY_MAP } from '../lib/constants';

export default function ExperienceCard({ exp }) {
  const { t } = useLocale();
  const platform = PLATFORM_MAP[exp.platform] || { icon: '📦', label: exp.platform };
  const difficulty = DIFFICULTY_MAP[exp.difficulty] || DIFFICULTY_MAP.medium;

  return (
    <div className="border-b border-[#d1d9e0] py-4 first:pt-0 last:border-b-0">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <Link to={`/experience/${exp.id}`} className="font-semibold text-[#24292f] hover:underline text-base leading-tight">
            {exp.title}
          </Link>
          <p className="text-gray-500 text-xs mt-1 line-clamp-2">{exp.problem_desc}</p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className={`label ${difficulty.color}`}>{t(`difficulty.${exp.difficulty}`)}</span>
            <span className="label bg-[#f6f8fa] text-gray-600 border border-[#d1d9e0]">{t(`platform.${exp.platform}`)}</span>
            {exp.framework && (
              <span className="label bg-[#f6f8fa] text-gray-600 border border-[#d1d9e0]">{exp.framework}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400 shrink-0 pt-1">
          <span>👍 {exp.upvote_count}</span>
          <span>✅ {exp.adoption_count}</span>
        </div>
      </div>
    </div>
  );
}
