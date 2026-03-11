package com.testpilot.noteapp;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import java.util.List;

public class NoteAdapter extends RecyclerView.Adapter<NoteAdapter.ViewHolder> {

    interface OnNoteAction {
        void onDelete(int position);
        void onToggleStar(int position);
    }

    private final List<NoteListActivity.Note> notes;
    private final OnNoteAction callback;

    public NoteAdapter(List<NoteListActivity.Note> notes, OnNoteAction callback) {
        this.notes = notes;
        this.callback = callback;
    }

    @NonNull
    @Override
    public ViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_note, parent, false);
        return new ViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ViewHolder holder, int position) {
        NoteListActivity.Note note = notes.get(position);
        holder.tvContent.setText(note.content);
        holder.tvContent.setContentDescription("note_" + position);

        holder.ivStar.setImageResource(
                note.starred ? android.R.drawable.btn_star_big_on : android.R.drawable.btn_star_big_off
        );
        holder.ivStar.setContentDescription(note.starred ? "starred_" + position : "unstarred_" + position);

        holder.ivStar.setOnClickListener(v -> callback.onToggleStar(holder.getAdapterPosition()));
        holder.btnDelete.setOnClickListener(v -> callback.onDelete(holder.getAdapterPosition()));
        holder.btnDelete.setContentDescription("btn_delete_" + position);
    }

    @Override
    public int getItemCount() {
        return notes.size();
    }

    static class ViewHolder extends RecyclerView.ViewHolder {
        final ImageView ivStar;
        final TextView tvContent;
        final ImageButton btnDelete;

        ViewHolder(@NonNull View itemView) {
            super(itemView);
            ivStar = itemView.findViewById(R.id.iv_star);
            tvContent = itemView.findViewById(R.id.tv_content);
            btnDelete = itemView.findViewById(R.id.btn_delete);
        }
    }
}
