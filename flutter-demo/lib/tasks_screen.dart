import 'package:flutter/material.dart';

class Task {
  String title;
  bool done;
  Task(this.title, {this.done = false});
}

/// 任务列表页
/// 预埋 Bug：
///   Bug-3: "待办" 计数器显示的是总任务数，而不是未完成任务数
///   Bug-4: 删除最后一个任务后，list index out of range 崩溃（_selected 未重置）
class TasksScreen extends StatefulWidget {
  const TasksScreen({super.key});

  @override
  State<TasksScreen> createState() => _TasksScreenState();
}

class _TasksScreenState extends State<TasksScreen> {
  final _tasks = <Task>[
    Task('买牛奶'),
    Task('写报告'),
    Task('修复登录Bug'),
  ];
  final _inputCtrl = TextEditingController();
  int _selected = 0; // Bug-4: 删完最后一项后 _selected 不重置

  void _addTask() {
    final t = _inputCtrl.text.trim();
    if (t.isEmpty) return;
    setState(() {
      _tasks.add(Task(t));
      _inputCtrl.clear();
    });
  }

  void _deleteTask(int index) {
    setState(() {
      _tasks.removeAt(index);
      // Bug-4: 删完后 _selected 可能超出范围，后续操作会崩溃
      // 正确做法应为: if (_selected >= _tasks.length) _selected = 0;
    });
  }

  void _toggleTask(int index) {
    setState(() => _tasks[index].done = !_tasks[index].done);
  }

  int get _pendingCount {
    // Bug-3: 返回总数而非待办数（正确应为 .where((t) => !t.done).length）
    return _tasks.length;
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('我的任务'),
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'logout',
            onPressed: () => Navigator.pushReplacementNamed(context, '/'),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(12),
            child: Semantics(
              label: 'txt_pending',
              child: Text(
                '待办任务：$_pendingCount 项', // Bug-3: 永远显示总数
                style:
                    const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(children: [
              Expanded(
                child: TextField(
                  controller: _inputCtrl,
                  decoration: const InputDecoration(
                      labelText: '新任务', hintText: 'tf_new_task'),
                ),
              ),
              const SizedBox(width: 8),
              Semantics(
                label: 'btn_add',
                button: true,
                child: ElevatedButton(
                    onPressed: _addTask, child: const Text('添加')),
              ),
            ]),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: ListView.builder(
              itemCount: _tasks.length,
              itemBuilder: (ctx, i) => ListTile(
                leading: Semantics(
                  label: 'chk_task_$i',
                  child: Checkbox(
                      value: _tasks[i].done, onChanged: (_) => _toggleTask(i)),
                ),
                title: Text(
                  _tasks[i].title,
                  // Bug-4: 完成后没有 strikeThrough 样式（视觉上无反馈）
                ),
                trailing: Semantics(
                  label: 'btn_delete_$i',
                  button: true,
                  child: IconButton(
                    icon: const Icon(Icons.delete, color: Colors.red),
                    onPressed: () => _deleteTask(i),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
