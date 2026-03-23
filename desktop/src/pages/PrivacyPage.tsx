export default function PrivacyPage() {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '60px 24px', fontFamily: 'sans-serif', color: '#1a1a1a', lineHeight: 1.8 }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>隐私政策</h1>
      <p style={{ color: '#666', marginBottom: 40 }}>最后更新：2025年3月</p>

      <p>新造AI（xinzaoai.com）非常重视您的隐私。本政策说明我们如何收集、使用和保护您的信息。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>1. 我们收集的信息</h2>
      <ul>
        <li><strong>账户信息</strong>：注册时提供的邮箱、用户名及密码（加密存储）。</li>
        <li><strong>使用数据</strong>：测试执行记录、蓝本文件、测试报告等，用于提供服务功能。</li>
        <li><strong>支付信息</strong>：付款由 Paddle 平台处理，我们不存储您的银行卡信息。</li>
        <li><strong>设备信息</strong>：浏览器类型、操作系统等基础日志信息，用于排查问题。</li>
      </ul>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>2. 信息使用方式</h2>
      <ul>
        <li>提供、维护和改进本服务</li>
        <li>处理订阅和付款</li>
        <li>发送服务通知和技术公告</li>
        <li>响应用户支持请求</li>
      </ul>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>3. 信息共享</h2>
      <p>我们不会向第三方出售您的个人信息。仅在以下情况下共享：</p>
      <ul>
        <li>支付处理：与 Paddle 共享必要的订单信息</li>
        <li>法律要求：依法配合政府或司法机关</li>
      </ul>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>4. 数据安全</h2>
      <p>我们采用行业标准的加密手段保护数据传输和存储安全。密码经过哈希处理，任何人（包括我们自己）均无法获取您的明文密码。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>5. Cookie</h2>
      <p>我们使用必要的 Cookie 维持登录状态。我们不使用第三方追踪 Cookie 进行广告投放。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>6. 您的权利</h2>
      <p>您可以随时登录账户查看、修改或删除您的个人信息。如需注销账户并删除所有数据，请联系我们。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>7. 数据留存</h2>
      <p>账户注销后，我们将在 30 天内删除您的个人数据，付款记录根据财务法规保留 7 年。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>8. 联系我们</h2>
      <p>如有隐私相关疑问，请发邮件至：<a href="mailto:support@xinzaoai.com" style={{ color: '#2563eb' }}>support@xinzaoai.com</a></p>
    </div>
  );
}
