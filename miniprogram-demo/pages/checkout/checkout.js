// FreshMart 结算页 - 含Bug3(优惠券) + Bug4(配送费)
Page({
  data: {
    cart: [],
    subtotal: 0,
    deliveryType: '',       // same_city / express
    deliveryFee: 0,
    address: '',
    coupon: null,
    couponDiscount: 0,
    total: '0.00',
    coupons: [],
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

    let subtotal = 0;
    Object.values(merged).forEach(item => {
      subtotal += item.actualPrice * item.qty;
    });

    this.setData({
      cart: Object.values(merged),
      subtotal: subtotal,
      coupons: app.globalData.coupons,
      address: app.globalData.address,
      deliveryType: app.globalData.deliveryType,
    });
    this.calcTotal();
  },

  // 选择地址
  onAddressInput(e) {
    const addr = e.detail.value;
    getApp().globalData.address = addr;
    this.setData({ address: addr });
  },

  // 选择配送方式
  onDeliveryChange(e) {
    const types = ['same_city', 'express'];
    const type = types[e.detail.value];
    getApp().globalData.deliveryType = type;

    // BUG 4 已修复: 同城配送免费(0元)
    let fee = 0;
    if (type === 'same_city') {
      fee = 0;
    } else if (type === 'express') {
      fee = 10;
    }

    this.setData({ deliveryType: type, deliveryFee: fee });
    this.calcTotal();
  },

  // 选择优惠券
  onCouponTap(e) {
    const couponId = e.currentTarget.dataset.id;
    const coupon = this.data.coupons.find(c => c.id === couponId);

    // BUG 3（隐蔽）: 满减判断条件有偏差
    // "满100减20" 应该是 subtotal >= 100 就能用
    // 但实际用的是 subtotal > threshold（严格大于）
    // 所以 subtotal 刚好 = 100 时不能用（差1分钱）
    if (this.data.subtotal > coupon.threshold) {
      this.setData({ coupon: coupon, couponDiscount: coupon.discount });
      getApp().globalData.coupon = coupon;
      this.setData({ message: '已使用 ' + coupon.name, msgClass: 'success' });
    } else {
      this.setData({
        message: '未满' + coupon.threshold + '元，不能使用此优惠券',
        msgClass: 'err',
      });
    }
    this.calcTotal();
  },

  // 计算总价
  calcTotal() {
    const { subtotal, deliveryFee, couponDiscount } = this.data;
    const total = subtotal + deliveryFee - couponDiscount;
    this.setData({ total: total.toFixed(2) });
  },

  // 提交订单
  submitOrder() {
    if (!this.data.address) {
      this.setData({ message: '请填写收货地址', msgClass: 'err' });
      return;
    }
    if (!this.data.deliveryType) {
      this.setData({ message: '请选择配送方式', msgClass: 'err' });
      return;
    }

    // 清空购物车
    getApp().globalData.cart = [];
    wx.navigateTo({
      url: '/pages/order/order?total=' + this.data.total +
           '&items=' + this.data.cart.length +
           '&delivery=' + this.data.deliveryType,
    });
  },
})
