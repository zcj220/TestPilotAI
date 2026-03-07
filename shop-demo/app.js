// ====== 初始数据 ======
const USERS_DB = [
  { id:1, name:'admin',  pass:'123456', email:'admin@shop.com',   reg:'2025-01-01', active:true },
  { id:2, name:'张三',   pass:'abc123', email:'zhangsan@qq.com',  reg:'2025-03-15', active:true },
  { id:3, name:'李四',   pass:'pass88', email:'lisi@163.com',     reg:'2025-06-20', active:false },
];

let products = [
  { id:1, name:'iPhone 16 Pro', price:8999, stock:50, cat:'电子', on:true },
  { id:2, name:'AirPods Pro 2', price:1899, stock:0,  cat:'电子', on:false },  // FIXED: 库存0则下架
  { id:3, name:'优衣库T恤',     price:99,   stock:200, cat:'服装', on:true },
  { id:4, name:'Python编程书',  price:89,   stock:30,  cat:'图书', on:false },
];

let orders = [
  { id:'ORD-001', user:'张三', product:'iPhone 16 Pro', qty:1, amount:8999, status:'已完成' },
  { id:'ORD-002', user:'李四', product:'AirPods Pro 2', qty:2, amount:3798, status:'已付款' },
  { id:'ORD-003', user:'张三', product:'优衣库T恤',     qty:3, amount:297,  status:'已发货' },
  { id:'ORD-004', user:'王五', product:'Python编程书',  qty:1, amount:89,   status:'待付款' },
];

let productIdSeq = 5;
let currentUser = null;

// ====== 登录 ======
function doLogin() {
  const u = document.getElementById('loginUser').value.trim();
  const p = document.getElementById('loginPass').value.trim();
  const errEl = document.getElementById('loginError');
  const found = USERS_DB.find(x => x.name === u && x.pass === p);
  if (!found) {
    errEl.style.display = 'block';
    errEl.textContent = '用户名或密码错误';
    return;
  }
  if (!found.active) {
    errEl.style.display = 'block';
    errEl.textContent = '该账号已被禁用';
    return;
  }
  currentUser = found;
  errEl.style.display = 'none';
  document.getElementById('loginPage').classList.remove('active');
  document.getElementById('mainPage').classList.add('active');
  initDashboard();
}

function doLogout() {
  currentUser = null;
  document.getElementById('mainPage').classList.remove('active');
  document.getElementById('loginPage').classList.add('active');
  document.getElementById('loginUser').value = '';
  document.getElementById('loginPass').value = '';
}

// ====== 导航 ======
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.nav').forEach(n => n.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  document.getElementById('nav-' + name).classList.add('active');
  if (name === 'products') renderProducts();
  if (name === 'orders')   renderOrders();
  if (name === 'users')    renderUsers();
}

// ====== 仪表盘 ======
function initDashboard() {
  // FIXED: 统计已付款+已发货+已完成
  const sales = orders
    .filter(o => ['已付款','已发货','已完成'].includes(o.status))
    .reduce((s, o) => s + o.amount, 0);

  document.getElementById('stat-sales').textContent    = '¥' + sales.toLocaleString();
  document.getElementById('stat-orders').textContent   = orders.length;
  document.getElementById('stat-products').textContent = products.length;
  document.getElementById('stat-users').textContent    = USERS_DB.length;

  const tbody = document.getElementById('recentBody');
  tbody.innerHTML = '';
  orders.slice(0, 3).forEach(o => {
    tbody.innerHTML += `<tr>
      <td>${o.id}</td><td>${o.user}</td>
      <td>¥${o.amount.toLocaleString()}</td>
      <td><span class="badge ${statusBadge(o.status)}">${o.status}</span></td>
    </tr>`;
  });
}

