import SwiftUI

struct LoginView: View {
    @EnvironmentObject var model: AppModel
    @State private var username = ""
    @State private var password = ""

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            VStack(spacing: 8) {
                Image(systemName: "checkmark.shield.fill")
                    .font(.system(size: 56))
                    .foregroundColor(.blue)
                    .accessibilityIdentifier("img_logo")

                Text("TestPilot Demo")
                    .font(.largeTitle)
                    .fontWeight(.bold)
                    .accessibilityIdentifier("lbl_title")

                Text("iOS 自动化测试示例应用")
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .accessibilityIdentifier("lbl_subtitle")
            }

            VStack(spacing: 16) {
                TextField("用户名", text: $username)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .autocapitalization(.none)
                    .disableAutocorrection(true)
                    .accessibilityIdentifier("tf_username")

                SecureField("密码", text: $password)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .accessibilityIdentifier("tf_password")

                if !model.loginError.isEmpty {
                    Text(model.loginError)
                        .foregroundColor(.red)
                        .font(.caption)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("lbl_error")
                }

                Button(action: {
                    model.login(username: username, password: password)
                }) {
                    Text("登录")
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 4)
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("btn_login")
            }
            .padding(.horizontal, 32)

            Spacer()

            Text("测试账号：admin / 123456")
                .font(.caption2)
                .foregroundColor(.secondary)
                .accessibilityIdentifier("lbl_hint")
        }
        .padding()
    }
}
