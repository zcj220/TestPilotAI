import { useLocale } from '../context/LocaleContext';

const PLUGIN_VERSION = '1.0.0';
const DESKTOP_VERSION = '1.0.0';

const IDE_PLATFORMS = [
  {
    name: 'VS Code',
    icon: '⎈',
    url: 'https://marketplace.visualstudio.com/items?itemName=testpilot-ai.testpilot-ai',
    available: true,
  },
  { name: 'Windsurf', icon: '⎈', url: '#', available: false },
  { name: 'Cursor', icon: '⎈', url: '#', available: false },
];

const DESKTOP_PLATFORMS = [
  { name: 'Windows', icon: '⊞', ext: '.exe', available: false },
  { name: 'macOS', icon: '⌘', ext: '.dmg', available: false },
];

export default function DownloadPage() {
  const { t } = useLocale();

  return (
    <div className="max-w-[960px] mx-auto px-4 lg:px-8 py-12">
      <h1 className="text-2xl font-bold text-[#24292f]">{t('nav.download')}</h1>
      <p className="mt-2 text-sm text-gray-500">
        {t('download.subtitle')}
      </p>

      {/* IDE 插件 */}
      <section className="mt-10">
        <h2 className="text-base font-semibold text-[#24292f] mb-1">{t('home.idePlugin')}</h2>
        <p className="text-xs text-[#57606a] mb-4">{t('home.idePluginPlatforms')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {IDE_PLATFORMS.map(p => (
            <div key={p.name} className="card flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">{p.icon}</span>
                <span className="font-semibold text-sm text-[#24292f]">{p.name}</span>
              </div>
              <span className="text-xs font-mono text-[#57606a]">v{PLUGIN_VERSION}</span>
              {p.available ? (
                <a
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-primary no-underline hover:no-underline text-xs text-center"
                >
                  {t('home.installPlugin')}
                </a>
              ) : (
                <span className="text-xs text-[#57606a] border border-[#d1d9e0] rounded px-2 py-1 text-center">
                  {t('home.comingSoon')}
                </span>
              )}
            </div>
          ))}
        </div>
      </section>

      {/* 桌面版 */}
      <section className="mt-10">
        <h2 className="text-base font-semibold text-[#24292f] mb-1">{t('home.desktopApp')}</h2>
        <p className="text-xs text-[#57606a] mb-4">{t('home.desktopAppPlatforms')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {DESKTOP_PLATFORMS.map(p => (
            <div key={p.name} className="card flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span className="text-lg">{p.icon}</span>
                <span className="font-semibold text-sm text-[#24292f]">{p.name}</span>
              </div>
              <span className="text-xs font-mono text-[#57606a]">v{DESKTOP_VERSION} · {p.ext}</span>
              <span className="text-xs text-[#57606a] border border-[#d1d9e0] rounded px-2 py-1 text-center">
                {t('home.comingSoon')}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* 历史版本 */}
      <section className="mt-10">
        <h2 className="text-base font-semibold text-[#24292f] mb-4">{t('download.changelog')}</h2>
        <div className="card">
          <div className="flex items-center gap-3 py-2">
            <span className="font-mono text-xs bg-[#f6f8fa] border border-[#d1d9e0] rounded px-2 py-0.5">v1.0.0</span>
            <span className="text-xs text-[#57606a]">{t('download.initialRelease')}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
