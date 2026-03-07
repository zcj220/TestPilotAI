// FreshMart 生鲜超市 - 含隐蔽Bug的测试小程序
App({
  globalData: {
    userInfo: null,
    isVip: true,           // 是否会员
    cart: [],              // 购物车
    address: '',           // 收货地址
    deliveryType: '',      // 配送方式: same_city / express
    coupon: null,          // 选中的优惠券
    coupons: [             // 可用优惠券
      { id: 1, name: '满100减20', threshold: 100, discount: 20 },
      { id: 2, name: '满200减50', threshold: 200, discount: 50 },
    ],
    products: [
      { id: 1, name: '红富士苹果', category: '水果', price: 12.5, vipPrice: 10.63, stock: 10, unit: '斤', img: '🍎' },
      { id: 2, name: '有机香蕉', category: '水果', price: 8.9, vipPrice: 7.57, stock: 15, unit: '斤', img: '🍌' },
      { id: 3, name: '新鲜草莓', category: '水果', price: 25.0, vipPrice: 21.25, stock: 3, unit: '盒', img: '🍓' },
      { id: 4, name: '三文鱼刺身', category: '海鲜', price: 68.0, vipPrice: 57.80, stock: 5, unit: '盒', img: '🐟' },
      { id: 5, name: '澳洲牛排', category: '肉类', price: 89.0, vipPrice: 75.65, stock: 8, unit: '块', img: '🥩' },
      { id: 6, name: '有机西蓝花', category: '蔬菜', price: 6.5, vipPrice: 5.53, stock: 20, unit: '颗', img: '🥦' },
      { id: 7, name: '红心火龙果', category: '水果', price: 15.0, vipPrice: 12.75, stock: 0, unit: '个', img: '🐉' },
      { id: 8, name: '青岛大虾', category: '海鲜', price: 45.0, vipPrice: 38.25, stock: 6, unit: '斤', img: '🦐' },
    ],
  }
})
