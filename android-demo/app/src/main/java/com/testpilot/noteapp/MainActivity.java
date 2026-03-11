package com.testpilot.noteapp;

import android.content.Intent;
import android.os.Bundle;
import android.view.View;
import android.widget.EditText;
import android.widget.TextView;

import androidx.appcompat.app.AppCompatActivity;

/**
 * 登录页面。
 *
 * 预埋Bug-1：空用户名不校验，直接登录成功。
 * 正确行为应该是提示"请输入用户名"。
 */
public class MainActivity extends AppCompatActivity {

    private EditText etUsername;
    private EditText etPassword;
    private TextView tvError;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        etUsername = findViewById(R.id.et_username);
        etPassword = findViewById(R.id.et_password);
        tvError = findViewById(R.id.tv_error);

        findViewById(R.id.btn_login).setOnClickListener(v -> doLogin());
    }

    private void doLogin() {
        String username = etUsername.getText().toString().trim();
        String password = etPassword.getText().toString().trim();

        tvError.setVisibility(View.GONE);

        // Bug-1：没有检查用户名是否为空！
        // 正确做法应该是：
        // if (username.isEmpty()) {
        //     tvError.setText("请输入用户名");
        //     tvError.setVisibility(View.VISIBLE);
        //     return;
        // }

        if (password.isEmpty()) {
            tvError.setText("请输入密码");
            tvError.setVisibility(View.VISIBLE);
            return;
        }

        // 简单验证：admin / admin123
        if ("admin".equals(username) && "admin123".equals(password)) {
            Intent intent = new Intent(this, NoteListActivity.class);
            startActivity(intent);
            finish();
        } else {
            tvError.setText("用户名或密码错误");
            tvError.setVisibility(View.VISIBLE);
        }
    }
}
