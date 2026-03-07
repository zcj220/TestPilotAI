// 商品详情页
Page({
  data: {
    product: null,
    isVip: false,
    message: '',
    msgClass: '',
  },

  onLoad(options) {
    const app = getApp();
    const id = parseInt(options.id);
    const product = app.globalData.products.find(p => p.id === id);
    this.setData({
      product: product,
      isVip: app.globalData.isVip,
    });
  },

  addToCart() {
    const app = getApp();
    const product = this.data.product;
    if (!product) return;

    if (product.stock <= 0) {
      this.setData({ message: '该商品已售罄', msgClass: 'err' });
      return;
    }

    let price = product.price;
    if (app.globalData.isVip) {
      price = product.vipPrice;
    }

    app.globalData.cart.push({
      id: product.id,
      name: product.name,
      price: product.price,
      actualPrice: price,
      unit: product.unit,
      img: product.img,
      qty: 1,
    });

    this.setData({
      message: product.name + ' 已加入购物车',
      msgClass: 'success',
    });
  },

  goCart() {
    wx.navigateTo({ url: '/pages/cart/cart' });
  },
})
