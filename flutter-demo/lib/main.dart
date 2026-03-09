import 'package:flutter/material.dart';
import 'login_screen.dart';
import 'tasks_screen.dart';

void main() {
  runApp(const TaskPilotApp());
}

class TaskPilotApp extends StatelessWidget {
  const TaskPilotApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TaskPilot Demo',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.indigo),
        useMaterial3: true,
        inputDecorationTheme: const InputDecorationTheme(
          border: OutlineInputBorder(),
          filled: true,
        ),
      ),
      initialRoute: '/',
      routes: {
        '/': (ctx) => const LoginScreen(),
        '/tasks': (ctx) => const TasksScreen(),
      },
    );
  }
}
