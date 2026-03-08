// ====== 数据 ======
const products = [
  { id:1, name:"红富士苹果", emoji:"🍎", price:12.8, originalPrice:15.8, stock:50, cat:"fruit", unit:"500g" },
  { id:2, name:"进口香蕉", emoji:"🍌", price:6.5, originalPrice:8.0, stock:30, cat:"fruit", unit:"500g" },
  { id:3, name:"水蜜桃", emoji:"🍑", price:18.8, originalPrice:22.0, stock:0, cat:"fruit", unit:"500g" },
  { id:4, name:"新疆葡萄", emoji:"🍇", price:15.5, originalPrice:19.9, stock:25, cat:"fruit", unit:"500g" },
  { id:5, name:"有机西兰花", emoji:"🥦", price:8.8, originalPrice:10.0, stock:40, cat:"vegetable", unit:"个" },
  { id:6, name:"新鲜番茄", emoji:"🍅", price:5.5, originalPrice:7.0, stock:60, cat:"vegetable", unit:"500g" },
  { id:7, name:"坚果混合装", emoji:"🥜", price:29.9, originalPrice:39.9, stock:20, cat:"snack", unit:"袋" },
  { id:8, name:"芒果干", emoji:"🥭", price:16.8, originalPrice:22.0, stock:35, cat:"snack", unit:"袋" },
];

let cart = [];
let orders = [];
let currentUser = null;
let currentCat = "all";
let searchKeyword = "";
let orderIdCounter = 10001;

// ====== 页面导航 ======
function showPage(pageId) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById(pageId).classList.add("active");
}

function switchTab(tabId) {
  document.querySelectorAll("#mainPage .tab").forEach(t => t.classList.remove("active"));
  document.getElementById(tabId).classList.add("active");
  document.querySelectorAll(".tab-item").forEach(t => t.classList.remove("active"));
  document.querySelector(`[data-tab="${tabId}"]`).classList.add("active");
  if (tabId === "tabCart") renderCart();
  if (tabId === "tabMe") renderProfile();
}

// ====== Toast ======
function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2000);
}

// ====== 登录/注册 ======
function doLogin() {
  const phone = document.getElementById("loginPhone").value.trim();
  const pass = document.getElementById("loginPass").value.trim();
  const errEl = document.getElementById("loginError");
  errEl.textContent = "";

  if (!phone) { errEl.textContent = "请输入手机号"; return; }
  if (!/^1\d{10}$/.test(phone)) { errEl.textContent = "手机号格式不正确"; return; }
  if (!pass) { errEl.textContent = "请输入密码"; return; }
  if (pass.length < 6) { errEl.textContent = "密码至少6位"; return; }

  // BUG 1（隐蔽）: 密码"123456"可以登录任何手机号，没有真正验证
  if (pass !== "123456" && pass !== "password") {
    errEl.textContent = "密码错误";
    return;
  }

  currentUser = { phone: phone, nickname: "用户" + phone.slice(-4), avatar: "😊" };
  showPage("mainPage");
  renderProducts();
  showToast("登录成功");
}

function doGuestLogin() {
  currentUser = null;
  showPage("mainPage");
  renderProducts();
}

function doRegister() {
  const phone = document.getElementById("regPhone").value.trim();
  const nickname = document.getElementById("regNickname").value.trim();
  const pass = document.getElementById("regPass").value.trim();
  const pass2 = document.getElementById("regPass2").value.trim();
  const errEl = document.getElementById("regError");
  errEl.textContent = "";

  if (!phone) { errEl.textContent = "请输入手机号"; return; }
  if (!/^1\d{10}$/.test(phone)) { errEl.textContent = "手机号格式不正确"; return; }
  if (!nickname) { errEl.textContent = "请输入昵称"; return; }
  if (!pass) { errEl.textContent = "请输入密码"; return; }
  if (pass.length < 6) { errEl.textContent = "密码至少6位"; return; }
  if (pass !== pass2) { errEl.textContent = "两次密码不一致"; return; }

  currentUser = { phone: phone, nickname: nickname, avatar: "😊" };
  showPage("mainPage");
  renderProducts();
  showToast("注册成功，已自动登录");
}

