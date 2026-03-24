import { useLocale } from '../context/LocaleContext';

const content = {
  zh: {
    title: '退款政策', updated: '最后更新：2026年3月',
    intro: '我们希望您满意 TestPilot AI 的服务。如果您对服务不满意，请参阅以下退款说明。我们的退款政策符合 Paddle 作为授权转售商的标准退款条款。',
    sections: [
      { h: '1. 14 天无理由退款', p: '首次订阅付款后 14 个自然日内，无论任何原因，均可申请全额退款。退款将退回原支付方式，通常在 5-10 个工作日内到账。' },
      { h: '2. 超过 14 天的情况', p: '超过 14 天后的订阅费用原则上不予退还。如遇以下特殊情况，请联系我们协商处理：', items: ['因本服务严重故障（非您的网络或设备原因）导致长时间无法正常使用', '重复扣款或账单系统错误'], after: '如遇上述情况，我们将合理评估并酌情处理退款申请。' },
      { h: '3. 年费订阅', p: '年费订阅在购买后 14 天内可全额退款。超过 14 天后如提出退款申请，我们将按实际情况合理处理。' },
      { h: '4. 如何申请退款', type: 'contact', pre: '发送邮件至', post: '，注明：', items: ['您的账户邮箱', '订单号（可在 Paddle 收据邮件中找到）', '退款原因（选填）'], after: '我们将在 2 个工作日内回复并处理。' },
    ],
  },
  en: {
    title: 'Refund Policy', updated: 'Last updated: March 2026',
    intro: 'We want you to be satisfied with TestPilot AI. If you are not, please review the refund information below. Our refund policy complies with the standard refund terms of Paddle, our authorised reseller.',
    sections: [
      { h: '1. 14-Day No-Questions-Asked Refund', p: 'Within 14 calendar days of your first subscription payment, you may request a full refund for any reason. Refunds are returned to the original payment method and typically arrive within 5-10 business days.' },
      { h: '2. After 14 Days', p: 'Subscription fees after 14 days are generally non-refundable. However, if you experience any of the following, please contact us and we will review your case:', items: ['A serious service outage (not caused by your network or device) affecting your ability to use the service', 'Duplicate charges or billing system errors'], after: 'We will assess these situations fairly and handle refund requests on a case-by-case basis.' },
      { h: '3. Annual Subscriptions', p: 'Annual subscriptions may be fully refunded within 14 days of purchase. After 14 days, refund requests will be handled reasonably based on the circumstances.' },
      { h: '4. EU / EEA / UK Consumers', p: 'If you are a consumer in the EU, EEA, or UK, you have the statutory right to withdraw from your purchase within 14 days of completing a transaction, in accordance with applicable consumer protection laws. To exercise this right, simply contact us within 14 days — no reason required.' },
      { h: '5. How to Request a Refund', type: 'contact', pre: 'Email us at', post: ' and include:', items: ['Your account email', 'Order number (found in your Paddle receipt email)', 'Reason for refund (optional)'], after: 'We will respond and process your request within 2 business days.' },
    ],
  },
};

export default function RefundPage() {
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
          {s.type === 'contact'
            ? <p>{s.pre} <a href="mailto:support@xinzaoai.com" className="text-blue-600 hover:underline">support@xinzaoai.com</a>{s.post}</p>
            : s.p && <p>{s.p}</p>}
          {s.items && <ul className="list-disc pl-5 mt-2 space-y-1">{s.items.map(i => <li key={i}>{i}</li>)}</ul>}
          {s.after && <p className="mt-2">{s.after}</p>}
        </div>
      ))}
    </div>
  );
}
