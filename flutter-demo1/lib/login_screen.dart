import 'package:flutter/material.dart';

/// 登录页面
/// 预埋 Bug：
///   Bug-1: 未验证用户名/密码为空，点击"登录"直接跳转 → 空账号可以登录
///   Bug-2: 密码框未使用 obscureText，密码明文可见
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _userCtrl = TextEditingController();
  final _passCtrl = TextEditingController();
  String _errorMsg = '';

  void _onLogin() {
    // ⚠️ Bug-1: 没有验证非空，任何输入（包括空）都能登录
    if (_userCtrl.text == 'admin' && _passCtrl.text == 'admin123') {
      Navigator.pushReplacementNamed(context, '/tasks');
    } else if (_userCtrl.text.isEmpty && _passCtrl.text.isEmpty) {
      // Bug-1: 空用户名密码应该拦截，但是这里没有处理 → 允许继续
      Navigator.pushReplacementNamed(context, '/tasks');
    } else {
      setState(() => _errorMsg = '用户名或密码错误');
    }
  }

  @override
  void dispose() {
    _userCtrl.dispose();
    _passCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('TaskPilot'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
      ),
      body: Padding(
        padding: const EdgeInsets.all(24.0),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Text('欢迎登录',
                style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
            const SizedBox(height: 32),
            // ⚠️ Bug-2: 密码框没加 obscureText: true，密码明文显示
            Semantics(
              label: 'tf_username',
              textField: true,
              child: TextField(
                controller: _userCtrl,
                decoration:
                    const InputDecoration(labelText: '用户名', hintText: '请输入用户名'),
              ),
            ),
            const SizedBox(height: 16),
            Semantics(
              label: 'tf_password',
              textField: true,
              child: TextField(
                controller: _passCtrl,
                // obscureText: true,  ← 故意注释掉，密码可见
                decoration:
                    const InputDecoration(labelText: '密码', hintText: '请输入密码'),
              ),
            ),
            const SizedBox(height: 8),
            if (_errorMsg.isNotEmpty)
              Semantics(
                label: 'txt_error',
                child:
                    Text(_errorMsg, style: const TextStyle(color: Colors.red)),
              ),
            const SizedBox(height: 24),
            Semantics(
              label: 'btn_login',
              button: true,
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _onLogin,
                  child: const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Text('登录', style: TextStyle(fontSize: 16)),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 16),
            const Text('测试账号：admin / admin123',
                style: TextStyle(color: Colors.grey)),
          ],
        ),
      ),
    );
  }
}
