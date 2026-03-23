import { Link } from 'react-router-dom';
import { useLocale } from '../context/LocaleContext';

const content = {
  zh: {
    title: '服务条款', updated: '最后更新：2025年3月',
    intro: '欢迎使用 TestPilot AI（以下简称"本服务"），由温州芯造科技有限公司提供。使用本服务即表示您同意以下条款。',
    refundText: '首次付款后 7 天内如对服务不满意，可申请全额退款。详见', refundLink: '退款政策',
    emailText: '如有疑问，请发邮件至：',
    sections: [
      { h: '1. 服务说明', p: 'TestPilot AI 是一款面向开发者的 AI 自动化测试工具，以 VS Code 插件形式提供，支持 Web、Android、iOS、小程序及桌面应用的自动化测试用例生成与执行。' },
      { h: '2. 账户与使用', p: '您需注册账户方可使用本服务。您有责任保护账户安全，并对账户下的所有行为负责。禁止将账户转让或共享给他人。' },
      { h: '3. 付款与订阅', p: '本服务提供免费版及付费订阅计划。付费计划按订阅周期（月付或年付）收费，费用通过 Paddle 平台处理。订阅到期前如未取消，将自动续费。' },
      { h: '4. 退款政策', type: 'refund' },
      { h: '5. 知识产权', p: '本服务的软件、文档、品牌标识等所有知识产权归温州芯造科技有限公司所有。您生成的测试蓝本文件归您所有。' },
      { h: '6. 免责声明', p: '本服务按"现状"提供，不对特定用途的适用性作出保证。我们不对因使用本服务导致的间接损失承担责任，赔偿上限为您最近一个月支付的订阅费用。' },
      { h: '7. 服务变更与终止', p: '我们保留随时修改或终止服务的权利，重大变更将提前 30 天通知用户。您可随时在账户设置中取消订阅。' },
      { h: '8. 适用法律', p: '本条款受中华人民共和国法律管辖。如发生争议，双方应友好协商解决；协商不成的，提交温州市鹿城区人民法院。' },
      { h: '9. 联系我们', type: 'email' },
    ],
  },
  en: {
    title: 'Terms of Service', updated: 'Last updated: March 2025',
    intro: 'Welcome to TestPilot AI ("the Service"), provided by Wenzhou Xinzao Technology Co., Ltd. By using the Service, you agree to these terms.',
    refundText: 'You may request a full refund within 7 days of your first payment. See our', refundLink: 'Refund Policy',
    emailText: 'For questions, email us at:',
    sections: [
      { h: '1. Service Description', p: 'TestPilot AI is an AI-powered automated testing tool delivered as a VS Code extension, supporting Web, Android, iOS, Mini Program, and Desktop app testing.' },
      { h: '2. Account & Use', p: 'You must register to use the Service. You are responsible for all activity under your account. Sharing or transferring accounts is prohibited.' },
      { h: '3. Payment & Subscriptions', p: 'Paid plans are billed monthly or annually via Paddle and auto-renew unless cancelled before the renewal date.' },
      { h: '4. Refund Policy', type: 'refund' },
      { h: '5. Intellectual Property', p: "All software, docs, and branding belong to Wenzhou Xinzao Technology Co., Ltd. Blueprint files you generate are yours." },
      { h: '6. Disclaimer', p: 'The Service is provided "as is". Our liability is limited to the subscription fee paid in your most recent billing period.' },
      { h: '7. Changes & Termination', p: 'We may modify or terminate the Service with 30 days notice for major changes. You may cancel anytime in account settings.' },
      { h: '8. Governing Law', p: "These terms are governed by the laws of the People's Republic of China." },
      { h: '9. Contact', type: 'email' },
    ],
  },
};

export default function TermsPage() {
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
          {s.type === 'refund' && <p>{c.refundText} <Link to="/refund" className="text-blue-600 hover:underline">{c.refundLink}</Link>.</p>}
          {s.type === 'email' && <p>{c.emailText} <a href="mailto:support@xinzaoai.com" className="text-blue-600 hover:underline">support@xinzaoai.com</a></p>}
        </div>
      ))}
    </div>
  );
}
