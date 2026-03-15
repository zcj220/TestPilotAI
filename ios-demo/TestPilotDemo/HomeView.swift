import SwiftUI

struct HomeView: View {
    @EnvironmentObject var model: AppModel
    @State private var showingAddItem = false

    var body: some View {
        NavigationView {
            VStack(spacing: 0) {
                // 欢迎横幅
                HStack {
                    Text("你好，\(model.username)！")
                        .font(.headline)
                        .accessibilityIdentifier("lbl_welcome")
                    Spacer()
                    Text("\(model.todos.filter { $0.isDone }.count)/\(model.todos.count) 完成")
                        .font(.caption)
                        .foregroundColor(.secondary)
                        .accessibilityIdentifier("lbl_progress")
                }
                .padding(.horizontal)
                .padding(.vertical, 12)
                .background(Color(.systemGray6))

                // 待办列表
                if model.todos.isEmpty {
                    VStack(spacing: 12) {
                        Spacer()
                        Image(systemName: "tray")
                            .font(.system(size: 48))
                            .foregroundColor(.secondary)
                        Text("暂无待办事项")
                            .foregroundColor(.secondary)
                            .accessibilityIdentifier("lbl_empty")
                        Spacer()
                    }
                } else {
                    List {
                        ForEach(Array(model.todos.enumerated()), id: \.element.id) { index, todo in
                            HStack(spacing: 12) {
                                Button(action: {
                                    model.toggleTodo(id: todo.id)
                                }) {
                                    Image(systemName: todo.isDone
                                          ? "checkmark.circle.fill"
                                          : "circle")
                                        .font(.title2)
                                        .foregroundColor(todo.isDone ? .green : .gray)
                                }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("todo_toggle_\(index)")

                                Text(todo.text)
                                    .strikethrough(todo.isDone)
                                    .foregroundColor(todo.isDone ? .secondary : .primary)
                                    .accessibilityIdentifier("todo_text_\(index)")

                                Spacer()
                            }
                            .padding(.vertical, 4)
                        }
                        .onDelete { indexSet in
                            indexSet.forEach { i in
                                model.deleteTodo(id: model.todos[i].id)
                            }
                        }
                    }
                    .accessibilityIdentifier("list_todos")
                }
            }
            .navigationTitle("我的待办")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("退出") {
                        model.logout()
                    }
                    .accessibilityIdentifier("btn_logout")
                }
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { showingAddItem = true }) {
                        Image(systemName: "plus")
                    }
                    .accessibilityIdentifier("btn_add")
                }
            }
        }
        .sheet(isPresented: $showingAddItem) {
            AddItemView()
        }
    }
}
