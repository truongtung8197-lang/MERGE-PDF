"""Giao diện CustomTkinter cho PDF Merger Tool - phong cách modern/flat."""

import os
import subprocess
import threading
from pathlib import Path

import customtkinter as ctk
from tkinter import END, Listbox, filedialog, messagebox

from merger_core import merge_pdfs, parse_input, resolve_output_path

ctk.set_appearance_mode("dark")  # "dark" | "light" | "system"
ctk.set_default_color_theme("blue")  # theme accent màu xanh

# Style Listbox (đồng bộ khi đổi style drag)
LIST_BG = "#2b2b2b"
LIST_FONT = ("Consolas", 12)
LIST_FG = "white"
# Màu nổi bật khi đang kéo: nền vàng + chữ đen (Listbox không hỗ trợ font từng dòng)
DRAG_BG = "#FFD700"
DRAG_FG = "#000000"


class PDFMergerApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("PDF Merger Tool")
        self.WINDOW_W = 620
        self.WINDOW_H = 740
        self.geometry(f"{self.WINDOW_W}x{self.WINDOW_H}")
        self.minsize(620, 730)  # minimum: đủ nút + log ~5 dòng kể cả sau khi mở folder
        self.resizable(True, True)

        # ===== Biến =====
        self.input_var = ctk.StringVar()
        self.output_folder_var = ctk.StringVar(value="")
        self.output_name_var = ctk.StringVar(value="merged.pdf")
        self.pdf_files: list[str] = []  # nguồn dữ liệu thật dùng để merge
        self.file_listbox = None
        self.merge_btn = None
        self.open_folder_btn = None
        self._last_output_path = None
        self._merge_running = False
        self._drag_block = None  # list index đang được kéo thả

        self._build_layout()
        self._center_window()
        self._log("Chào mừng! Chọn Folder hoặc Files PDF để bắt đầu.", "info")

    def _center_window(self):
        """Căn cửa sổ vào giữa trên (y ≈ 1/3 màn hình) tránh log bị taskbar che."""
        w, h = self.WINDOW_W, self.WINDOW_H
        x = (self.winfo_screenwidth() - w) // 2
        y = max(0, (self.winfo_screenheight() - h) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ================= LAYOUT =================
    def _build_layout(self):
        # --- Header ---
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(10, 4))

        ctk.CTkLabel(
            header,
            text="📄  PDF Merger",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(anchor="w")

        # --- Card chứa form ---
        card = ctk.CTkFrame(self, corner_radius=14)
        card.pack(fill="x", padx=24, pady=6)

        pad = {"padx": 20, "pady": (4, 0)}

        # --- Input ---
        ctk.CTkLabel(
            card, text="Nguồn PDF", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", **pad)
        input_row = ctk.CTkFrame(card, fg_color="transparent")
        input_row.pack(fill="x", padx=20, pady=(4, 0))
        ctk.CTkEntry(
            input_row,
            textvariable=self.input_var,
            placeholder_text="Chọn Folder hoặc nhiều file PDF...",
            height=34,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            input_row, text="Folder", width=80, height=34, command=self._pick_folder
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            input_row, text="Files", width=80, height=34, command=self._pick_files
        ).pack(side="left")

        # --- Danh sách file (thứ tự ghép) ---
        ctk.CTkLabel(
            card,
            text="Danh sách file (thứ tự ghép) - kéo thả để sắp xếp",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(anchor="w", **pad)

        list_box_frame = ctk.CTkFrame(card, corner_radius=10)
        list_box_frame.pack(fill="x", padx=20, pady=(4, 0))

        inner = ctk.CTkFrame(list_box_frame, fg_color="transparent")
        inner.pack(fill="x", padx=8, pady=6)

        # Listbox + scrollbar (bên trái, chiếm hết chỗ)
        list_col = ctk.CTkFrame(inner, fg_color="transparent")
        list_col.pack(side="left", fill="x", expand=True)

        scrollbar = ctk.CTkScrollbar(list_col)
        scrollbar.pack(side="right", fill="y")

        self.file_listbox = Listbox(
            list_col,
            bg=LIST_BG,
            fg=LIST_FG,
            selectbackground="#1f6aa5",
            selectmode="extended",
            exportselection=False,
            font=LIST_FONT,
            height=2,
            activestyle="none",
            highlightthickness=0,
            bd=0,
            yscrollcommand=scrollbar.set,
        )
        self.file_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.file_listbox.yview)

        # Bind sự kiện: double-click xoá + kéo thả sắp xếp
        self.file_listbox.bind("<Double-Button-1>", self._on_double_click_delete)
        self.file_listbox.bind("<Button-1>", self._on_drag_start)
        self.file_listbox.bind("<B1-Motion>", self._on_drag_motion)
        self.file_listbox.bind("<ButtonRelease-1>", self._on_drag_end)

        # Cột nút thao tác (bên phải)
        btn_col = ctk.CTkFrame(inner, fg_color="transparent")
        btn_col.pack(side="left", padx=(8, 0))

        btn_specs = [
            ("↑ Lên", self._move_up),
            ("↓ Xuống", self._move_down),
            ("🗑 Xoá", self._delete_selected),
            ("Xoá tất cả", self._delete_all),
        ]
        for text, cmd in btn_specs:
            ctk.CTkButton(
                btn_col,
                text=text,
                width=90,
                height=30,
                command=cmd,
                font=ctk.CTkFont(size=12),
            ).pack(pady=(0, 4))

        # --- Output folder ---
        ctk.CTkLabel(
            card, text="Thư mục Output", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", **pad)
        out_row = ctk.CTkFrame(card, fg_color="transparent")
        out_row.pack(fill="x", padx=20, pady=(4, 0))
        ctk.CTkEntry(
            out_row,
            textvariable=self.output_folder_var,
            placeholder_text="Để trống = lưu cùng folder chứa PDF đầu tiên",
            height=34,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            out_row,
            text="Chọn...",
            width=80,
            height=34,
            command=self._pick_output_folder,
        ).pack(side="left")
        ctk.CTkLabel(
            card,
            text="💡 Để trống: file sẽ được lưu cùng folder chứa PDF đầu tiên (folder input)",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=20, pady=(3, 0))

        # --- Output filename ---
        ctk.CTkLabel(
            card, text="Tên file output", font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", **pad)
        ctk.CTkEntry(card, textvariable=self.output_name_var, height=34).pack(
            fill="x", padx=20, pady=(4, 0)
        )

        # --- Nút merge ---
        self.merge_btn = ctk.CTkButton(
            card,
            text="⚡  GHÉP FILE PDF",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42,
            corner_radius=10,
            fg_color="#2FA572",
            hover_color="#268A5F",
            command=self._on_merge,
        )
        self.merge_btn.pack(fill="x", padx=20, pady=(6, 8))

        # Nút mở folder output — ẩn mặc định, chỉ hiện sau khi ghép thành công
        self.open_folder_btn = ctk.CTkButton(
            card,
            text="📂  Mở thư mục Output",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=36,
            corner_radius=10,
            fg_color="transparent",
            border_width=2,
            border_color="#2FA572",
            text_color="#2FA572",
            hover_color="#1F5C45",
            command=self._open_output_folder,
        )
        self.open_folder_btn.pack(fill="x", padx=20, pady=(0, 14))
        self.open_folder_btn.pack_forget()  # ẩn ban đầu

        # --- Log ---
        log_label = ctk.CTkLabel(
            self, text="Trạng thái", font=ctk.CTkFont(size=13, weight="bold")
        )
        log_label.pack(anchor="w", padx=24, pady=(2, 4))

        self.log_box = ctk.CTkTextbox(
            self,
            height=170,
            corner_radius=10,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.log_box.pack(fill="both", expand=True, padx=24, pady=(0, 6))
        self.log_box.configure(state="disabled")

        # Tag màu cho log (CTkTextbox kế thừa tkinter Text nên dùng tag_config được)
        self.log_box._textbox.tag_config("info", foreground="#8ab4f8")
        self.log_box._textbox.tag_config("success", foreground="#4CAF50")
        self.log_box._textbox.tag_config("error", foreground="#ff6b6b")
        self.log_box._textbox.tag_config("default", foreground="#dddddd")

        # Ghi chú
        ctk.CTkLabel(
            self,
            text="Output trùng tên sẽ tự động thêm _1, _2...",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray60"),
        ).pack(anchor="w", padx=24, pady=(0, 8))

    # ================= LOG =================
    def _log(self, msg: str, level: str = "default"):
        self.log_box.configure(state="normal")
        prefix = {"info": "ℹ️ ", "success": "✅ ", "error": "❌ "}.get(level, "")
        self.log_box._textbox.insert("end", prefix + msg + "\n", level)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ================= FILE LIST =================
    def refresh_file_list(self):
        """Xoá toàn bộ Listbox và insert lại từ self.pdf_files (hiện basename)."""
        if self.file_listbox is None:
            return
        self.file_listbox.delete(0, END)
        for f in self.pdf_files:
            self.file_listbox.insert(END, os.path.basename(f))

        count = len(self.pdf_files)
        self.input_var.set(f"{count} file đã chọn" if count else "")

    def _on_double_click_delete(self, event):
        """Double-click vào 1 dòng → xoá dòng đó."""
        sel = self.file_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self.pdf_files):
            self.pdf_files.pop(idx)
            self.refresh_file_list()

    # ================= DRAG STYLE =================
    def _apply_drag_style(self):
        """Nổi bật các item đang kéo: nền vàng + chữ đen."""
        if not self._drag_block:
            return
        for i in self._drag_block:
            if 0 <= i < self.file_listbox.size():
                self.file_listbox.itemconfig(i, bg=DRAG_BG, fg=DRAG_FG)

    def _reset_drag_style(self):
        """Trả lại nền/font thường cho toàn bộ Listbox."""
        for i in range(self.file_listbox.size()):
            self.file_listbox.itemconfig(i, bg=LIST_BG, fg=LIST_FG)

    # ================= SORT BUTTONS =================
    def _move_up(self):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        block = list(sel)
        if min(block) <= 0:
            return
        new_block = self._move_block(block, min(block) - 1)
        self.refresh_file_list()
        self._select_block(new_block)

    def _move_down(self):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        block = list(sel)
        if max(block) >= len(self.pdf_files) - 1:
            return
        new_block = self._move_block(block, max(block) + 1)
        self.refresh_file_list()
        self._select_block(new_block)

    def _delete_selected(self):
        sel = self.file_listbox.curselection()
        if not sel:
            return
        # Xoá tất cả các item đang chọn (từ cuối lên đầu để không lệch index)
        for idx in reversed(sel):
            if 0 <= idx < len(self.pdf_files):
                self.pdf_files.pop(idx)
        self.refresh_file_list()

    def _delete_all(self):
        self.pdf_files = []
        self.refresh_file_list()

    def _select_block(self, indices):
        """Chọn lại một block các index (dùng sau khi di chuyển)."""
        self.file_listbox.selection_clear(0, END)
        for i in indices:
            self.file_listbox.selection_set(i)

    # ================= DRAG & DROP =================
    def _on_drag_start(self, event):
        """Bắt đầu kéo: ghi nhận block các item đang được chọn."""
        idx = self.file_listbox.nearest(event.y)
        if idx < 0:
            return
        sel = self.file_listbox.curselection()
        shift_held = bool(event.state & 0x0001)
        if idx not in sel:
            if not shift_held:
                # Click vào item ngoài vùng chọn (không giữ Shift) → chỉ chọn item đó
                self.file_listbox.selection_clear(0, END)
                self.file_listbox.selection_set(idx)
                sel = (idx,)
            else:
                # Giữ Shift: thêm item vào vùng chọn hiện tại
                self.file_listbox.selection_set(idx)
                sel = self.file_listbox.curselection()
        self._drag_block = list(sel)
        self._apply_drag_style()

    def _on_drag_motion(self, event):
        """Kéo: tự cuộn + di chuyển block tới vị trí con trỏ."""
        if not self._drag_block:
            return
        self._auto_scroll_list(event.y)
        target = self.file_listbox.nearest(event.y)
        if target < 0 or target >= len(self.pdf_files):
            return
        block_min = min(self._drag_block)
        block_max = max(self._drag_block)
        if target == block_min and target == block_max:
            return
        new_block = self._move_block(self._drag_block, target)
        self._drag_block = new_block
        self.refresh_file_list()
        # Giữ highlight + tô màu/in đậm trên block vừa di chuyển
        self._select_block(new_block)
        self._apply_drag_style()

    def _on_drag_end(self, event):
        self._reset_drag_style()
        self._drag_block = None

    def _auto_scroll_list(self, y):
        """Tự cuộn Listbox khi kéo gần biên trên/dưới."""
        h = self.file_listbox.winfo_height()
        if y < 20:
            self.file_listbox.yview_scroll(-1, "units")
        elif y > h - 20:
            self.file_listbox.yview_scroll(1, "units")

    def _move_block(self, src_indices, target_idx):
        """Di chuyển một block các index (đã sort) tới trước vị trí target_idx.

        Trả về list index mới của block sau khi di chuyển.
        """
        if not src_indices:
            return []
        block = [self.pdf_files[i] for i in src_indices]
        for i in reversed(src_indices):
            del self.pdf_files[i]
        if target_idx > src_indices[-1]:
            insert_at = target_idx - len(block) + 1
        else:
            insert_at = target_idx
        insert_at = max(0, min(insert_at, len(self.pdf_files)))
        for off, f in enumerate(block):
            self.pdf_files.insert(insert_at + off, f)
        return list(range(insert_at, insert_at + len(block)))

    # ================= HANDLERS =================
    def _pick_folder(self):
        folder = filedialog.askdirectory(title="Chọn Folder chứa PDF")
        if not folder:
            return
        pdf_files, err = parse_input(folder)
        if err:
            messagebox.showerror("Lỗi", err)
            self._log(err, "error")
            return
        self.pdf_files = pdf_files
        self.refresh_file_list()
        self.input_var.set(f"{len(pdf_files)} file đã chọn từ folder: {folder}")
        self._log(f"Đã nạp {len(pdf_files)} file từ folder: {folder}", "info")

    def _pick_files(self):
        files = filedialog.askopenfilenames(
            title="Chọn file PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not files:
            return
        # Giữ nguyên thứ tự người dùng chọn trong dialog
        self.pdf_files = list(files)
        self.refresh_file_list()
        self._log(f"Đã nạp {len(files)} file theo thứ tự bạn chọn.", "info")

    def _pick_output_folder(self):
        folder = filedialog.askdirectory(title="Chọn Folder lưu output")
        if folder:
            self.output_folder_var.set(folder)

    # ================= MERGE =================
    def _on_merge(self):
        if self._merge_running:
            return

        # Reset trạng thái nút mở folder từ lần ghép trước
        self.open_folder_btn.pack_forget()
        self._last_output_path = None

        pdf_paths = list(self.pdf_files)
        if not pdf_paths:
            messagebox.showerror("Lỗi", "Chưa có file PDF nào trong danh sách.")
            self._log("Chưa có file PDF nào trong danh sách.", "error")
            return

        if len(pdf_paths) == 1:
            msg = "Chỉ có 1 file PDF, thực chất chỉ là copy. Vẫn tiếp tục?"
            if not messagebox.askyesno("Xác nhận", msg):
                return

        out_dir = self.output_folder_var.get().strip()
        if not out_dir:
            out_dir = str(Path(pdf_paths[0]).parent)

        output_path = resolve_output_path(out_dir, self.output_name_var.get())
        self._last_output_path = str(output_path)

        self._merge_running = True
        self.merge_btn.configure(state="disabled", text="Đang ghép...")

        self._log(f"Đã tìm thấy {len(pdf_paths)} file PDF.", "info")

        def worker():
            success, msg = merge_pdfs(
                pdf_paths, output_path, log_callback=lambda m: self._log(m, "default")
            )
            self.after(0, self._merge_done, success, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _merge_done(self, success, msg):
        self._merge_running = False
        self.merge_btn.configure(state="normal", text="⚡  GHÉP FILE PDF")
        if success:
            self._log(msg, "success")
            messagebox.showinfo("Hoàn tất", msg)
            # Hiện nút mở folder sau khi ghép thành công
            if self._last_output_path:
                self.open_folder_btn.pack(
                    fill="x", padx=20, pady=(0, 14), after=self.merge_btn
                )
                # Mở rộng cửa sổ thêm ~60px để log không bị che bởi nút mới hiện
                self.geometry(f"{self.winfo_width()}x{self.winfo_height() + 60}")
                self.update_idletasks()
        else:
            self._log(msg, "error")
            messagebox.showerror("Lỗi", msg)

    # ================= OPEN OUTPUT FOLDER =================
    def _open_output_folder(self):
        """Mở File Explorer tới file output vừa tạo (file được chọn sẵn)."""
        path = self._last_output_path
        if not path or not Path(path).exists():
            messagebox.showwarning("Chưa có file", "Chưa có file output nào để mở.")
            return

        try:
            # Windows: mở Explorer và chọn sẵn file vừa tạo
            subprocess.Popen(f'explorer /select,"{path}"')
            self._log(f"Đã mở folder chứa file output: {path}", "info")
        except Exception:
            # Fallback: mở thẳng folder chứa file
            try:
                os.startfile(str(Path(path).parent))
            except Exception as e:
                self._log(f"Không mở được folder: {e}", "error")


if __name__ == "__main__":
    app = PDFMergerApp()
    app.mainloop()