function doLogout() {
  currentUser = null;
  cart = [];
  document.getElementById("loginPhone").value = "";
  document.getElementById("loginPass").value = "";
  document.getElementById("loginError").textContent = "";
  showPage("loginPage");
  showToast("已退出登录");
}

// ====== 商品 ======
function getFilteredProducts() {
  let list = products;
  if (currentCat !== "all") {
    list = list.filter(p => p.cat === currentCat);
  }
  if (searchKeyword) {
    list = list.filter(p => p.name.includes(searchKeyword));
  }
  return list;
}

function renderProducts() {
  const list = getFilteredProducts();
  const el = document.getElementById("productList");
  if (list.length === 0) {
    el.innerHTML = '<div class="empty-state"><div class="empty-icon">🔍</div><div class="empty-text" id="noResult">没有找到相关商品</div></div>';
    return;
  }
  el.innerHTML = list.map(p => {
    const inCart = cart.find(c => c.id === p.id);
    const qty = inCart ? inCart.qty : 0;
    const soldOut = p.stock <= 0;
    return `<div class="product-card" data-id="${p.id}" id="product-${p.id}">
      <div class="product-img">${p.emoji}</div>
      <div class="product-info">
        <div class="product-name" id="pname-${p.id}">${p.name}</div>
        <div class="product-price">¥${p.price}<span class="original">¥${p.originalPrice}</span></div>
        <div class="product-stock" id="pstock-${p.id}">${soldOut ? "已售罄" : "库存" + p.stock + p.unit}</div>
      </div>
      <button class="product-btn${soldOut ? " disabled" : ""}" id="addBtn-${p.id}"
        ${soldOut ? "disabled" : `onclick="addToCart(${p.id})"`}>
        ${soldOut ? "已售罄" : (qty > 0 ? "再来一份(已加"+qty+")" : "加入购物车")}
      </button>
    </div>`;
  }).join("");
}

function selectCategory(cat) {
  currentCat = cat;
  document.querySelectorAll(".cat-item").forEach(c => c.classList.remove("active"));
  document.querySelector(`[data-cat="${cat}"]`).classList.add("active");
  renderProducts();
}

function doSearch() {
  searchKeyword = document.getElementById("searchInput").value.trim();
  renderProducts();
}

// ====== 购物车 ======
function addToCart(id) {
  const p = products.find(x => x.id === id);
  if (!p || p.stock <= 0) return;

  const existing = cart.find(c => c.id === id);
  if (existing) {
    // BUG 2（隐蔽）: 库存检查只看是否>0，不检查购物车中已有数量
    // 库存50但可以无限加入购物车
    existing.qty += 1;
  } else {
    cart.push({ id: p.id, name: p.name, emoji: p.emoji, price: p.price, qty: 1 });
  }
  updateCartBadge();
  renderProducts();
  showToast(`${p.name} 已加入购物车`);
}

function updateCartBadge() {
  const total = cart.reduce((s, c) => s + c.qty, 0);
  const badge = document.getElementById("cartBadge");
  const countEl = document.getElementById("cartItemCount");
  if (total > 0) {
    badge.textContent = total;
    badge.style.display = "flex";
  } else {
    badge.style.display = "none";
  }
  if (countEl) countEl.textContent = total;
}

function renderCart() {
  const listEl = document.getElementById("cartList");
  const emptyEl = document.getElementById("cartEmpty");
  const footerEl = document.getElementById("cartFooter");
  const totalEl = document.getElementById("cartTotal");
  const countEl = document.getElementById("cartItemCount");

  if (cart.length === 0) {
    listEl.innerHTML = "";
    emptyEl.style.display = "block";
    footerEl.style.display = "none";
    return;
  }

  emptyEl.style.display = "none";
  footerEl.style.display = "flex";

  // BUG 3（隐蔽）: 总价计算用浮点加法，不做精度处理
  // 12.8 + 6.5 + 6.5 = 25.799999999999997 而不是 25.80
  let total = 0;
  cart.forEach(c => { total += c.price * c.qty; });

  listEl.innerHTML = cart.map(c => `<div class="cart-item" id="cartItem-${c.id}">
    <div class="cart-item-img">${c.emoji}</div>
    <div class="cart-item-info">
      <div class="cart-item-name">${c.name}</div>
      <div class="cart-item-price">¥${c.price}</div>
    </div>
    <div class="cart-item-qty">
      <button class="qty-btn" onclick="changeQty(${c.id},-1)">−</button>
      <span class="qty-val" id="qty-${c.id}">${c.qty}</span>
      <button class="qty-btn" onclick="changeQty(${c.id},1)">+</button>
    </div>
    <span class="cart-item-remove" onclick="removeFromCart(${c.id})">✕</span>
  </div>`).join("");

  totalEl.textContent = "¥" + total.toFixed(2);
  countEl.textContent = cart.reduce((s, c) => s + c.qty, 0);
}

