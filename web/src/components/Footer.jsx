import { Link } from 'react-router-dom';
import { useLocale } from '../context/LocaleContext';

export default function Footer() {
  const { t } = useLocale();
  return (
    <footer className="border-t border-[#d1d9e0] mt-auto">
      <div className="max-w-[1280px] mx-auto px-4 lg:px-8 py-10">
        <div className="flex flex-col md:flex-row justify-between gap-8 text-sm text-gray-500">
          <div className="space-y-1">
            <div className="font-medium text-[#24292f] text-xs">温州芯造科技有限公司</div>
            <div className="text-xs">Wenzhou Xinzao Technology Co., Ltd</div>
            <div className="text-xs">地址：浙江省温州市鹿城区矮登桥128号11幢1011室D</div>
            <div className="text-xs mt-2">
              <a href="https://beian.miit.gov.cn" target="_blank" rel="noreferrer"
                className="text-gray-400 hover:text-gray-600 no-underline hover:no-underline">
                ICP主体备案号：浙ICP备2026006058号-1
              </a>
            </div>
            <div className="text-xs">
              <a href="https://www.beian.gov.cn" target="_blank" rel="noreferrer"
                className="text-gray-400 hover:text-gray-600 no-underline hover:no-underline">
                公安备案：浙公网安备33030202002335号
              </a>
            </div>
            <div className="text-xs text-gray-400">© 2026 TestPilot AI (测试领航员 AI)</div>
          </div>
          <div className="flex flex-wrap gap-6 items-start">
            <Link to="/explore" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.explore')}</Link>
            <Link to="/pricing" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.pricing')}</Link>
            <Link to="/leaderboard" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.leaderboard')}</Link>
            <Link to="/terms" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.terms')}</Link>
            <Link to="/privacy" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.privacy')}</Link>
            <Link to="/refund" className="text-gray-500 hover:text-gray-900 no-underline hover:no-underline">{t('footer.refund')}</Link>
            <a href="https://marketplace.visualstudio.com/items?itemName=testpilot-ai.testpilot-ai"
              target="_blank" rel="noreferrer"
              className="text-[#0969da] hover:text-[#0550ae] no-underline hover:no-underline font-medium">
              ↓ {t('footer.download')}
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
