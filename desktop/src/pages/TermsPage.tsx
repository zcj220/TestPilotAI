export default function TermsPage() {
  return (
    <div style={{ maxWidth: 800, margin: '0 auto', padding: '60px 24px', fontFamily: 'sans-serif', color: '#1a1a1a', lineHeight: 1.8 }}>
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>服务条款</h1>
      <p style={{ color: '#666', marginBottom: 40 }}>最后更新：2025年3月</p>

      <p>欢迎使用 TestPilot AI（以下简称"本服务"），由新造AI（xinzaoai.com）提供。使用本服务即表示您同意以下条款。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>1. 服务说明</h2>
      <p>TestPilot AI 是一款面向开发者的 AI 自动化测试工具，以 VS Code 插件形式提供，支持 Web、Android、iOS、小程序及桌面应用的自动化测试用例生成与执行。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>2. 账户与使用</h2>
      <p>您需注册账户方可使用本服务。您有责任保护账户安全，并对账户下的所有行为负责。禁止将账户转让或共享给他人。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>3. 付款与订阅</h2>
      <p>本服务提供免费版及付费订阅计划。付费计划按订阅周期（月付或年付）收费，费用通过 Paddle 平台处理。订阅到期前如未取消，将自动续费。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>4. 退款政策</h2>
      <p>首次付款后 7 天内如对服务不满意，可申请全额退款。超出 7 天后的费用原则上不予退还，但如因服务故障导致无法正常使用，我们将酌情处理。详见 <a href="/refund" style={{ color: '#2563eb' }}>退款政策页面</a>。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>5. 知识产权</h2>
      <p>本服务的软件、文档、品牌标识等所有知识产权归新造AI所有。您生成的测试蓝本文件归您所有。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>6. 免责声明</h2>
      <p>本服务按"现状"提供，不对特定用途的适用性作出保证。我们不对因使用本服务导致的间接损失承担责任，赔偿上限为您最近一个月支付的订阅费用。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>7. 服务变更与终止</h2>
      <p>我们保留随时修改或终止服务的权利，重大变更将提前 30 天通知用户。您可随时在账户设置中取消订阅。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>8. 适用法律</h2>
      <p>本条款受中华人民共和国法律管辖。</p>

      <h2 style={{ fontSize: 20, marginTop: 36 }}>9. 联系我们</h2>
      <p>如有疑问，请发邮件至：<a href="mailto:support@xinzaoai.com" style={{ color: '#2563eb' }}>support@xinzaoai.com</a></p>
    </div>
  );
}