function changeQty(id, delta) {
  const item = cart.find(c => c.id === id);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) {
    cart = cart.filter(c => c.id !== id);
  }
  updateCartBadge();
  renderCart();
}

function removeFromCart(id) {
  cart = cart.filter(c => c.id !== id);
  updateCartBadge();
  renderCart();
  showToast("已移除");
}

function clearCart() {
  if (cart.length === 0) return;
  cart = [];
  updateCartBadge();
  renderCart();
  showToast("购物车已清空");
}

// ====== 结算 ======
function goCheckout() {
  if (cart.length === 0) {
    showToast("购物车为空");
    return;
  }
  if (!currentUser) {
    showToast("请先登录");
    showPage("loginPage");
    return;
  }
  renderCheckout();
  showPage("checkoutPage");
}

function renderCheckout() {
  const itemsEl = document.getElementById("checkoutItems");
  itemsEl.innerHTML = cart.map(c => `<div class="checkout-item">
    <div class="checkout-item-img">${c.emoji}</div>
    <div class="checkout-item-name">${c.name}</div>
    <div class="checkout-item-qty">x${c.qty}</div>
    <div class="checkout-item-price">¥${(c.price * c.qty).toFixed(2)}</div>
  </div>`).join("");

  updateCheckoutTotal();
}

function updateCheckoutTotal() {
  let subtotal = 0;
  cart.forEach(c => { subtotal += c.price * c.qty; });

  const deliveryType = document.querySelector('input[name="delivery"]:checked').value;
  // BUG 4（隐蔽）: 自提应该免费(0元)，但实际收了3元
  let deliveryFee = deliveryType === "selfpick" ? 3 : 8;

  // BUG 5（隐蔽）: 新用户首单减5元的优惠没有真正生效
  // 代码写了discount=5但计算total时忘了减
  let discount = 5;
  let total = subtotal + deliveryFee;  // 应该是 subtotal + deliveryFee - discount

  document.getElementById("checkoutSubtotal").textContent = "¥" + subtotal.toFixed(2);
  document.getElementById("checkoutDelivery").textContent = deliveryType === "selfpick" ? "免费" : "¥8.00";
  document.getElementById("checkoutDiscount").textContent = "-¥" + discount.toFixed(2);
  document.getElementById("checkoutTotal").textContent = "¥" + total.toFixed(2);
}

function submitOrder() {
  const name = document.getElementById("addrName").value.trim();
  const phone = document.getElementById("addrPhone").value.trim();
  const addr = document.getElementById("addrDetail").value.trim();
  const errEl = document.getElementById("checkoutError");
  errEl.textContent = "";

  if (!name) { errEl.textContent = "请输入收货人姓名"; return; }
  if (!phone) { errEl.textContent = "请输入联系电话"; return; }
  if (!/^1\d{10}$/.test(phone)) { errEl.textContent = "手机号格式不正确"; return; }
  if (!addr) { errEl.textContent = "请输入详细地址"; return; }

  const deliveryType = document.querySelector('input[name="delivery"]:checked').value;
  let subtotal = 0;
  cart.forEach(c => { subtotal += c.price * c.qty; });
  let deliveryFee = deliveryType === "selfpick" ? 3 : 8;
  let total = subtotal + deliveryFee;

  const orderNo = "ORD" + (orderIdCounter++);
  const order = {
    no: orderNo,
    items: [...cart],
    total: total,
    status: "待发货",
    time: new Date().toLocaleString(),
    address: { name, phone, addr },
    delivery: deliveryType
  };
  orders.unshift(order);

  // 清空购物车
  cart = [];
  updateCartBadge();

  // 显示结果
  document.getElementById("resultOrderNo").textContent = "订单号：" + orderNo;
  document.getElementById("resultAmount").textContent = "¥" + total.toFixed(2);
  showPage("orderResultPage");
  showToast("下单成功！");
}

