package com.testpilot.noteapp;

import android.app.AlertDialog;
import android.os.Bundle;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import java.util.ArrayList;
import java.util.List;

/**
 * 笔记列表页面。
 *
 * 预埋Bug-2：搜索区分大小写（应该不区分）。
 *   搜索 "hello" 找不到 "Hello World"。
 *
 * 预埋Bug-3：字数统计多算了一倍（乘以2）。
 *   3条笔记共15字，显示"总字数：30"。
 */
public class NoteListActivity extends AppCompatActivity {

    private final List<Note> allNotes = new ArrayList<>();
    private final List<Note> displayNotes = new ArrayList<>();
    private NoteAdapter adapter;
    private EditText etSearch;
    private EditText etNewNote;
    private ImageButton btnClearSearch;
    private TextView tvNoteCount;
    private TextView tvCharCount;
    private TextView tvEmpty;
    private RecyclerView rvNotes;
    private String currentFilter = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_note_list);

        etSearch = findViewById(R.id.et_search);
        btnClearSearch = findViewById(R.id.btn_clear_search);
        etNewNote = findViewById(R.id.et_new_note);
        tvNoteCount = findViewById(R.id.tv_note_count);
        tvCharCount = findViewById(R.id.tv_char_count);
        tvEmpty = findViewById(R.id.tv_empty);
        rvNotes = findViewById(R.id.rv_notes);

        // 初始化 RecyclerView
        adapter = new NoteAdapter(displayNotes, new NoteAdapter.OnNoteAction() {
            @Override
            public void onDelete(int position) {
                confirmDelete(position);
            }

            @Override
            public void onToggleStar(int position) {
                Note note = displayNotes.get(position);
                note.starred = !note.starred;
                adapter.notifyItemChanged(position);
            }
        });
        rvNotes.setLayoutManager(new LinearLayoutManager(this));
        rvNotes.setAdapter(adapter);

        // 添加默认笔记
        addNote("欢迎使用NoteApp");
        addNote("这是一个测试笔记");
        addNote("Hello World");

        // 搜索框监听
        etSearch.addTextChangedListener(new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence s, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence s, int start, int before, int count) {}
            @Override
            public void afterTextChanged(Editable s) {
                currentFilter = s.toString();
                btnClearSearch.setVisibility(currentFilter.isEmpty() ? View.GONE : View.VISIBLE);
                applyFilter();
            }
        });

        btnClearSearch.setOnClickListener(v -> etSearch.setText(""));

        // 添加按钮
        findViewById(R.id.btn_add).setOnClickListener(v -> {
            String text = etNewNote.getText().toString().trim();
            if (text.isEmpty()) {
                Toast.makeText(this, "请输入笔记内容", Toast.LENGTH_SHORT).show();
                return;
            }
            addNote(text);
            etNewNote.setText("");
        });

        updateStats();
    }

    private void addNote(String content) {
        Note note = new Note(content);
        allNotes.add(note);
        applyFilter();
        updateStats();
    }

    private void confirmDelete(int displayPos) {
        new AlertDialog.Builder(this)
                .setTitle("确认删除")
                .setMessage("确定要删除这条笔记吗？")
                .setPositiveButton("删除", (d, w) -> {
                    Note note = displayNotes.get(displayPos);
                    allNotes.remove(note);
                    applyFilter();
                    updateStats();
                })
                .setNegativeButton("取消", null)
                .show();
    }

    private void applyFilter() {
        displayNotes.clear();
        for (Note note : allNotes) {
            if (currentFilter.isEmpty()) {
                displayNotes.add(note);
            } else {
                // Bug-2：搜索区分大小写！
                // 正确做法应该是：note.content.toLowerCase().contains(currentFilter.toLowerCase())
                if (note.content.contains(currentFilter)) {
                    displayNotes.add(note);
                }
            }
        }
        adapter.notifyDataSetChanged();

        // 显示/隐藏空状态
        tvEmpty.setVisibility(displayNotes.isEmpty() ? View.VISIBLE : View.GONE);
        rvNotes.setVisibility(displayNotes.isEmpty() ? View.GONE : View.VISIBLE);
    }

    private void updateStats() {
        tvNoteCount.setText("共 " + allNotes.size() + " 条笔记");

        // Bug-3：字数统计多算了一倍（乘以2）！
        // 正确做法应该是直接 totalChars，不乘以2
        int totalChars = 0;
        for (Note note : allNotes) {
            totalChars += note.content.length();
        }
        tvCharCount.setText("总字数：" + (totalChars * 2));  // Bug! 多乘了2
    }

    /** 笔记数据模型 */
    static class Note {
        String content;
        boolean starred;

        Note(String content) {
            this.content = content;
            this.starred = false;
        }
    }
}
