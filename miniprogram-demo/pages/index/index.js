// BuggyMini 首页 - 含4个预埋Bug
Page({
  data: {
    products: [
      { id: 1, name: "无线耳机", price: 299, displayPrice: "299" },
      { id: 2, name: "机械键盘", price: 199, displayPrice: "199" },
      { id: 3, name: "扩展坞", price: 159, displayPrice: "159" }
    ],
    cartCount: 0,
    cartTotal: "0",
    message: "",
    msgClass: ""
  },

  addToCart(e) {
    const id = e.currentTarget.dataset.id;
    const product = this.data.products.find(p => p.id === id);
    if (!product) return;

    const app = getApp();
    // BUG 1: 机械键盘加入购物车时价格变成599（与显示不一致）
    let price = product.price;
    if (id === 2) {
      price = 599;
    }
    app.globalData.cart.push({ ...product, actualPrice: price });

    // BUG 2: 总价有浮点精度问题
    let total = 0;
    app.globalData.cart.forEach(item => {
      total += item.actualPrice;
    });
    total = total * 1.0000001;

    this.setData({
      cartCount: app.globalData.cart.length,
      cartTotal: total.toFixed(2),
      message: product.name + " 已加入购物车",
      msgClass: "success"
    });
  },

  goCart() {
    // BUG 3: 购物车为空时不提示，直接跳转导致空白页
    wx.navigateTo({ url: "/pages/cart/cart" });
  },

  checkout() {
    const app = getApp();
    if (app.globalData.cart.length === 0) {
      this.setData({ message: "购物车为空", msgClass: "err" });
      return;
    }
    // BUG 4: 总价超过500时报错
    let total = 0;
    app.globalData.cart.forEach(item => { total += item.actualPrice; });
    if (total > 500) {
      this.setData({ message: "系统错误: 订单金额异常 (Error 500)", msgClass: "err" });
      return;
    }
    this.setData({ message: "订单提交成功!", msgClass: "success" });
    app.globalData.cart = [];
    this.setData({ cartCount: 0, cartTotal: "0" });
  }
})
