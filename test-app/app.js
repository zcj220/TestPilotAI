/**
 * 订单管理系统 - TestPilot AI 测试专用
 * 
 * 故意埋入的Bug清单：
 * 1. [计算错误] 小计 = 单价（没乘数量）
 * 2. [JS报错] 删除商品时引用 undefined 属性
 * 3. [错误提示] 空表单提交显示 .error 元素
 * 4. [布局溢出] 长商品名 nowrap 不截断
 * 5. [网络请求] 提交订单时调用不存在的API，触发404
 */

let orderItems = [];
let nextId = 1;

const CATEGORY_MAP = {
    electronics: "电子产品",
    clothing: "服装",
    food: "食品",
    books: "图书",
};

function addProduct() {
    const nameEl = document.getElementById("productName");
    const priceEl = document.getElementById("productPrice");
    const qtyEl = document.getElementById("productQty");
    const catEl = document.getElementById("productCategory");
    const errorEl = document.getElementById("formError");

    const name = nameEl.value.trim();
    const price = parseFloat(priceEl.value);
    const qty = parseInt(qtyEl.value, 10);
    const category = catEl.value;

    // 验证
    errorEl.style.display = "none";
    if (!name) {
        errorEl.textContent = "错误：请输入商品名称";
        errorEl.style.display = "block";
        return;
    }
    if (isNaN(price) || price <= 0) {
        errorEl.textContent = "错误：请输入有效的单价";
        errorEl.style.display = "block";
        return;
    }
    if (isNaN(qty) || qty < 1) {
        errorEl.textContent = "错误：数量必须大于0";
        errorEl.style.display = "block";
        return;
    }
    if (!category) {
        errorEl.textContent = "错误：请选择商品分类";
        errorEl.style.display = "block";
        return;
    }

    // 添加到列表
    orderItems.push({
        id: nextId++,
        name: name,
        price: price,
        qty: qty,
        category: category,
    });

    // 清空表单
    nameEl.value = "";
    priceEl.value = "";
    qtyEl.value = "1";
    catEl.value = "";

    renderTable();
}

function removeProduct(id) {
    // BUG 2: 引用不存在的属性 item.product 而非 item.name
    // 这会在控制台产生 TypeError，异常检测器应该捕获
    const item = orderItems.find(i => i.id === id);
    console.log("删除商品: " + item.product.toUpperCase());  // BUG: item.product 不存在

    orderItems = orderItems.filter(i => i.id !== id);
    renderTable();
}

function renderTable() {
    const tbody = document.getElementById("orderBody");
    const emptyMsg = document.getElementById("emptyMsg");
    const countEl = document.getElementById("itemCount");
    const totalQtyEl = document.getElementById("totalQty");
    const totalPriceEl = document.getElementById("totalPrice");

    tbody.innerHTML = "";

    if (orderItems.length === 0) {
        emptyMsg.style.display = "block";
        countEl.textContent = "0";
        totalQtyEl.textContent = "0";
        totalPriceEl.textContent = "\u00a50.00";
        return;
    }

    emptyMsg.style.display = "none";
    countEl.textContent = orderItems.length;

    let totalQty = 0;
    let totalPrice = 0;

    orderItems.forEach(item => {
        // BUG 1: 小计只用单价，没乘数量
        const subtotal = item.price;  // 正确应该是 item.price * item.qty

        totalQty += item.qty;
        totalPrice += subtotal;

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td class="product-name">${item.name}</td>
            <td>${CATEGORY_MAP[item.category] || item.category}</td>
            <td>\u00a5${item.price.toFixed(2)}</td>
            <td>${item.qty}</td>
            <td>\u00a5${subtotal.toFixed(2)}</td>
            <td><button class="btn btn-danger" onclick="removeProduct(${item.id})">删除</button></td>
        `;
        tbody.appendChild(tr);
    });

    totalQtyEl.textContent = totalQty;
    totalPriceEl.textContent = "\u00a5" + totalPrice.toFixed(2);
}

function submitOrder() {
    const resultEl = document.getElementById("submitResult");

    if (orderItems.length === 0) {
        resultEl.style.display = "block";
        resultEl.innerHTML = '<div class="error-msg">提交失败：订单中没有商品</div>';
        return;
    }

    // BUG 5: 调用一个不存在的API地址，触发 404 网络错误
    // 异常检测器应该捕获这个网络请求失败
    fetch("/api/v1/orders/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ items: orderItems }),
    })
    .then(resp => {
        if (!resp.ok) {
            throw new Error("HTTP " + resp.status);
        }
        return resp.json();
    })
    .then(data => {
        resultEl.style.display = "block";
        resultEl.innerHTML = '<div class="success-msg">订单提交成功！订单号：' + data.order_id + '</div>';
    })
    .catch(err => {
        resultEl.style.display = "block";
        resultEl.innerHTML = '<div class="error-msg">订单提交失败：' + err.message + '</div>';
    });
}

// 页面初始化
renderTable();
