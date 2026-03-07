Page({
  data: {
    cart: [],
    total: "0.00",
    message: "",
    msgClass: ""
  },

  onShow() {
    const app = getApp();
    const cart = app.globalData.cart || [];
    let total = 0;
    cart.forEach(item => { total += item.actualPrice; });
    this.setData({
      cart: cart,
      total: total.toFixed(2)
    });
  },

  checkout() {
    if (this.data.cart.length === 0) {
      this.setData({ message: "购物车为空", msgClass: "err" });
      return;
    }
    this.setData({ message: "订单提交成功!", msgClass: "success" });
    const app = getApp();
    app.globalData.cart = [];
    this.setData({ cart: [], total: "0.00" });
  }
})
