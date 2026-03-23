export default function RefundPage() {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '60px 24px', fontFamily: 'sans-serif', color: '#1a1a1a', lineHeight: 1.8 }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>退款政策</h1>
      <p style={{ color: '#666', marginBottom: 40 }}>最后更新：2025年3月</p>

      <p>我们希望您满意 TestPilot AI 的服务。如果您对服务不满意，请参阅以下退款说明。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>1. 7 天无理由退款</h2>
      <p>首次订阅付款后 <strong>7 个自然日内</strong>，无论任何原因，均可申请全额退款。退款将退回原支付方式，通常在 5-10 个工作日内到账。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>2. 超过 7 天的情况</h2>
      <p>超过 7 天后的订阅费用原则上不予退还。以下情况除外：</p>
      <ul>
        <li>因本服务严重故障（非您的网络或设备原因）导致连续 72 小时以上无法正常使用</li>
        <li>我们单方面大幅削减服务功能，且未提前告知</li>
        <li>重复扣款或账单系统错误</li>
      </ul>
      <p>如遇上述情况，我们将按实际无法使用的时长按比例退款。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>3. 年费订阅</h2>
      <p>年费订阅在购买后 7 天内可全额退款。超过 7 天后如提出退款申请，我们将按已使用月数扣除相应费用后退还剩余金额。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>4. 不适用退款的情形</h2>
      <ul>
        <li>免费版或试用期账户</li>
        <li>因违反服务条款被终止的账户</li>
        <li>已明确使用过大量 AI 调用额度（超出正常试用范围）</li>
      </ul>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>5. 如何申请退款</h2>
      <p>发送邮件至 <a href="mailto:support@xinzaoai.com" style={{ color: '#2563eb' }}>support@xinzaoai.com</a>，注明：</p>
      <ul>
        <li>您的账户邮箱</li>
        <li>订单号（可在 Paddle 收据邮件中找到）</li>
        <li>退款原因（选填）</li>
      </ul>
      <p>我们将在 2 个工作日内回复并处理。</p>
    </div>
  );
}
