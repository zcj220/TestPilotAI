import SwiftUI

struct TodoItem: Identifiable {
    let id = UUID()
    var text: String
    var isDone: Bool = false
}

class AppModel: ObservableObject {
    @Published var isLoggedIn = false
    @Published var username = ""
    @Published var loginError = ""
    @Published var todos: [TodoItem] = []

    func login(username: String, password: String) {
        if username == "admin" && password == "123456" {
            self.username = username
            self.isLoggedIn = true
            self.loginError = ""
            self.todos = [
                TodoItem(text: "完成第一个iOS测试"),
                TodoItem(text: "检查测试报告"),
            ]
        } else {
            self.loginError = "用户名或密码错误"
        }
    }

    func logout() {
        isLoggedIn = false
        username = ""
        loginError = ""
        todos = []
    }

    func addTodo(_ text: String) {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        todos.append(TodoItem(text: trimmed))
    }

    func toggleTodo(id: UUID) {
        if let idx = todos.firstIndex(where: { $0.id == id }) {
            todos[idx].isDone.toggle()
        }
    }

    func deleteTodo(id: UUID) {
        todos.removeAll { $0.id == id }
    }
}
