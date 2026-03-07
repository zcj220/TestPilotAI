// FreshMart 购物车页
Page({
  data: {
    cart: [],
    subtotal: '0.00',
    itemCount: 0,
    message: '',
    msgClass: '',
  },

  onShow() {
    const app = getApp();
    const cart = app.globalData.cart || [];

    // 合并相同商品
    const merged = {};
    cart.forEach(item => {
      if (merged[item.id]) {
        merged[item.id].qty += 1;
      } else {
        merged[item.id] = { ...item };
      }
    });
    const mergedList = Object.values(merged);

    // BUG 5（隐蔽）: 小计计算有精度问题
    // 每个商品的 actualPrice * qty 累加时，直接用浮点加法
    // 例：10.63 * 3 = 31.889999... 而非 31.89
    let subtotal = 0;
    mergedList.forEach(item => {
      subtotal += item.actualPrice * item.qty;
    });

    this.setData({
      cart: mergedList,
      subtotal: subtotal.toFixed(2),
      itemCount: cart.length,
    });
  },

  // 删除商品
  removeItem(e) {
    const id = e.currentTarget.dataset.id;
    const app = getApp();
    app.globalData.cart = app.globalData.cart.filter(item => item.id !== id);
    this.onShow();
    this.setData({ message: '已移除', msgClass: 'success' });
  },

  // 去结算
  goCheckout() {
    if (this.data.cart.length === 0) {
      this.setData({ message: '购物车为空', msgClass: 'err' });
      return;
    }
    wx.navigateTo({ url: '/pages/checkout/checkout' });
  },

  // 继续购物
  goBack() {
    wx.navigateBack();
  },
})
