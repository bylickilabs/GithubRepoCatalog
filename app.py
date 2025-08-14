import os
import sys
import sqlite3
import csv
import zipfile
import configparser
import webbrowser
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

import traceback
import logging

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

PIL_AVAILABLE = True
try:
    from PIL import Image, ImageTk
except Exception:
    PIL_AVAILABLE = False

APP_NAME = "GitHub Repo Catalog & Archiver"
APP_VERSION = "1.1.0"
APP_AUTHOR = "©Thorsten Bylicki | ©BYLICKILABS"
GITHUB_URL = "https://github.com/bylickilabs"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "repos.db")
LOG_PATH = os.path.join(BASE_DIR, "startup_error.log")

IMAGE_DIR_CANDIDATES = ("assets", "Assets", "media", "Media")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

TARGET_W, TARGET_H = 1280, 640
TARGET_AR = TARGET_W / TARGET_H

I18N = {
    "en": {
        "window_title": f"{APP_NAME} v{APP_VERSION}",
        "banner_title": APP_NAME,
        "author": f"{APP_AUTHOR}",
        "search": "Search",
        "placeholder_search": "Filter by name or path...",
        "scan_folder": "Scan Folder",
        "archive_selected": "Archive Selected",
        "open_folder": "Open Folder",
        "export_csv": "Export CSV",
        "language": "DE",
        "include_git": "Include .git in ZIP",
        "status_indexing": "Indexing repositories...",
        "status_ready": "Ready.",
        "col_name": "Name",
        "col_path": "Path",
        "col_size": "Size (MB)",
        "col_mtime": "Last Modified",
        "col_remote": "Remote",
        "menu_file": "File",
        "menu_quit": "Quit",
        "menu_help": "Help",
        "menu_about": "About",
        "about_title": "About",
        "about_body": (
            f"{APP_NAME} v{APP_VERSION}\n"
            f"Local repository catalog, search and archiving tool.\n\n"
            f"Author: {APP_AUTHOR}\n\n"
            f"This app stores metadata in 'repos.db' next to the executable."
        ),
        "confirm_zip": "Select destination ZIP file",
        "info": "Info",
        "error": "Error",
        "no_selection": "Please select a repository first.",
        "zip_done": "Archive created successfully.",
        "csv_saved": "CSV exported successfully.",
        "scan_done": "Scan completed.",
        "btn_github": "GitHub",
        "preview_title": "Preview",
        "preview_no_pillow": "Install Pillow (pip install pillow) to enable image preview.",
        "preview_not_found": "No suitable image found in assets.",
        "preview_from": "From",
        "preview_size": "Size",
    },
    "de": {
        "window_title": f"{APP_NAME} v{APP_VERSION}",
        "banner_title": APP_NAME,
        "author": f"{APP_AUTHOR}",
        "search": "Suche",
        "placeholder_search": "Nach Name oder Pfad filtern...",
        "scan_folder": "Ordner scannen",
        "archive_selected": "Auswahl archivieren",
        "open_folder": "Ordner öffnen",
        "export_csv": "CSV exportieren",
        "language": "EN",
        "include_git": ".git ins ZIP aufnehmen",
        "status_indexing": "Repos werden indiziert...",
        "status_ready": "Bereit.",
        "col_name": "Name",
        "col_path": "Pfad",
        "col_size": "Größe (MB)",
        "col_mtime": "Zuletzt geändert",
        "col_remote": "Remote",
        "menu_file": "Datei",
        "menu_quit": "Beenden",
        "menu_help": "Hilfe",
        "menu_about": "Info",
        "about_title": "Info",
        "about_body": (
            f"{APP_NAME} v{APP_VERSION}\n"
            f"Lokales Katalog-, Such- und Archivierungstool für Repositories.\n\n"
            f"Autor: {APP_AUTHOR}\n\n"
            f"Diese App speichert Metadaten in 'repos.db' neben der ausführbaren Datei."
        ),
        "confirm_zip": "Ziel-ZIP-Datei auswählen",
        "info": "Info",
        "error": "Fehler",
        "no_selection": "Bitte zuerst ein Repository auswählen.",
        "zip_done": "Archiv erfolgreich erstellt.",
        "csv_saved": "CSV erfolgreich exportiert.",
        "scan_done": "Scan abgeschlossen.",
        "btn_github": "GitHub",
        "preview_title": "Vorschau",
        "preview_no_pillow": "Installiere Pillow (pip install pillow), um die Bildvorschau zu aktivieren.",
        "preview_not_found": "Kein geeignetes Bild in assets gefunden.",
        "preview_from": "Aus",
        "preview_size": "Größe",
    },
}

