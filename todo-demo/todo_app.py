"""PyQt5 待办事项应用 - TestPilot AI 桌面测试 Demo（增强版）

功能：
- 添加待办事项（支持优先级选择）
- 标记完成/取消完成
- 删除待办事项
- 清空已完成项
- 编辑待办事项（双击编辑）
- 优先级标记（High/Medium/Low，彩色标签）
- 搜索过滤
- 排序（按名称/优先级/状态）
- 显示统计（总数/已完成/未完成/高优先级数）
- 全选/取消全选
"""

import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QMessageBox, QFrame, QComboBox, QInputDialog, QCheckBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor


PRIORITY_COLORS = {
    "High": "#e74c3c",
    "Medium": "#f39c12",
    "Low": "#27ae60",
}

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


class TodoApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TodoApp")
        self.setFixedSize(500, 680)
        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QLineEdit {
                padding: 8px; border: 2px solid #ddd; border-radius: 4px;
                font-size: 14px; background: white;
            }
            QLineEdit:focus { border-color: #4a90d9; }
            QPushButton {
                padding: 8px 16px; border: none; border-radius: 4px;
                font-size: 12px; font-weight: bold; color: white;
                background-color: #4a90d9;
            }
            QPushButton:hover { background-color: #357abd; }
            QPushButton#deleteBtn { background-color: #e74c3c; }
            QPushButton#deleteBtn:hover { background-color: #c0392b; }
            QPushButton#clearBtn { background-color: #95a5a6; }
            QPushButton#clearBtn:hover { background-color: #7f8c8d; }
            QPushButton#toggleBtn { background-color: #27ae60; }
            QPushButton#toggleBtn:hover { background-color: #219a52; }
            QPushButton#editBtn { background-color: #8e44ad; }
            QPushButton#editBtn:hover { background-color: #732d91; }
            QPushButton#selectAllBtn { background-color: #2980b9; }
            QPushButton#selectAllBtn:hover { background-color: #1f6fa0; }
            QListWidget {
                border: 2px solid #ddd; border-radius: 4px;
                background: white; font-size: 13px;
                outline: none;
            }
            QListWidget::item { padding: 6px; border-bottom: 1px solid #eee; }
            QListWidget::item:selected { background-color: #e8f0fe; color: black; }
            QLabel#titleLabel { font-size: 20px; font-weight: bold; color: #2c3e50; }
            QLabel#statsLabel { font-size: 12px; color: #7f8c8d; }
            QLabel#filterLabel { font-size: 12px; color: #7f8c8d; font-style: italic; }
            QComboBox {
                padding: 6px; border: 2px solid #ddd; border-radius: 4px;
                font-size: 13px; background: white;
            }
            QLineEdit#searchField {
                padding: 6px; border: 2px solid #bbb; border-radius: 4px;
                font-size: 13px; background: #fffde7;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 12, 16, 12)

        # 标题
        title = QLabel("Todo App")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        # 搜索栏
        search_row = QHBoxLayout()
        self.search_field = QLineEdit()
        self.search_field.setObjectName("searchField")
        self.search_field.setPlaceholderText("Search...")
        self.search_field.setAccessibleName("SearchField")
        self.search_field.textChanged.connect(self._apply_filter)
        search_row.addWidget(self.search_field)

        # 排序下拉
        self.sort_combo = QComboBox()
        self.sort_combo.setAccessibleName("SortCombo")
        self.sort_combo.addItems(["Sort: Default", "Sort: Name", "Sort: Priority", "Sort: Status"])
        self.sort_combo.currentIndexChanged.connect(self._apply_sort)
        search_row.addWidget(self.sort_combo)
        layout.addLayout(search_row)

        # 过滤状态标签
        self.filter_label = QLabel("")
        self.filter_label.setObjectName("filterLabel")
        self.filter_label.setAlignment(Qt.AlignCenter)
        self.filter_label.hide()
        layout.addWidget(self.filter_label)

        # 输入区
        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("输入待办事项...")
        self.input_field.setAccessibleName("TodoInput")
        self.input_field.returnPressed.connect(self.add_todo)
        input_row.addWidget(self.input_field)

        self.priority_combo = QComboBox()
        self.priority_combo.setAccessibleName("PriorityCombo")
        self.priority_combo.addItems(["High", "Medium", "Low"])
        self.priority_combo.setCurrentIndex(1)  # 默认Medium
        self.priority_combo.setFixedWidth(90)
        input_row.addWidget(self.priority_combo)

        add_btn = QPushButton("Add")
        add_btn.setAccessibleName("AddButton")
        add_btn.clicked.connect(self.add_todo)
        input_row.addWidget(add_btn)
        layout.addLayout(input_row)

        # 列表
        self.todo_list = QListWidget()
        self.todo_list.setAccessibleName("TodoList")
        self.todo_list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self.todo_list)

        # 操作按钮行1
        btn_row1 = QHBoxLayout()

        toggle_btn = QPushButton("Toggle Done")
        toggle_btn.setObjectName("toggleBtn")
        toggle_btn.setAccessibleName("ToggleDoneButton")
        toggle_btn.clicked.connect(self.toggle_done)
        btn_row1.addWidget(toggle_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("editBtn")
        edit_btn.setAccessibleName("EditButton")
        edit_btn.clicked.connect(self.edit_todo)
        btn_row1.addWidget(edit_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.setObjectName("deleteBtn")
        delete_btn.setAccessibleName("DeleteButton")
        delete_btn.clicked.connect(self.delete_todo)
        btn_row1.addWidget(delete_btn)

        layout.addLayout(btn_row1)

        # 操作按钮行2
        btn_row2 = QHBoxLayout()

        clear_btn = QPushButton("Clear Done")
        clear_btn.setObjectName("clearBtn")
        clear_btn.setAccessibleName("ClearDoneButton")
        clear_btn.clicked.connect(self.clear_done)
        btn_row2.addWidget(clear_btn)

        select_all_btn = QPushButton("Select All")
        select_all_btn.setObjectName("selectAllBtn")
        select_all_btn.setAccessibleName("SelectAllButton")
        select_all_btn.clicked.connect(self.select_all_done)
        btn_row2.addWidget(select_all_btn)

        layout.addLayout(btn_row2)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # 统计
        self.stats_label = QLabel()
        self.stats_label.setObjectName("statsLabel")
        self.stats_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.stats_label)

        # 内部数据：每项 = {"text": str, "done": bool, "priority": str}
        self._items = []

        # 初始数据
        self._add_item("Buy milk", priority="High")
        self._add_item("Read book", priority="Medium")
        self._add_item("Exercise", priority="Low")
        self._add_item("Write report", priority="High")
        self._add_item("Call dentist", priority="Medium")
        self._refresh_list()

    def _add_item(self, text: str, done: bool = False, priority: str = "Medium"):
        self._items.append({"text": text, "done": done, "priority": priority})

    def _refresh_list(self):
        """根据内部数据重建列表显示。"""
        self.todo_list.clear()
        search = self.search_field.text().strip().lower()
        visible_count = 0
        for idx, item_data in enumerate(self._items):
            # 搜索过滤
            if search and search not in item_data["text"].lower():
                continue
            visible_count += 1
            display = self._format_display(item_data)
            list_item = QListWidgetItem(display)
            list_item.setData(Qt.UserRole, idx)  # 存储原始索引
            # 优先级颜色标签
            pcolor = PRIORITY_COLORS.get(item_data["priority"], "#333")
            if item_data["done"]:
                list_item.setForeground(QColor("#aaa"))
            else:
                list_item.setForeground(QColor(pcolor))
            self.todo_list.addItem(list_item)

        # 过滤状态
        if search:
            self.filter_label.setText(f"Showing {visible_count} of {len(self._items)} items")
            self.filter_label.show()
        else:
            self.filter_label.hide()

        self._update_stats()

    def _format_display(self, item_data: dict) -> str:
        done_mark = "✓" if item_data["done"] else "○"
        pri_tag = f"[{item_data['priority'][0]}]"  # [H] [M] [L]
        return f"{done_mark} {pri_tag} {item_data['text']}"

    def _get_selected_index(self) -> int:
        """获取当前选中项对应的原始数据索引。"""
        item = self.todo_list.currentItem()
        if not item:
            return -1
        return item.data(Qt.UserRole)

    def add_todo(self):
        text = self.input_field.text().strip()
        if not text:
            QMessageBox.warning(self, "Warning", "Please enter a todo item")
            return
        if len(text) > 50:
            QMessageBox.warning(self, "Warning", "Todo item too long (max 50 chars)")
            return
        # 检查重复
        for d in self._items:
            if d["text"].lower() == text.lower():
                QMessageBox.warning(self, "Warning", f"Duplicate item: {text}")
                return
        priority = self.priority_combo.currentText()
        self._add_item(text, priority=priority)
        self.input_field.clear()
        self._refresh_list()

    def toggle_done(self):
        idx = self._get_selected_index()
        if idx < 0:
            QMessageBox.information(self, "Info", "Please select an item first")
            return
        self._items[idx]["done"] = not self._items[idx]["done"]
        self._refresh_list()

    def edit_todo(self):
        idx = self._get_selected_index()
        if idx < 0:
            QMessageBox.information(self, "Info", "Please select an item to edit")
            return
        old_text = self._items[idx]["text"]
        new_text, ok = QInputDialog.getText(
            self, "Edit Todo", "Edit item:", QLineEdit.Normal, old_text
        )
        if ok and new_text.strip():
            new_text = new_text.strip()
            if new_text != old_text:
                # 检查重复
                for i, d in enumerate(self._items):
                    if i != idx and d["text"].lower() == new_text.lower():
                        QMessageBox.warning(self, "Warning", f"Duplicate item: {new_text}")
                        return
                self._items[idx]["text"] = new_text
                self._refresh_list()

    def delete_todo(self):
        idx = self._get_selected_index()
        if idx < 0:
            QMessageBox.information(self, "Info", "Please select an item to delete")
            return
        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Delete '{self._items[idx]['text']}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self._items.pop(idx)
            self._refresh_list()

    def clear_done(self):
        done_count = sum(1 for d in self._items if d["done"])
        if done_count == 0:
            QMessageBox.information(self, "Info", "No completed items to clear")
            return
        self._items = [d for d in self._items if not d["done"]]
        self._refresh_list()

    def select_all_done(self):
        all_done = all(d["done"] for d in self._items) if self._items else False
        for d in self._items:
            d["done"] = not all_done
        self._refresh_list()

    def _on_double_click(self, item: QListWidgetItem):
        """双击列表项触发编辑。"""
        self.todo_list.setCurrentItem(item)
        self.edit_todo()

    def _apply_filter(self):
        """搜索框内容变化时重新过滤列表。"""
        self._refresh_list()

    def _apply_sort(self, index: int):
        """排序下拉变化时重新排序。"""
        if index == 1:  # Name
            self._items.sort(key=lambda d: d["text"].lower())
        elif index == 2:  # Priority
            self._items.sort(key=lambda d: PRIORITY_ORDER.get(d["priority"], 9))
        elif index == 3:  # Status
            self._items.sort(key=lambda d: (d["done"], d["text"].lower()))
        # index == 0: Default, 不排序
        self._refresh_list()

    def _update_stats(self):
        total = len(self._items)
        done = sum(1 for d in self._items if d["done"])
        pending = total - done
        high = sum(1 for d in self._items if d["priority"] == "High" and not d["done"])
        self.stats_label.setText(
            f"Total: {total} | Done: {done} | Pending: {pending} | Urgent: {high}"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = TodoApp()
    window.show()
    sys.exit(app.exec_())