// ====== 商品管理 ======
function renderProducts(list) {
  list = list || products;
  const tbody = document.getElementById('productBody');
  const empty = document.getElementById('productEmpty');
  tbody.innerHTML = '';
  if (list.length === 0) { empty.style.display='block'; return; }
  empty.style.display = 'none';
  list.forEach(p => {
    // FIXED: 价格带¥前缀和千分位
    tbody.innerHTML += `<tr>
      <td>${p.id}</td><td>${p.name}</td>
      <td>¥${parseFloat(p.price).toLocaleString('zh-CN', {minimumFractionDigits:2, maximumFractionDigits:2})}</td>
      <td>${p.stock}</td><td>${p.cat}</td>
      <td><span class="badge ${p.on ? 'badge-success':'badge-gray'}">${p.on?'上架':'下架'}</span></td>
      <td><button class="btn-del" onclick="deleteProduct(${p.id})">删除</button></td>
    </tr>`;
  });
}

function filterProducts() {
  const kw = document.getElementById('searchInput').value.trim().toLowerCase();
  renderProducts(kw ? products.filter(p => p.name.toLowerCase().includes(kw)) : products);
}

function toggleAddForm() {
  const f = document.getElementById('addForm');
  f.style.display = f.style.display === 'none' ? 'block' : 'none';
  document.getElementById('pErr').style.display = 'none';
}

function saveProduct() {
  const name  = document.getElementById('pName').value.trim();
  const price = parseFloat(document.getElementById('pPrice').value);
  const stock = parseInt(document.getElementById('pStock').value);
  const cat   = document.getElementById('pCat').value;
  const errEl = document.getElementById('pErr');

  if (!name)          { errEl.style.display='block'; errEl.textContent='请输入商品名称'; return; }
  if (isNaN(price) || price < 0) { errEl.style.display='block'; errEl.textContent='价格无效'; return; }
  if (isNaN(stock) || stock < 0) { errEl.style.display='block'; errEl.textContent='库存无效'; return; }
  if (!cat)           { errEl.style.display='block'; errEl.textContent='请选择分类'; return; }

  products.push({ id: productIdSeq++, name, price, stock, cat, on: true });
  errEl.style.display = 'none';
  toggleAddForm();
  ['pName','pPrice','pStock'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('pCat').value = '';
  renderProducts();
  document.getElementById('stat-products').textContent = products.length;
}

function deleteProduct(id) {
  products = products.filter(p => p.id !== id);
  renderProducts();
}

// ====== 订单管理 ======
function renderOrders(list) {
  list = list || orders;
  const tbody = document.getElementById('orderBody');
  const empty = document.getElementById('orderEmpty');
  tbody.innerHTML = '';
  if (list.length === 0) { empty.style.display='block'; }
  else { empty.style.display='none'; }

  // FIXED: 合计用数值相加，带¥格式
  let total = 0;
  list.forEach(o => {
    total += o.amount;
    tbody.innerHTML += `<tr>
      <td>${o.id}</td><td>${o.user}</td><td>${o.product}</td>
      <td>${o.qty}</td><td>${o.amount.toLocaleString()}</td>
      <td><span class="badge ${statusBadge(o.status)}">${o.status}</span></td>
      <td>${o.status==='已付款'?`<button class="btn-ship" onclick="shipOrder('${o.id}')">发货</button>`:''}</td>
    </tr>`;
  });
  document.getElementById('orderTotalAmt').textContent = '¥' + total.toLocaleString();
}

function filterOrders() {
  const v = document.getElementById('orderFilter').value;
  renderOrders(v === 'all' ? orders : orders.filter(o => o.status === v));
}

function shipOrder(id) {
  const o = orders.find(x => x.id === id);
  if (o) { o.status = '已发货'; renderOrders(); }
}

// ====== 用户管理 ======
function renderUsers() {
  const tbody = document.getElementById('userBody');
  tbody.innerHTML = '';
  USERS_DB.forEach(u => {
    tbody.innerHTML += `<tr>
      <td>${u.id}</td><td>${u.name}</td><td>${u.email}</td><td>${u.reg}</td>
      <td><span class="badge ${u.active?'badge-success':'badge-gray'}">${u.active?'正常':'禁用'}</span></td>
    </tr>`;
  });
}

// ====== 工具 ======
function statusBadge(s) {
  return { '待付款':'badge-warn', '已付款':'badge-info', '已发货':'badge-info', '已完成':'badge-success' }[s] || 'badge-gray';
}