// ====== 我的订单 ======
function renderOrders() {
  const listEl = document.getElementById("orderList");
  const emptyEl = document.getElementById("orderListEmpty");
  if (orders.length === 0) {
    listEl.innerHTML = "";
    emptyEl.style.display = "block";
    return;
  }
  emptyEl.style.display = "none";
  listEl.innerHTML = orders.map(o => `<div class="order-card" id="order-${o.no}">
    <div class="order-header">
      <span>${o.no}</span>
      <span class="order-status">${o.status}</span>
    </div>
    <div class="order-items">${o.items.map(i => i.emoji + i.name + " x" + i.qty).join("、")}</div>
    <div class="order-time" style="font-size:12px;color:#999">${o.time}</div>
    <div class="order-amount">¥${o.total.toFixed(2)}</div>
  </div>`).join("");
}

// ====== 我的 ======
function renderProfile() {
  if (currentUser) {
    document.getElementById("userName").textContent = currentUser.nickname;
    document.getElementById("userPhone").textContent = currentUser.phone;
    document.getElementById("userAvatar").textContent = currentUser.avatar;
    document.getElementById("logoutBtn").style.display = "block";
  } else {
    document.getElementById("userName").textContent = "游客模式";
    document.getElementById("userPhone").textContent = "登录后享受更多服务";
    document.getElementById("userAvatar").textContent = "👤";
    document.getElementById("logoutBtn").style.display = "none";
  }
  document.getElementById("couponCount").textContent = currentUser ? "2" : "0";
}

// ====== 事件绑定 ======
document.addEventListener("DOMContentLoaded", function() {
  // 登录
  document.getElementById("loginBtn").addEventListener("click", doLogin);
  document.getElementById("guestBtn").addEventListener("click", doGuestLogin);
  document.getElementById("registerLink").addEventListener("click", () => showPage("registerPage"));

  // 注册
  document.getElementById("regBackBtn").addEventListener("click", () => showPage("loginPage"));
  document.getElementById("regSubmitBtn").addEventListener("click", doRegister);

  // 底部Tab
  document.querySelectorAll(".tab-item").forEach(item => {
    item.addEventListener("click", () => switchTab(item.dataset.tab));
  });

  // 分类
  document.querySelectorAll(".cat-item").forEach(item => {
    item.addEventListener("click", () => selectCategory(item.dataset.cat));
  });

  // 搜索
  document.getElementById("searchBtn").addEventListener("click", doSearch);
  document.getElementById("searchInput").addEventListener("keyup", function(e) {
    if (e.key === "Enter") doSearch();
  });

  // 购物车
  document.getElementById("cartClearBtn").addEventListener("click", clearCart);
  document.getElementById("checkoutBtn").addEventListener("click", goCheckout);
  document.getElementById("goShopBtn").addEventListener("click", () => switchTab("tabHome"));

  // 结算
  document.getElementById("checkoutBackBtn").addEventListener("click", () => {
    showPage("mainPage");
    switchTab("tabCart");
  });
  document.querySelectorAll('input[name="delivery"]').forEach(r => {
    r.addEventListener("change", updateCheckoutTotal);
  });
  document.getElementById("submitOrderBtn").addEventListener("click", submitOrder);

  // 订单结果
  document.getElementById("backHomeBtn").addEventListener("click", () => {
    showPage("mainPage");
    switchTab("tabHome");
    renderProducts();
  });
  document.getElementById("viewOrderBtn").addEventListener("click", () => {
    renderOrders();
    showPage("orderListPage");
  });

  // 我的
  document.getElementById("menuOrders").addEventListener("click", () => {
    renderOrders();
    showPage("orderListPage");
  });
  document.getElementById("menuAbout").addEventListener("click", () => {
    showToast("鲜果坊 v1.0 — TestPilot AI Demo");
  });
  document.getElementById("logoutBtn").addEventListener("click", doLogout);

  // 订单列表返回
  document.getElementById("orderListBackBtn").addEventListener("click", () => {
    showPage("mainPage");
    switchTab("tabMe");
  });
});
