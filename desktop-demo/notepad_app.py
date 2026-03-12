"""
TestPilot AI - Windows 桌面测试 Demo 应用
tkinter 笔记本程序，用于验证桌面测试流程。

tkinter 对 UI Automation 的支持较弱（控件 Name/AutomationId 多为空），
这恰恰代表了真实世界中许多桌面应用的情况。
TestPilot AI 必须能通过 AI 视觉降级来应对这类应用。

功能：
1. 登录页（用户名+密码）
2. 笔记列表页（添加、删除、搜索）
3. 字数统计

预埋Bug：
- Bug-1：空用户名点登录，提示"Please enter password"而非"Please enter username"
- Bug-2：搜索区分大小写（应不区分）
- Bug-3：字数统计多算一倍

启动：python notepad_app.py
"""

import tkinter as tk
from tkinter import messagebox


class NoteApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("NoteApp")
        self.root.geometry("400x500")
        self.root.resizable(False, False)

        # 数据
        self.notes: list[str] = ["Hello World", "Buy groceries", "Call Alice"]
        self.logged_in = False

        # 正确的登录凭据
        self.valid_user = "admin"
        self.valid_pass = "admin123"

        self._show_login()

    # ── 登录页 ──────────────────────────────────────

    def _show_login(self):
        self._clear()
        self.logged_in = False

        frame = tk.Frame(self.root, padx=30, pady=30)
        frame.pack(expand=True)

        tk.Label(frame, text="NoteApp", font=("Arial", 20, "bold")).pack(pady=(0, 5))
        tk.Label(frame, text="Simple note-taking app", font=("Arial", 9), fg="gray").pack(pady=(0, 20))

        # 用户名
        tk.Label(frame, text="Username", anchor="w").pack(fill="x")
        self.entry_user = tk.Entry(frame, width=30)
        self.entry_user.pack(pady=(0, 10))

        # 密码
        tk.Label(frame, text="Password", anchor="w").pack(fill="x")
        self.entry_pass = tk.Entry(frame, width=30, show="*")
        self.entry_pass.pack(pady=(0, 15))

        # 登录按钮
        self.btn_login = tk.Button(frame, text="Login", width=20, command=self._on_login)
        self.btn_login.pack(pady=(0, 10))

        # 错误提示
        self.lbl_error = tk.Label(frame, text="", fg="red", wraplength=300)
        self.lbl_error.pack()

    def _on_login(self):
        user = self.entry_user.get().strip()
        pwd = self.entry_pass.get().strip()

        # Bug-1：空用户名时提示"Please enter password"（应为"Please enter username"）
        if not user:
            self.lbl_error.config(text="Please enter password")
            return
        if not pwd:
            self.lbl_error.config(text="Please enter password")
            return
        if user != self.valid_user or pwd != self.valid_pass:
            self.lbl_error.config(text="Invalid username or password")
            return

        self.logged_in = True
        self._show_main()

    # ── 主页面（笔记列表）──────────────────────────

    def _show_main(self):
        self._clear()

        # 顶部栏
        top = tk.Frame(self.root, padx=10, pady=5)
        top.pack(fill="x")
        tk.Label(top, text="NoteApp", font=("Arial", 14, "bold")).pack(side="left")
        tk.Button(top, text="Logout", command=self._show_login).pack(side="right")

        # 搜索栏
        search_frame = tk.Frame(self.root, padx=10, pady=5)
        search_frame.pack(fill="x")
        self.entry_search = tk.Entry(search_frame, width=25)
        self.entry_search.pack(side="left", padx=(0, 5))
        tk.Button(search_frame, text="Search", command=self._on_search).pack(side="left")
        tk.Button(search_frame, text="Clear", command=self._on_clear_search).pack(side="left", padx=(5, 0))

        # 统计标签
        stat_frame = tk.Frame(self.root, padx=10, pady=2)
        stat_frame.pack(fill="x")
        self.lbl_count = tk.Label(stat_frame, text="", fg="blue")
        self.lbl_count.pack(side="left")
        self.lbl_chars = tk.Label(stat_frame, text="", fg="blue")
        self.lbl_chars.pack(side="right")

        # 笔记列表
        list_frame = tk.Frame(self.root, padx=10, pady=5)
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Arial", 11))
        self.listbox.pack(fill="both", expand=True)

        # 添加区域
        add_frame = tk.Frame(self.root, padx=10, pady=5)
        add_frame.pack(fill="x")
        self.entry_note = tk.Entry(add_frame, width=25)
        self.entry_note.pack(side="left", padx=(0, 5))
        tk.Button(add_frame, text="Add", command=self._on_add).pack(side="left")
        tk.Button(add_frame, text="Delete", command=self._on_delete).pack(side="left", padx=(5, 0))

        self._refresh_list()

    def _refresh_list(self, filtered: list[str] | None = None):
        self.listbox.delete(0, tk.END)
        items = filtered if filtered is not None else self.notes
        for note in items:
            self.listbox.insert(tk.END, note)

        count = len(self.notes)
        self.lbl_count.config(text=f"Total: {count} notes")

        # Bug-3：字数统计多算一倍
        total_chars = sum(len(n) for n in self.notes)
        self.lbl_chars.config(text=f"Total chars: {total_chars * 2}")

    def _on_add(self):
        text = self.entry_note.get().strip()
        if not text:
            return
        self.notes.append(text)
        self.entry_note.delete(0, tk.END)
        self._refresh_list()

    def _on_delete(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Warning", "Please select a note to delete")
            return
        idx = sel[0]
        note = self.notes[idx]
        if messagebox.askyesno("Confirm Delete", f"Delete '{note}'?"):
            del self.notes[idx]
            self._refresh_list()

    def _on_search(self):
        keyword = self.entry_search.get().strip()
        if not keyword:
            self._refresh_list()
            return
        # Bug-2：搜索区分大小写（应不区分）
        filtered = [n for n in self.notes if keyword in n]
        self._refresh_list(filtered)

    def _on_clear_search(self):
        self.entry_search.delete(0, tk.END)
        self._refresh_list()

    # ── 工具 ────────────────────────────────────────

    def _clear(self):
        for w in self.root.winfo_children():
            w.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = NoteApp(root)
    root.mainloop()