SQL_SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    mtime INTEGER NOT NULL,
    remote_url TEXT
);
"""

class RepoDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self.conn.execute(SQL_SCHEMA)
        self.conn.commit()

    def upsert_repo(self, name: str, path: str, size_bytes: int, mtime: int, remote_url: Optional[str]):
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO repos(name, path, size_bytes, mtime, remote_url)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                name=excluded.name,
                size_bytes=excluded.size_bytes,
                mtime=excluded.mtime,
                remote_url=excluded.remote_url
            """,
            (name, path, size_bytes, mtime, remote_url)
        )
        self.conn.commit()

    def all_repos(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, name, path, size_bytes, mtime, remote_url FROM repos ORDER BY mtime DESC")
        return cur.fetchall()

    def search(self, query: str):
        q = f"%{query.lower()}%"
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, name, path, size_bytes, mtime, remote_url
            FROM repos
            WHERE lower(name) LIKE ? OR lower(path) LIKE ?
            ORDER BY mtime DESC
            """,
            (q, q)
        )
        return cur.fetchall()

def is_git_repo(path: Path) -> bool:
    return (path / ".git").is_dir()

def compute_dir_size_bytes(path: Path, exclude_git: bool = False) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        if exclude_git and ".git" in dirs:
            dirs.remove(".git")
        for f in files:
            fp = os.path.join(root, f)
            try:
                total += os.path.getsize(fp)
            except OSError:
                pass
    return total

def get_git_remote_url(repo_path: Path) -> Optional[str]:
    cfg_path = repo_path / ".git" / "config"
    if not cfg_path.exists():
        return None
    config = configparser.ConfigParser()
    try:
        config.read(cfg_path, encoding="utf-8")
        section = 'remote "origin"'
        if config.has_section(section) and config.has_option(section, "url"):
            return config.get(section, "url")
    except Exception:
        pass
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None

def format_size_mb(size_bytes: int) -> str:
    try:
        return f"{size_bytes / (1024*1024):.2f}"
    except Exception:
        return "0.00"

def open_in_explorer(path: Path):
    try:
        if platform.system() == "Windows":
            os.startfile(str(path))
        elif platform.system() == "Darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as e:
        messagebox.showerror("Error", str(e))

def zip_directory(source_dir: Path, dest_zip: Path, include_git: bool = False):
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for root, dirs, files in os.walk(source_dir):
            if not include_git and ".git" in dirs:
                dirs.remove(".git")
            for f in files:
                fp = Path(root) / f
                try:
                    arcname = fp.relative_to(source_dir)
                except Exception:
                    arcname = fp.name
                try:
                    zf.write(fp, arcname)
                except Exception:
                    pass

def list_candidate_images(repo_root: Path) -> List[Path]:
    out: List[Path] = []
    for d in IMAGE_DIR_CANDIDATES:
        p = repo_root / d
        if p.is_dir():
            for root, _, files in os.walk(p):
                for f in files:
                    if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                        out.append(Path(root) / f)
    return out

def img_size(path: Path) -> Optional[Tuple[int, int]]:
    if not PIL_AVAILABLE:
        return None
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None

def score_image(size_wh: Tuple[int, int]) -> float:
    w, h = size_wh
    if w <= 0 or h <= 0:
        return 1e9
    ar = float(w) / float(h)
    ar_penalty = abs(ar - TARGET_AR) * 1000.0
    size_penalty = abs(w - TARGET_W) + abs(h - TARGET_H)
    exact_bonus = -5000.0 if (w == TARGET_W and h == TARGET_H) else 0.0
    return ar_penalty + size_penalty + exact_bonus

def pick_best_image(paths: List[Path]) -> Optional[Path]:
    if not PIL_AVAILABLE:
        return None
    best_p = None
    best_s = 1e18
    for p in paths:
        sz = img_size(p)
        if not sz:
            continue
        s = score_image(sz)
        if s < best_s:
            best_s = s
            best_p = p
    return best_p

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.lang = "en"
        self.db = RepoDB(DB_PATH)
        self.include_git_var = tk.BooleanVar(value=False)
        self.geometry("2000x720")
        self.minsize(1900, 640)

        self._build_menu()
        self._build_header()
        self._build_body()
        self._build_statusbar()

        self.refresh_table()
        self._apply_i18n()


    def _build_menu(self):
        try:
            self.config(menu=None)
        except Exception:
            pass
        t = I18N[self.lang]
        self.title(t["window_title"])

        self.menu = tk.Menu(self)
        self.config(menu=self.menu)

        self.file_menu = tk.Menu(self.menu, tearoff=0)
        self.file_menu.add_command(label=t["menu_quit"], command=self.destroy)
        self.menu.add_cascade(label=t["menu_file"], menu=self.file_menu)

        self.help_menu = tk.Menu(self.menu, tearoff=0)
        self.help_menu.add_command(label=t["menu_about"], command=self.show_about)
        self.menu.add_cascade(label=t["menu_help"], menu=self.help_menu)

    def _build_header(self):
        frm = ttk.Frame(self, padding=(10, 10, 10, 0))
        frm.pack(fill="x")

        left = ttk.Frame(frm)
        left.pack(side="left", fill="x", expand=True)
        self.lbl_title = ttk.Label(left, text="", font=("Segoe UI", 16, "bold"))
        self.lbl_title.pack(anchor="w")
        self.lbl_author = ttk.Label(left, text="", font=("Segoe UI", 9))
        self.lbl_author.pack(anchor="w", pady=(2, 0))

        right = ttk.Frame(frm)
        right.pack(side="right")
        self.btn_github = ttk.Button(right, text="", command=lambda: webbrowser.open(GITHUB_URL))
        self.btn_github.pack(side="right", padx=(6, 0))
        self.btn_info = ttk.Button(right, text="", command=self.show_about)
        self.btn_info.pack(side="right", padx=(6, 0))
        self.btn_lang = ttk.Button(right, text="", command=self.toggle_language)
        self.btn_lang.pack(side="right", padx=(6, 0))

    def _build_body(self):
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        left.pack(side="left", fill="both", expand=True)

        search_row = ttk.Frame(left)
        search_row.pack(fill="x")
        self.lbl_search = ttk.Label(search_row, text="")
        self.lbl_search.pack(side="left")
        self.entry_search = ttk.Entry(search_row)
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(8, 8))
        self.entry_search.insert(0, "")
        self.entry_search.bind("<KeyRelease>", lambda e: self.on_search())
        self.entry_search.bind("<FocusIn>", self._clear_placeholder)

        self.chk_include_git = ttk.Checkbutton(search_row, text="", variable=self.include_git_var)
        self.chk_include_git.pack(side="right")

        table_frame = ttk.Frame(left)
        table_frame.pack(fill="both", expand=True, pady=(10, 10))
        columns = ("name", "path", "size", "mtime", "remote")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.tree.heading("name", text="Name")
        self.tree.heading("path", text="Path")
        self.tree.heading("size", text="Size (MB)")
        self.tree.heading("mtime", text="Last Modified")
        self.tree.heading("remote", text="Remote")
        self.tree.column("name", width=200, anchor="w")
        self.tree.column("path", width=460, anchor="w")
        self.tree.column("size", width=90, anchor="e")
        self.tree.column("mtime", width=160, anchor="center")
        self.tree.column("remote", width=260, anchor="w")
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)

        actions = ttk.Frame(left)
        actions.pack(fill="x")
        self.btn_scan = ttk.Button(actions, text="", command=self.scan_folder)
        self.btn_scan.pack(side="left")
        self.btn_archive = ttk.Button(actions, text="", command=self.archive_selected)
        self.btn_archive.pack(side="left", padx=(8, 0))
        self.btn_open = ttk.Button(actions, text="", command=self.open_selected)
        self.btn_open.pack(side="left", padx=(8, 0))
        self.btn_export = ttk.Button(actions, text="", command=self.export_csv)
        self.btn_export.pack(side="left", padx=(8, 0))

        right = ttk.Frame(body, width=420)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        self.lbl_preview_title = ttk.Label(right, text="", font=("Segoe UI", 11, "bold"))
        self.lbl_preview_title.pack(anchor="w", pady=(0, 6))

        self.preview_container = ttk.Frame(right, relief="groove", padding=6)
        self.preview_container.pack(fill="both", expand=True)

        self.preview_canvas = tk.Canvas(self.preview_container, highlightthickness=0)
        self.preview_canvas.pack(fill="both", expand=True)

        meta = ttk.Frame(right)
        meta.pack(fill="x", pady=(6, 0))
        self.lbl_preview_path = ttk.Label(meta, text="", wraplength=380, justify="left")
        self.lbl_preview_path.pack(anchor="w")
        self.lbl_preview_size = ttk.Label(meta, text="")
        self.lbl_preview_size.pack(anchor="w")

        self._preview_img_ref = None
        self._preview_src_path = None

        self.preview_canvas.bind("<Configure>", self._redraw_preview)

    def _build_statusbar(self):
        self.status = tk.StringVar(value="")
        bar = ttk.Frame(self, padding=(10, 0, 10, 10))
        bar.pack(fill="x")
        self.lbl_status = ttk.Label(bar, textvariable=self.status)
        self.lbl_status.pack(anchor="w")

    def _apply_i18n(self):
        t = I18N[self.lang]
        self.title(t["window_title"])
        self.lbl_title.configure(text=t["banner_title"])
        self.lbl_author.configure(text=t["author"])

        self.lbl_search.configure(text=t["search"])
        if self.entry_search.get() == "" or self.entry_search.get() in (
            I18N["en"]["placeholder_search"], I18N["de"]["placeholder_search"]
        ):
            self.entry_search.delete(0, tk.END)
            self.entry_search.insert(0, t["placeholder_search"])
        self.chk_include_git.configure(text=t["include_git"])

        self.btn_scan.configure(text=t["scan_folder"])
        self.btn_archive.configure(text=t["archive_selected"])
        self.btn_open.configure(text=t["open_folder"])
        self.btn_export.configure(text=t["export_csv"])
        self.btn_lang.configure(text=t["language"])
        self.btn_info.configure(text=t["menu_about"])
        self.btn_github.configure(text=t["btn_github"])

        self.tree.heading("name", text=t["col_name"])
        self.tree.heading("path", text=t["col_path"])
        self.tree.heading("size", text=t["col_size"])
        self.tree.heading("mtime", text=t["col_mtime"])
        self.tree.heading("remote", text=t["col_remote"])

        self.lbl_preview_title.configure(text=t["preview_title"])

        if not PIL_AVAILABLE:
            self._set_preview_message(t["preview_no_pillow"])
        else:
            self._set_preview_message(t["preview_not_found"])

        self.status.set(t["status_ready"])

    def toggle_language(self):
        self.lang = "en" if self.lang == "de" else "de"
        self._build_menu()
        self._apply_i18n()

    def show_about(self):
        t = I18N[self.lang]
        messagebox.showinfo(t["about_title"], t["about_body"])

    def _clear_placeholder(self, event):
        if self.entry_search.get() in (
            I18N["en"]["placeholder_search"], I18N["de"]["placeholder_search"]
        ):
            self.entry_search.delete(0, tk.END)

    def on_search(self):
        query = self.entry_search.get().strip()
        if query in (I18N["en"]["placeholder_search"], I18N["de"]["placeholder_search"]):
            query = ""
        rows = self.db.search(query) if query else self.db.all_repos()
        self._populate_table(rows)

    def refresh_table(self):
        rows = self.db.all_repos()
        self._populate_table(rows)

    def _populate_table(self, rows):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for _id, name, path, size_bytes, mtime, remote in rows:
            size_mb = format_size_mb(size_bytes)
            dt = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
            self.tree.insert("", "end", iid=str(_id), values=(name, path, size_mb, dt, remote or ""))

    def scan_folder(self):
        t = I18N[self.lang]
        folder = filedialog.askdirectory()
        if not folder:
            return
        self.status.set(t["status_indexing"])
        self.update_idletasks()

        base = Path(folder)
        candidates = []
        if is_git_repo(base):
            candidates.append(base)
        for root, dirs, _ in os.walk(base):
            for d in dirs:
                p = Path(root) / d
                if is_git_repo(p):
                    candidates.append(p)

        seen = set()
        uniq = []
        for c in candidates:
            s = str(c)
            if s not in seen:
                uniq.append(c)
                seen.add(s)

        for repo_path in uniq:
            try:
                name = repo_path.name
                size = compute_dir_size_bytes(repo_path, exclude_git=True)
                mtime = int(repo_path.stat().st_mtime)
                remote = get_git_remote_url(repo_path)
                self.db.upsert_repo(name, str(repo_path), size, mtime, remote)
            except Exception as e:
                print(f"Error scanning {repo_path}: {e}", file=sys.stderr)

        self.refresh_table()
        self.status.set(t["scan_done"])

    def _selected_repo_path(self) -> Optional[Path]:
        sel = self.tree.selection()
        if not sel:
            return None
        item = self.tree.item(sel[0])
        vals = item.get("values", [])
        if not vals or len(vals) < 2:
            return None
        return Path(vals[1])

    def open_selected(self):
        t = I18N[self.lang]
        p = self._selected_repo_path()
        if not p:
            messagebox.showinfo(t["info"], t["no_selection"])
            return
        open_in_explorer(p)

    def archive_selected(self):
        t = I18N[self.lang]
        p = self._selected_repo_path()
        if not p:
            messagebox.showinfo(t["info"], t["no_selection"])
            return
        initial = f"{p.name}.zip"
        dest = filedialog.asksaveasfilename(
            title=t["confirm_zip"],
            defaultextension=".zip",
            initialfile=initial,
            filetypes=[("ZIP", ".zip")]
        )
        if not dest:
            return
        try:
            zip_directory(p, Path(dest), include_git=self.include_git_var.get())
            messagebox.showinfo(t["info"], t["zip_done"])
        except Exception as e:
            messagebox.showerror(t["error"], str(e))

    def export_csv(self):
        t = I18N[self.lang]
        dest = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV", ".csv")],
            initialfile="repositories.csv"
        )
        if not dest:
            return
        try:
            with open(dest, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    I18N[self.lang]["col_name"],
                    I18N[self.lang]["col_path"],
                    I18N[self.lang]["col_size"],
                    I18N[self.lang]["col_mtime"],
                    I18N[self.lang]["col_remote"]
                ])
                for iid in self.tree.get_children():
                    vals = self.tree.item(iid, "values")
                    writer.writerow(vals)
            messagebox.showinfo(t["info"], t["csv_saved"])
        except Exception as e:
            messagebox.showerror(t["error"], str(e))

    def on_row_select(self, event):
        repo = self._selected_repo_path()
        t = I18N[self.lang]
        if not repo:
            self._set_preview_message(t["preview_not_found"])
            return
        if not PIL_AVAILABLE:
            self._set_preview_message(t["preview_no_pillow"])
            return

        imgs = list_candidate_images(repo)
        if not imgs:
            self._set_preview_message(t["preview_not_found"])
            return

        best = pick_best_image(imgs)
        if not best:
            self._set_preview_message(t["preview_not_found"])
            return

        self._preview_src_path = best
        self._render_preview(best)

    def _render_preview(self, img_path: Path):

        t = I18N[self.lang]
        if not PIL_AVAILABLE or img_path is None or not img_path.exists():
            self._set_preview_message(t["preview_not_found"])
            return
        try:
            with Image.open(img_path) as im:
                ow, oh = im.size
                cw = max(self.preview_canvas.winfo_width(), 10)
                ch = max(self.preview_canvas.winfo_height(), 10)

                im_ratio = ow / oh if oh != 0 else 1.0
                canvas_ratio = cw / ch if ch != 0 else 1.0

                if im_ratio > canvas_ratio:
                    new_w = cw
                    new_h = int(cw / im_ratio)
                else:
                    new_h = ch
                    new_w = int(ch * im_ratio)
                if new_w < 1: new_w = 1
                if new_h < 1: new_h = 1

                im = im.convert("RGBA")
                im = im.resize((new_w, new_h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(im)

                self.preview_canvas.delete("all")
                x = (cw - new_w) // 2
                y = (ch - new_h) // 2
                self.preview_canvas.create_image(x, y, anchor="nw", image=photo)
                self._preview_img_ref = photo
                self.lbl_preview_path.configure(text=f"{t['preview_from']}: {img_path}")
                self.lbl_preview_size.configure(text=f"{t['preview_size']}: {ow}×{oh}")
        except Exception as e:
            self._set_preview_message(str(e))

    def _redraw_preview(self, event):
        if self._preview_src_path:
            self._render_preview(self._preview_src_path)

    def _set_preview_message(self, msg: str):
        self.preview_canvas.delete("all")
        cw = max(self.preview_canvas.winfo_width(), 10)
        ch = max(self.preview_canvas.winfo_height(), 10)
        self.preview_canvas.create_text(
            cw // 2, ch // 2, text=msg, anchor="center", width=cw - 20, justify="center"
        )
        self._preview_img_ref = None
        self.lbl_preview_path.configure(text="")
        self.lbl_preview_size.configure(text="")

def main():
    logging.basicConfig(filename=LOG_PATH, level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        app = App()
        style = ttk.Style(app)
        style.configure("TButton", padding=(10, 6))
        style.configure("TLabel", padding=(2, 2))
        style.configure("Treeview", rowheight=22)
        app.mainloop()
    except tk.TclError as e:
        tb = traceback.format_exc()
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(tb + "\n")
        except Exception:
            pass
        print("[FATAL] Tkinter/Tcl error:", e, "\nSee:", LOG_PATH, file=sys.stderr)
    except Exception as e:
        tb = traceback.format_exc()
        try:
            with open(LOG_PATH, "a", encoding="utf-8") as f:
                f.write(tb + "\n")
        except Exception:
            pass
        try:
            messagebox.showerror("Startup Error", str(e))
        except Exception:
            pass
        print("[FATAL] Unexpected error:", e, "\nSee:", LOG_PATH, file=sys.stderr)

if __name__ == "__main__":
    main()