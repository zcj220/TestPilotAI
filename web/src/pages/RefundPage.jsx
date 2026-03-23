import { useLocale } from '../context/LocaleContext';

const content = {
  zh: {
    title: '退款政策', updated: '最后更新：2025年3月',
    intro: '我们希望您满意 TestPilot AI 的服务。如果您对服务不满意，请参阅以下退款说明。',
    sections: [
      { h: '1. 7 天无理由退款', p: '首次订阅付款后 7 个自然日内，无论任何原因，均可申请全额退款。退款将退回原支付方式，通常在 5-10 个工作日内到账。' },
      { h: '2. 超过 7 天的情况', p: '超过 7 天后的订阅费用原则上不予退还。以下情况除外：', items: ['因本服务严重故障（非您的网络或设备原因）导致连续 72 小时以上无法正常使用', '我们单方面大幅削减服务功能，且未提前告知', '重复扣款或账单系统错误'], after: '如遇上述情况，我们将按实际无法使用的时长按比例退款。' },
      { h: '3. 年费订阅', p: '年费订阅在购买后 7 天内可全额退款。超过 7 天后如提出退款申请，我们将按已使用月数扣除相应费用后退还剩余金额。' },
      { h: '4. 不适用退款的情形', items: ['免费版或试用期账户', '因违反服务条款被终止的账户', '已明确使用过大量 AI 调用额度（超出正常试用范围）'] },
      { h: '5. 如何申请退款', type: 'contact', pre: '发送邮件至', post: '，注明：', items: ['您的账户邮箱', '订单号（可在 Paddle 收据邮件中找到）', '退款原因（选填）'], after: '我们将在 2 个工作日内回复并处理。' },
    ],
  },
  en: {
    title: 'Refund Policy', updated: 'Last updated: March 2025',
    intro: 'We want you to be satisfied with TestPilot AI. If you are not, please review the refund information below.',
    sections: [
      { h: '1. 7-Day No-Questions-Asked Refund', p: 'Within 7 calendar days of your first subscription payment, you may request a full refund for any reason. Refunds are returned to the original payment method and typically arrive within 5-10 business days.' },
      { h: '2. After 7 Days', p: 'Subscription fees after 7 days are generally non-refundable, with the following exceptions:', items: ['A serious service outage (not caused by your network or device) lasting more than 72 consecutive hours', 'We unilaterally and significantly reduce service features without prior notice', 'Duplicate charges or billing system errors'], after: 'In these cases, we will issue a pro-rated refund for the unusable period.' },
      { h: '3. Annual Subscriptions', p: 'Annual subscriptions may be fully refunded within 7 days of purchase. After 7 days, refund requests will be prorated based on months already used.' },
      { h: '4. Non-Refundable Cases', items: ['Free or trial accounts', 'Accounts terminated for violating the Terms of Service', 'Accounts that have consumed a significant amount of AI credits beyond normal trial use'] },
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
