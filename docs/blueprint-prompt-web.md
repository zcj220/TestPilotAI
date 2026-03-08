# TestPilot AI — Web蓝本生成提示词

> 前置条件：请先阅读 `docs/blueprint-prompt-golden-rules.md` 中的8条黄金规则。

---

## Web平台专属规则

### 模块拆分

Web项目**必须按功能模块拆分蓝本**，不要创建单一的 testpilot.json：

```
testpilot/
  auth.testpilot.json        — 登录/注册/权限/退出
  product.testpilot.json     — 商品管理CRUD
  order.testpilot.json       — 订单管理
  cart.testpilot.json        — 购物车
  user.testpilot.json        — 用户管理
  dashboard.testpilot.json   — 仪表盘/统计
```

### 支持的 action

```
navigate / click / fill / select / wait / screenshot
assert_text / assert_visible / hover / scroll
```

### 蓝本格式

```json
{
  "app_name": "模块名称（如：用户认证模块）",
  "description": "蓝本功能说明（50-200字）",
  "base_url": "http://localhost:端口",
  "version": "1.0",
  "platform": "web",
  "start_command": "npm start（纯HTML留空）",
  "start_cwd": "./",
  "pages": [
    {
      "url": "/",
      "title": "页面标题",
      "elements": {
        "登录按钮": "#login-btn",
        "用户名输入": "#username"
      },
      "scenarios": [
        {
          "name": "正常登录",
          "steps": [
            {"action": "navigate", "value": "http://localhost:3000"},
            {"action": "fill", "target": "#username", "value": "admin"},
            {"action": "fill", "target": "#password", "value": "123456"},
            {"action": "click", "target": "#login-btn"},
            {"action": "assert_text", "target": "#welcome", "expected": "欢迎"}
          ]
        },
        {
          "name": "空密码登录（异常）",
          "steps": [
            {"action": "navigate", "value": "http://localhost:3000"},
            {"action": "fill", "target": "#username", "value": "admin"},
            {"action": "click", "target": "#login-btn"},
            {"action": "assert_text", "target": "#error", "expected": "请输入密码"}
          ]
        }
      ]
    }
  ]
}
```

### Web专属注意事项

1. **导航用绝对URL**：`{"action": "navigate", "value": "http://localhost:3000/products"}`
2. **表单提交后等待**：如果提交后有异步请求，加 `{"action": "wait", "value": "1000"}` 等待1秒
3. **弹窗验证**：`alert/confirm` 弹窗需要用 `assert_text` 验证弹窗容器的文字
4. **SPA路由**：单页应用切换路由后，断言新页面的关键元素可见
5. **响应式**：如果应用支持移动端，考虑添加不同viewport的场景
