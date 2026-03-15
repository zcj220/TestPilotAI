import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useLocale } from '../context/LocaleContext';
import { billing } from '../lib/api';

const DEFAULT_PLANS = [
  { type: 'free', name_zh: '免费版', name_en: 'Free', price_monthly: 0, credits_monthly: 50, max_concurrent_tests: 1,
    features_zh: ['基础测试', 'Bug 检测', '测试报告'], features_en: ['Basic testing', 'Bug detection', 'Test reports'] },
  { type: 'basic', name_zh: '基础版', name_en: 'Basic', price_monthly: 19, credits_monthly: 500, max_concurrent_tests: 2,
    features_zh: ['基础测试', 'Bug 检测', '测试报告', '自动修复', '历史记录'], features_en: ['Basic testing', 'Bug detection', 'Test reports', 'Auto repair', 'History'] },
  { type: 'pro', name_zh: '专业版', name_en: 'Pro', price_monthly: 59, credits_monthly: 2000, max_concurrent_tests: 5,
    features_zh: ['全部基础功能', '交叉验证', 'VNC 实时观看', '优先支持'], features_en: ['All basic features', 'Cross validation', 'Live VNC', 'Priority support'] },
  { type: 'team', name_zh: '团队版', name_en: 'Team', price_monthly: 199, credits_monthly: 10000, max_concurrent_tests: 10,
    features_zh: ['全部功能', '团队协作', 'API 访问', '专属支持'], features_en: ['All features', 'Team collaboration', 'API access', 'Dedicated support'] },
];

export default function PricingPage() {
  const { t, locale } = useLocale();
  const [plans] = useState(DEFAULT_PLANS);

  return (
    <div className="max-w-4xl mx-auto px-4 lg:px-8 py-10">
      <div className="text-center mb-10">
        <h1 className="text-xl font-semibold text-[#24292f]">{t('pricing.title')}</h1>
        <p className="text-sm text-gray-500 mt-2">{t('pricing.subtitle')}</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {plans.map(plan => (
          <div key={plan.type} className="card flex flex-col">
            <h3 className="font-semibold text-[#24292f]">{locale === 'zh' ? plan.name_zh : plan.name_en}</h3>
            <div className="mt-3 mb-1">
              <span className="text-2xl font-bold text-[#24292f]">
                {plan.price_monthly === 0 ? t('pricing.free') : `¥${plan.price_monthly}`}
              </span>
              {plan.price_monthly > 0 && <span className="text-xs text-gray-500">{t('pricing.perMonth')}</span>}
            </div>
            <div className="text-xs text-gray-500 mb-4">{plan.credits_monthly.toLocaleString()} {t('pricing.creditsPerMonth')}</div>
            <ul className="space-y-1.5 flex-1 mb-4">
              {(locale === 'zh' ? plan.features_zh : plan.features_en).map(f => (
                <li key={f} className="text-xs text-gray-600 flex items-start gap-1.5">
                  <span className="text-gray-400">✓</span>{f}
                </li>
              ))}
            </ul>
            <Link to={plan.type === 'free' ? '/login?tab=register' : '/login'}
              className="btn-secondary text-center no-underline hover:no-underline">
              {plan.price_monthly === 0 ? t('pricing.startFree') : t('pricing.choosePlan')}
            </Link>
          </div>
        ))}
      </div>
    </div>
  );
}
