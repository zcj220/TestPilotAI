import { useLocale } from '../context/LocaleContext';

const content = {
  zh: {
    title: '隐私政策', updated: '最后更新：2025年3月',
    intro: '温州芯造科技有限公司（xinzaoai.com）非常重视您的隐私。本政策说明我们如何收集、使用和保护您的信息。',
    emailText: '如有隐私相关疑问，请发邮件至：',
    sections: [
      { h: '1. 我们收集的信息', items: ['账户信息：注册时提供的邮箱、用户名及密码（加密存储）。', '使用数据：测试执行记录、蓝本文件、测试报告等，用于提供服务功能。', '支付信息：付款由 Paddle 平台处理，我们不存储您的银行卡信息。', '设备信息：浏览器类型、操作系统等基础日志信息，用于排查问题。'] },
      { h: '2. 信息使用方式', items: ['提供、维护和改进本服务', '处理订阅和付款', '发送服务通知和技术公告', '响应用户支持请求'] },
      { h: '3. 信息共享', p: '我们不会向第三方出售您的个人信息。仅在以下情况下共享：', items: ['支付处理：与 Paddle 共享必要的订单信息', '法律要求：依法配合政府或司法机关'] },
      { h: '4. 数据安全', p: '我们采用行业标准的加密手段保护数据传输和存储安全。密码经过哈希处理，任何人（包括我们自己）均无法获取您的明文密码。' },
      { h: '5. Cookie', p: '我们使用必要的 Cookie 维持登录状态。我们不使用第三方追踪 Cookie 进行广告投放。' },
      { h: '6. 您的权利', p: '您可以随时登录账户查看、修改或删除您的个人信息。如需注销账户并删除所有数据，请联系我们。' },
      { h: '7. 数据留存', p: '账户注销后，我们将在 30 天内删除您的个人数据，付款记录根据财务法规保留 7 年。' },
      { h: '8. 联系我们', type: 'email' },
    ],
  },
  en: {
    title: 'Privacy Policy', updated: 'Last updated: March 2025',
    intro: 'Wenzhou Xinzao Technology Co., Ltd. (xinzaoai.com) takes your privacy seriously. This policy explains how we collect, use, and protect your information.',
    emailText: 'For privacy-related questions, please email us at:',
    sections: [
      { h: '1. Information We Collect', items: ['Account information: Email, username, and password (encrypted) provided at registration.', 'Usage data: Test execution records, blueprint files, and test reports used to provide service features.', 'Payment information: Payments are processed by Paddle; we do not store your bank card details.', 'Device information: Basic logs such as browser type and operating system, used for troubleshooting.'] },
      { h: '2. How We Use Your Information', items: ['Provide, maintain, and improve the service', 'Process subscriptions and payments', 'Send service notifications and technical announcements', 'Respond to user support requests'] },
      { h: '3. Information Sharing', p: 'We do not sell your personal information to third parties. We share data only in the following cases:', items: ['Payment processing: sharing necessary order information with Paddle', 'Legal requirements: complying with government or judicial authorities as required by law'] },
      { h: '4. Data Security', p: 'We use industry-standard encryption to protect data in transit and at rest. Passwords are hashed and cannot be recovered by anyone, including us.' },
      { h: '5. Cookies', p: 'We use essential cookies to maintain your login session. We do not use third-party tracking cookies for advertising purposes.' },
      { h: '6. Your Rights', p: 'You may log in at any time to view, modify, or delete your personal information. To close your account and erase all data, please contact us.' },
      { h: '7. Data Retention', p: 'After account deletion, we will erase your personal data within 30 days. Payment records are retained for 7 years in accordance with financial regulations.' },
      { h: '8. Contact Us', type: 'email' },
    ],
  },
};

export default function PrivacyPage() {
  const { locale } = useLocale();
  const c = locale === 'en' ? content.en : content.zh;
  return (
    <div className="max-w-3xl mx-auto px-6 py-12 text-gray-800 leading-relaxed">
      <h1 className="text-2xl font-bold mb-2">{c.title}</h1>
      <p className="text-gray-400 mb-10 text-sm">{c.updated}</p>
      <p className="mb-6">{c.intro}</p>
      {c.sections.map((s) => (
        <div key={s.h} className="mt-8">
          <h2 className="text-lg font-semibold mb-2">{s.h}</h2>
          {s.p && <p>{s.p}</p>}
          {s.items && <ul className="list-disc pl-5 mt-2 space-y-1">{s.items.map(i => <li key={i}>{i}</li>)}</ul>}
          {s.type === 'email' && <p>{c.emailText} <a href="mailto:support@xinzaoai.com" className="text-blue-600 hover:underline">support@xinzaoai.com</a></p>}
        </div>
      ))}
    </div>
  );
}
