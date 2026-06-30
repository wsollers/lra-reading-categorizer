from __future__ import annotations

import sys
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import APP_VERSION
from .core import CategorizerStore, app_last_modified, load_categories, open_pdf_in_chrome


class CategorizerApp(tk.Tk):
    def __init__(self, store: CategorizerStore, chrome_path: Path | None = None) -> None:
        super().__init__()
        self.store = store
        self.chrome_path = chrome_path
        self.categories = load_categories()
        self.main_labels = {category.main_slug: category.main_label for category in self.categories}
        self.main_by_label = {category.main_label: category.main_slug for category in self.categories}
        self.subs_by_main: dict[str, list[tuple[str, str]]] = {}
        for category in self.categories:
            self.subs_by_main.setdefault(category.main_slug, []).append((category.sub_slug, category.sub_label))
        self.current = None
        self.viewer_process: subprocess.Popen | None = None
        self.title("LRA Reading Categorizer")
        self.geometry("980x560")
        self.minsize(820, 480)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.create_widgets()
        self.load_next()

    def create_widgets(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)

        top = ttk.Frame(outer)
        top.pack(fill=tk.X)
        self.progress_var = tk.StringVar(value="Record 0 of 0")
        ttk.Label(top, textvariable=self.progress_var, font=("Segoe UI", 12, "bold")).pack(side=tk.LEFT)
        self.source_var = tk.StringVar()
        ttk.Label(top, textvariable=self.source_var).pack(side=tk.RIGHT)

        body = ttk.Frame(outer)
        body.pack(fill=tk.BOTH, expand=True, pady=(12, 8))
        body.columnconfigure(1, weight=1)

        self.filename_var = tk.StringVar()
        self.path_var = tk.StringVar()
        self.title_var = tk.StringVar()
        self.isbn_var = tk.StringVar()
        self.author_var = tk.StringVar()
        self.main_var = tk.StringVar()
        self.sub_var = tk.StringVar()

        self.add_label_entry(body, 0, "Filename", self.filename_var, readonly=True)
        self.add_label_entry(body, 1, "Source path", self.path_var, readonly=True)
        self.add_label_entry(body, 2, "Title", self.title_var)
        self.add_label_entry(body, 3, "ISBN", self.isbn_var)
        self.add_label_entry(body, 4, "First author", self.author_var)

        ttk.Label(body, text="Main category").grid(row=5, column=0, sticky=tk.W, pady=4)
        self.main_combo = ttk.Combobox(body, textvariable=self.main_var, values=list(self.main_by_label), state="readonly")
        self.main_combo.grid(row=5, column=1, sticky=tk.EW, pady=4)
        self.main_combo.bind("<<ComboboxSelected>>", self.on_main_changed)

        ttk.Label(body, text="Subcategory").grid(row=6, column=0, sticky=tk.W, pady=4)
        self.sub_combo = ttk.Combobox(body, textvariable=self.sub_var, state="readonly")
        self.sub_combo.grid(row=6, column=1, sticky=tk.EW, pady=4)

        ttk.Label(body, text="Notes").grid(row=7, column=0, sticky=tk.NW, pady=4)
        self.notes = tk.Text(body, height=6, wrap=tk.WORD)
        self.notes.grid(row=7, column=1, sticky=tk.NSEW, pady=4)
        body.rowconfigure(7, weight=1)

        self.status_var = tk.StringVar()
        ttk.Label(outer, textvariable=self.status_var).pack(fill=tk.X, pady=(0, 8))

        buttons = ttk.Frame(outer)
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Open PDF", command=self.open_pdf).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Skip", command=self.skip).pack(side=tk.RIGHT, padx=(0, 8))
        ttk.Button(buttons, text="Refresh", command=self.load_next).pack(side=tk.RIGHT, padx=(0, 8))

        footer = ttk.Frame(outer)
        footer.pack(fill=tk.X, pady=(8, 0))
        ttk.Label(footer, text=f"Version {APP_VERSION} | Last modified {app_last_modified()}").pack(side=tk.RIGHT)

    def add_label_entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, readonly: bool = False) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=4)
        entry = ttk.Entry(parent, textvariable=variable)
        if readonly:
            entry.configure(state="readonly")
        entry.grid(row=row, column=1, sticky=tk.EW, pady=4)

    def on_main_changed(self, event: object | None = None) -> None:
        main_slug = self.main_by_label.get(self.main_var.get(), "")
        subs = self.subs_by_main.get(main_slug, [])
        labels = [label for _, label in subs]
        self.sub_combo.configure(values=labels)
        if labels and self.sub_var.get() not in labels:
            self.sub_var.set(labels[0])

    def set_category(self, main_slug: str, sub_slug: str) -> None:
        self.main_var.set(self.main_labels.get(main_slug, "Reference and Miscellaneous"))
        self.on_main_changed()
        sub_label = next((label for slug, label in self.subs_by_main.get(main_slug, []) if slug == sub_slug), "")
        if sub_label:
            self.sub_var.set(sub_label)

    def selected_category_slugs(self) -> tuple[str, str]:
        main_slug = self.main_by_label.get(self.main_var.get(), "")
        sub_slug = ""
        for slug, label in self.subs_by_main.get(main_slug, []):
            if label == self.sub_var.get():
                sub_slug = slug
                break
        return main_slug, sub_slug

    def load_next(self) -> None:
        self.close_pdf_viewer()
        self.current = self.store.current_pending()
        total = self.store.queue_count()
        processed = self.store.processed_count()
        if not self.current:
            self.progress_var.set(f"Complete: {processed} of {total}")
            self.source_var.set("")
            self.status_var.set("No pending records.")
            return
        row = self.current
        self.progress_var.set(f"Record {processed + 1} of {total}")
        self.source_var.set(str(row["source_id"]))
        self.filename_var.set(str(row["filename"]))
        self.path_var.set(str(row["source_path"]))
        self.title_var.set(str(row["title"]))
        self.isbn_var.set(str(row["isbn"]))
        self.author_var.set(str(row["first_author"]))
        self.set_category(str(row["main_category"]), str(row["sub_category"]))
        self.notes.delete("1.0", tk.END)
        self.notes.insert("1.0", str(row["notes"] or ""))
        self.status_var.set("Loaded pending record.")
        self.open_pdf()

    def open_pdf(self) -> None:
        if not self.current:
            return
        try:
            self.close_pdf_viewer()
            self.viewer_process = open_pdf_in_chrome(Path(str(self.current["source_path"])), self.chrome_path)
            self.status_var.set("Opened PDF.")
        except Exception as exc:
            self.status_var.set(f"Could not open PDF: {exc}")

    def close_pdf_viewer(self) -> None:
        process = self.viewer_process
        self.viewer_process = None
        if not process:
            return
        if process.poll() is not None:
            return
        try:
            if sys.platform.startswith("win"):
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                process.terminate()
                process.wait(timeout=2)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def save(self) -> None:
        if not self.current:
            return
        main_slug, sub_slug = self.selected_category_slugs()
        if not main_slug or not sub_slug:
            messagebox.showerror("Missing category", "Choose a main category and subcategory.")
            return
        try:
            result = self.store.save_record(
                str(self.current["source_id"]),
                self.title_var.get().strip(),
                self.isbn_var.get().strip(),
                self.author_var.get().strip(),
                main_slug,
                sub_slug,
                self.notes.get("1.0", tk.END).strip(),
            )
            self.close_pdf_viewer()
            self.status_var.set(f"Saved: {result['copy_status']} -> {result['destination']}")
            self.load_next()
        except Exception as exc:
            messagebox.showerror("Save failed", str(exc))
            self.status_var.set(f"Save failed: {exc}")

    def skip(self) -> None:
        if not self.current:
            return
        self.close_pdf_viewer()
        self.store.skip_record(str(self.current["source_id"]), self.notes.get("1.0", tk.END).strip())
        self.status_var.set("Skipped record.")
        self.load_next()

    def on_close(self) -> None:
        self.close_pdf_viewer()
        self.store.close()
        self.destroy()
