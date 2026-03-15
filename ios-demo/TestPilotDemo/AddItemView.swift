import SwiftUI

struct AddItemView: View {
    @EnvironmentObject var model: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var text = ""

    var body: some View {
        NavigationView {
            VStack(spacing: 20) {
                TextField("输入待办事项", text: $text)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                    .padding(.horizontal)
                    .accessibilityIdentifier("tf_new_item")

                Spacer()
            }
            .padding(.top, 24)
            .navigationTitle("新增待办")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("取消") {
                        dismiss()
                    }
                    .accessibilityIdentifier("btn_cancel")
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("保存") {
                        model.addTodo(text)
                        dismiss()
                    }
                    .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
                    .accessibilityIdentifier("btn_save")
                }
            }
        }
    }
}
