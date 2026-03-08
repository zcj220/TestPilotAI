// FreshMart 首页 - 商品列表 + 搜索 + 分类
Page({
  data: {
    products: [],
    filteredProducts: [],
    categories: ['全部', '水果', '海鲜', '肉类', '蔬菜'],
    activeCategory: '全部',
    searchKeyword: '',
    sortBy: 'default',  // default / price_asc / price_desc
    cartCount: 0,
    isVip: false,
    message: '',
    msgClass: '',
  },

  onShow() {
    const app = getApp();
    this.setData({
      products: app.globalData.products,
      filteredProducts: app.globalData.products,
      isVip: app.globalData.isVip,
      cartCount: app.globalData.cart.length,
    });
  },

  // 搜索
  onSearch(e) {
    const keyword = e.detail.value || '';
    this.setData({ searchKeyword: keyword });
    this.filterProducts();
  },

  // 切换分类
  onCategoryTap(e) {
    const cat = e.currentTarget.dataset.cat;
    this.setData({ activeCategory: cat });
    this.filterProducts();
  },

  // 排序切换
  onSortChange(e) {
    const sorts = ['default', 'price_asc', 'price_desc'];
    this.setData({ sortBy: sorts[e.detail.value] });
    this.filterProducts();
  },

  // 筛选+排序逻辑
  filterProducts() {
    const { products, activeCategory, searchKeyword, sortBy } = this.data;
    let list = products.filter(p => {
      const catOk = activeCategory === '全部' || p.category === activeCategory;
      const keyOk = !searchKeyword || p.name.includes(searchKeyword);
      return catOk && keyOk;
    });

    // BUG 6（隐蔽）: 按价格升序排序时，比较用的是字符串而非数字
    // 导致 8.9 排在 68.0 后面（因为 "8" > "6"）
    if (sortBy === 'price_asc') {
      list = list.sort((a, b) => String(a.price).localeCompare(String(b.price)));
    } else if (sortBy === 'price_desc') {
      list = list.sort((a, b) => b.price - a.price);
    }

    this.setData({ filteredProducts: list });
  },

  // 加入购物车
  addToCart(e) {
    const id = e.currentTarget.dataset.id;
    const app = getApp();
    const product = app.globalData.products.find(p => p.id === id);
    if (!product) return;

    // 检查库存
    if (product.stock <= 0) {
      this.setData({ message: product.name + ' 已售罄', msgClass: 'err' });
      return;
    }

    // BUG 2（隐蔽）: 库存检查只看是否>0，不检查购物车中已有数量
    // 库存10但可以无限加入购物车

    // 计算价格
    let price = product.price;
    if (app.globalData.isVip) {
      // BUG 1（隐蔽）: 会员价计算错误
      // 应该是8折(price*0.8)，但vipPrice字段实际存的是8.5折的值
      // 注意：vipPrice 在 app.js 中已经预设了错误值（8.5折而非8折）
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
      cartCount: app.globalData.cart.length,
      message: product.name + ' 已加入购物车',
      msgClass: 'success',
    });
  },

  // 查看商品详情
  goDetail(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: '/pages/detail/detail?id=' + id });
  },

  // 查看购物车
  goCart() {
    wx.navigateTo({ url: '/pages/cart/cart' });
  },
})
