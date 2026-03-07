// FreshMart 订单结果页
Page({
  data: {
    total: '0.00',
    items: 0,
    delivery: '',
    orderId: '',
  },

  onLoad(options) {
    const orderId = 'FM' + Date.now().toString().slice(-8);
    this.setData({
      total: options.total || '0.00',
      items: parseInt(options.items) || 0,
      delivery: options.delivery === 'same_city' ? '同城配送' : '快递配送',
      orderId: orderId,
    });
  },

  goHome() {
    wx.navigateBack({ delta: 10 });
  },
})
