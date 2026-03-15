export const PLATFORMS = [
  { value: 'web', label: 'Web', icon: '🌐' },
  { value: 'android', label: 'Android', icon: '🤖' },
  { value: 'ios', label: 'iOS', icon: '🍎' },
  { value: 'miniprogram', label: 'Mini Program', icon: '💬' },
  { value: 'desktop', label: 'Desktop', icon: '🖥️' },
];

export const DIFFICULTIES = [
  { value: 'easy', color: 'bg-[#dafbe1] text-[#1a7f37]' },
  { value: 'medium', color: 'bg-[#fff8c5] text-[#9a6700]' },
  { value: 'hard', color: 'bg-[#ffebe9] text-[#cf222e]' },
];

export const SORT_OPTIONS = [
  { value: 'created_at' },
  { value: 'upvotes' },
  { value: 'views' },
  { value: 'adoption' },
];

export const PLATFORM_MAP = Object.fromEntries(PLATFORMS.map(p => [p.value, p]));
export const DIFFICULTY_MAP = Object.fromEntries(DIFFICULTIES.map(d => [d.value, d]));
