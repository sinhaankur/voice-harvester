"""
VoiceHarvester - drag-and-drop desktop app.

Drop in video/audio files, click "Extract Voice", and get clean WAVs
ready for AI voice-cloning tools.

Run with:  python app.py
Drag-and-drop needs the optional package 'tkinterdnd2'. If it's missing,
the app still works via the "Add files..." button.
"""

import os
import sys
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import engine

# Optional drag-and-drop support.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND = True
except Exception:
    _DND = False


APP_TITLE = "VoiceHarvester - voice extractor for AI tools"


class App:
    def __init__(self, root):
        self.root = root
        root.title(APP_TITLE)
        root.geometry("680x560")
        root.minsize(560, 480)

        self.files = []           # input paths
        self.out_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "VoiceHarvester_output"))
        self.merge_var = tk.BooleanVar(value=False)
        self.demucs_var = tk.BooleanVar(value=engine.have_demucs())
        self.log_q = queue.Queue()

        self._build_ui()
        self._poll_log()
        self._check_ffmpeg()

    # ---------- UI ----------
    def _build_ui(self):
        pad = dict(padx=10, pady=6)

        head = ttk.Label(self.root, text="Drop video or audio files below",
                         font=("Helvetica", 13, "bold"))
        head.pack(anchor="w", **pad)

        # Drop zone / list
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=10)

        self.listbox = tk.Listbox(frame, selectmode=tk.EXTENDED, height=10,
                                  bg="#fafafa", relief="groove", bd=2)
        self.listbox.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.listbox.yview)
        sb.pack(side="right", fill="y")
        self.listbox.config(yscrollcommand=sb.set)

        if _DND:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind("<<Drop>>", self._on_drop)
            hint = "Tip: drag files straight onto the list, or use Add files."
        else:
            hint = "Tip: install 'tkinterdnd2' for drag-and-drop. For now, use Add files."
        ttk.Label(self.root, text=hint, foreground="#666").pack(anchor="w", **pad)

        # File buttons
        btns = ttk.Frame(self.root)
        btns.pack(fill="x", **pad)
        ttk.Button(btns, text="Add files...", command=self._add_files).pack(side="left")
        ttk.Button(btns, text="Remove selected", command=self._remove_selected).pack(side="left", padx=6)
        ttk.Button(btns, text="Clear", command=self._clear).pack(side="left")

        # Options
        opt = ttk.LabelFrame(self.root, text="Options")
        opt.pack(fill="x", padx=10, pady=6)
        ttk.Checkbutton(
            opt, text="Best-quality voice isolation (Demucs, if installed)",
            variable=self.demucs_var,
        ).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(
            opt, text="Also merge everything into one combined sample",
            variable=self.merge_var,
        ).pack(anchor="w", padx=8, pady=2)

        outrow = ttk.Frame(opt)
        outrow.pack(fill="x", padx=8, pady=4)
        ttk.Label(outrow, text="Save to:").pack(side="left")
        ttk.Entry(outrow, textvariable=self.out_dir).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(outrow, text="...", width=3, command=self._pick_out).pack(side="left")

        # Run + progress
        self.run_btn = ttk.Button(self.root, text="Extract Voice", command=self._run)
        self.run_btn.pack(fill="x", padx=10, pady=(8, 2))
        self.progress = ttk.Progressbar(self.root, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=2)

        # Log
        self.log = tk.Text(self.root, height=7, state="disabled", bg="#1e1e1e",
                           fg="#d4d4d4", relief="flat")
        self.log.pack(fill="both", expand=False, padx=10, pady=(6, 10))

    # ---------- helpers ----------
    def _check_ffmpeg(self):
        if not engine.have_ffmpeg():
            messagebox.showwarning(
                "ffmpeg not found",
                "ffmpeg / ffprobe are required but were not found on your PATH.\n\n"
                "Install ffmpeg, then restart this app.\n"
                "  macOS:   brew install ffmpeg\n"
                "  Windows: winget install Gyan.FFmpeg\n"
                "  Linux:   sudo apt install ffmpeg",
            )
        self._log("Ready." + ("  (Demucs detected)" if engine.have_demucs()
                              else "  (Demucs not installed - ffmpeg cleanup will be used)"))

    def _add_paths(self, paths):
        added = 0
        for p in paths:
            p = p.strip().strip("{}")  # DnD wraps spaced paths in braces
            if not p:
                continue
            if os.path.splitext(p)[1].lower() in engine.SUPPORTED_EXTS and p not in self.files:
                self.files.append(p)
                self.listbox.insert(tk.END, os.path.basename(p))
                added += 1
        if added:
            self._log(f"Added {added} file(s).")

    def _on_drop(self, event):
        # event.data is a space-separated list, braces around spaced paths
        raw = self.root.tk.splitlist(event.data)
        self._add_paths(list(raw))

    def _add_files(self):
        exts = " ".join("*" + e for e in sorted(engine.SUPPORTED_EXTS))
        paths = filedialog.askopenfilenames(
            title="Choose video or audio files",
            filetypes=[("Media files", exts), ("All files", "*.*")],
        )
        self._add_paths(list(paths))

    def _remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            del self.files[i]
            self.listbox.delete(i)

    def _clear(self):
        self.files.clear()
        self.listbox.delete(0, tk.END)

    def _pick_out(self):
        d = filedialog.askdirectory(title="Choose output folder")
        if d:
            self.out_dir.set(d)

    def _log(self, msg):
        self.log_q.put(msg)

    def _poll_log(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.log.config(state="normal")
                self.log.insert(tk.END, msg + "\n")
                self.log.see(tk.END)
                self.log.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(120, self._poll_log)

    # ---------- run ----------
    def _run(self):
        if not self.files:
            messagebox.showinfo("No files", "Add some video or audio files first.")
            return
        if not engine.have_ffmpeg():
            messagebox.showerror("ffmpeg missing", "Install ffmpeg and restart.")
            return
        self.run_btn.config(state="disabled")
        self.progress.config(value=0, maximum=len(self.files))
        t = threading.Thread(target=self._worker, daemon=True)
        t.start()

    def _worker(self):
        out_dir = self.out_dir.get()
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            self._log(f"Cannot create output folder: {e}")
            self.root.after(0, lambda: self.run_btn.config(state="normal"))
            return

        def progress(i, total, name):
            self.root.after(0, lambda: self.progress.config(value=i))

        results = engine.process_batch(
            self.files, out_dir,
            use_demucs=self.demucs_var.get(),
            merge=self.merge_var.get(),
            progress=progress,
            log=self._log,
        )

        ok = [r for r in results if r.ok]
        bad = [r for r in results if not r.ok]
        self._log("")
        self._log(f"Done. {len(ok)} succeeded, {len(bad)} failed.")
        self._log(f"Output folder: {out_dir}")

        def finish():
            self.run_btn.config(state="normal")
            messagebox.showinfo(
                "Finished",
                f"{len(ok)} file(s) processed.\nSaved to:\n{out_dir}",
            )
        self.root.after(0, finish)


def main():
    if _DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
