#!/usr/bin/env python3
"""
NEO YT DOWNLOADER
-----------------
A desktop YouTube video/audio downloader built with Tkinter + yt-dlp,
styled in a bold neo-brutalist aesthetic (thick black borders, hard
drop shadows, flat saturated colors, no gradients, no rounded corners).

INSTALL DEPENDENCIES:
    pip install yt-dlp pillow requests

You also need FFmpeg installed and available on PATH:
    - required to merge separate video+audio streams into one file
    - required to extract audio-only downloads as MP3
    Windows: https://www.gyan.dev/ffmpeg/builds/  (add the /bin folder to PATH)
    Mac:     brew install ffmpeg
    Linux:   sudo apt install ffmpeg

RUN:
    python youtube_downloader.py

FEATURES:
    1. Live thumbnail + title/channel/duration preview before you download
    2. Three download modes: Video+Audio, Video Only, Audio Only (MP3)
    3. Quality selector auto-populated with the resolutions actually
       available for that specific video
    4. Full playlist download support (toggle on/off)
    5. Real-time progress bar with live speed + ETA
    6. Cancel-mid-download button
    7. Persistent download history with one-click "open folder"
"""

import os
import json
import queue
import threading
import subprocess
import platform
from datetime import datetime
from io import BytesIO

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    import requests
except ImportError:
    requests = None

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


# ----------------------------------------------------------------------
# ---------------------------  THEME / COLORS  --------------------------
# ----------------------------------------------------------------------
BG      = "#F5F0E6"   # warm off-white background
SURFACE = "#FFFFFF"   # card surface
BLACK   = "#111111"
YELLOW  = "#FFD23F"
PINK    = "#FF6B9D"
PURPLE  = "#9B7BFF"
GREEN   = "#4ADE80"
RED     = "#FF5C5C"
BLUE    = "#5CC8FF"

FONT_TITLE  = ("Arial Black", 20, "bold")
FONT_HEAD   = ("Arial Black", 13, "bold")
FONT_BODY   = ("Arial", 11)
FONT_BODY_B = ("Arial", 11, "bold")
FONT_MONO   = ("Consolas", 10)

SHADOW_OFFSET = 5
BORDER_WIDTH = 3

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".ytdl_neo_history.json")


# ----------------------------------------------------------------------
# ---------------------------  HELPER WIDGETS  --------------------------
# ----------------------------------------------------------------------
class NeoButton(tk.Canvas):
    """Hard-shadow, thick-border neo-brutalist button."""

    def __init__(self, parent, text, command=None, bg=YELLOW, fg=BLACK,
                 width=160, height=44, font=FONT_BODY_B, **kw):
        super().__init__(parent, width=width + SHADOW_OFFSET,
                         height=height + SHADOW_OFFSET,
                         bg=parent.cget("bg"), highlightthickness=0, **kw)
        self.command = command
        self.bg_color = bg
        self.fg_color = fg
        self.w = width
        self.h = height
        self.pressed = False
        self.disabled = False

        self.create_rectangle(SHADOW_OFFSET, SHADOW_OFFSET,
                              width + SHADOW_OFFSET, height + SHADOW_OFFSET,
                              fill=BLACK, outline="")
        self.rect = self.create_rectangle(0, 0, width, height,
                                          fill=bg, outline=BLACK, width=BORDER_WIDTH)
        self.label = self.create_text(width / 2, height / 2, text=text,
                                      font=font, fill=fg)

        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", lambda e: self.config(cursor="hand2" if not self.disabled else "arrow"))

    def _on_press(self, _e):
        if self.disabled:
            return
        self.move(self.rect, SHADOW_OFFSET, SHADOW_OFFSET)
        self.move(self.label, SHADOW_OFFSET, SHADOW_OFFSET)
        self.pressed = True

    def _on_release(self, e):
        if self.disabled or not self.pressed:
            return
        self.move(self.rect, -SHADOW_OFFSET, -SHADOW_OFFSET)
        self.move(self.label, -SHADOW_OFFSET, -SHADOW_OFFSET)
        self.pressed = False
        if 0 <= e.x <= self.w and 0 <= e.y <= self.h and self.command:
            self.command()

    def set_enabled(self, enabled):
        self.disabled = not enabled
        self.itemconfig(self.rect, fill=self.bg_color if enabled else "#CCCCCC")
        self.itemconfig(self.label, fill=self.fg_color if enabled else "#888888")


class NeoProgressBar(tk.Frame):
    """Thick-bordered, flat-fill progress bar."""

    def __init__(self, parent, width=690, height=28, fill=GREEN, **kw):
        super().__init__(parent, width=width, height=height, bg=SURFACE,
                         highlightbackground=BLACK, highlightthickness=BORDER_WIDTH, **kw)
        self.pack_propagate(False)
        self.width = width - 2 * BORDER_WIDTH
        self.height = height - 2 * BORDER_WIDTH
        self.canvas = tk.Canvas(self, width=self.width, height=self.height,
                                bg=SURFACE, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.bar = self.canvas.create_rectangle(0, 0, 0, self.height, fill=fill, outline="")
        self.pct_text = self.canvas.create_text(self.width / 2, self.height / 2,
                                                text="0%", font=("Arial", 9, "bold"), fill=BLACK)

    def set_progress(self, pct, color=None):
        pct = max(0, min(100, pct))
        w = self.width * pct / 100
        self.canvas.coords(self.bar, 0, 0, w, self.height)
        if color:
            self.canvas.itemconfig(self.bar, fill=color)
        self.canvas.itemconfig(self.pct_text, text=f"{pct:.0f}%")
        self.canvas.tag_raise(self.pct_text)


def neo_label(parent, text, font=FONT_BODY, fg=BLACK, bg=None, **kw):
    return tk.Label(parent, text=text, font=font, fg=fg,
                    bg=bg if bg else parent.cget("bg"), **kw)


def neo_entry(parent, textvariable=None, width=40, **kw):
    return tk.Entry(parent, textvariable=textvariable, width=width, font=FONT_BODY,
                    bg=SURFACE, fg=BLACK, insertbackground=BLACK,
                    highlightbackground=BLACK, highlightthickness=BORDER_WIDTH,
                    relief="flat", **kw)


# ----------------------------------------------------------------------
# ------------------------------  MAIN APP  ------------------------------
# ----------------------------------------------------------------------
class YTDownloaderApp:
    def __init__(self, root):
        self.root = root
        root.title("NEO YT DOWNLOADER")
        root.geometry("760x780")
        root.configure(bg=BG)
        root.resizable(False, False)

        self.msg_queue = queue.Queue()
        self.download_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.url_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="video_audio")
        self.quality_var = tk.StringVar(value="Best available")
        self.playlist_var = tk.BooleanVar(value=False)
        self.cancel_requested = False
        self.info = None
        self.thumb_img = None
        self.history = self._load_history()

        self._setup_ttk_style()
        self._build_ui()
        self.root.after(150, self._poll_queue)

    # ---------------- UI BUILD ----------------
    def _setup_ttk_style(self):
        # Classic tk.Radiobutton / tk.Checkbutton / tk.OptionMenu render
        # unreliably on macOS's native "Aqua" theme once you customize
        # their colors (label text can silently vanish). The "clam"
        # theme is a plain, cross-platform renderer that actually
        # respects custom colors/fonts, so we use it for those controls.
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Neo.TRadiobutton", background=SURFACE, foreground=BLACK,
                        font=FONT_BODY_B)
        style.map("Neo.TRadiobutton", background=[("active", SURFACE)])
        style.configure("Neo.TCheckbutton", background=SURFACE, foreground=BLACK,
                        font=FONT_BODY_B)
        style.map("Neo.TCheckbutton", background=[("active", SURFACE)])
        style.configure("Neo.TCombobox", fieldbackground=SURFACE, background=SURFACE,
                        foreground=BLACK, font=FONT_BODY)

    def _card(self, parent):
        return tk.Frame(parent, bg=SURFACE, highlightbackground=BLACK,
                        highlightthickness=BORDER_WIDTH)

    def _build_ui(self):
        header = tk.Frame(self.root, bg=BLACK, height=70)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="NEO YT DOWNLOADER", font=FONT_TITLE,
                 bg=BLACK, fg=YELLOW).pack(side="left", padx=20, pady=10)
        tk.Label(header, text="paste. fetch. smash download.", font=("Arial", 10, "italic"),
                 bg=BLACK, fg="#DDDDDD").pack(side="left", pady=10)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=15)

        # URL card
        url_card = self._card(body)
        url_card.pack(fill="x", pady=(0, 12))
        neo_label(url_card, "VIDEO / PLAYLIST URL", font=FONT_HEAD).pack(anchor="w", padx=14, pady=(12, 4))
        row = tk.Frame(url_card, bg=SURFACE)
        row.pack(fill="x", padx=14, pady=(0, 12))
        neo_entry(row, textvariable=self.url_var, width=42).pack(side="left", fill="x", expand=True, ipady=6)
        NeoButton(row, "PASTE", command=self._paste_clipboard, bg=BLUE,
                  width=90, height=36).pack(side="left", padx=(8, 0))
        NeoButton(row, "FETCH INFO", command=self._fetch_info_thread, bg=PURPLE, fg="white",
                  width=140, height=36).pack(side="left", padx=(8, 0))

        # Info card
        self.info_card = self._card(body)
        self.info_card.pack(fill="x", pady=(0, 12))
        info_inner = tk.Frame(self.info_card, bg=SURFACE)
        info_inner.pack(fill="x", padx=14, pady=12)
        self.thumb_label = tk.Label(info_inner, bg="#DDDDDD", width=20, height=6)
        self.thumb_label.pack(side="left")
        text_col = tk.Frame(info_inner, bg=SURFACE)
        text_col.pack(side="left", fill="x", expand=True, padx=(14, 0))
        self.title_label = neo_label(text_col, "No video loaded yet — paste a link and hit FETCH INFO",
                                     font=FONT_BODY_B)
        self.title_label.pack(anchor="w")
        self.meta_label = neo_label(text_col, "", fg="#555555")
        self.meta_label.pack(anchor="w", pady=(4, 0))

        # Options card
        opt_card = self._card(body)
        opt_card.pack(fill="x", pady=(0, 12))
        neo_label(opt_card, "DOWNLOAD OPTIONS", font=FONT_HEAD).pack(anchor="w", padx=14, pady=(12, 8))

        mode_row = tk.Frame(opt_card, bg=SURFACE)
        mode_row.pack(fill="x", padx=14)
        for label, val in [("Video + Audio", "video_audio"),
                           ("Video Only", "video_only"),
                           ("Audio Only (MP3)", "audio_only")]:
            ttk.Radiobutton(mode_row, text=label, variable=self.mode_var, value=val,
                            style="Neo.TRadiobutton").pack(side="left", padx=(0, 16), pady=8)

        qrow = tk.Frame(opt_card, bg=SURFACE)
        qrow.pack(fill="x", padx=14, pady=(0, 6))
        neo_label(qrow, "Quality:", font=FONT_BODY_B).pack(side="left")
        self.quality_menu = ttk.Combobox(qrow, textvariable=self.quality_var,
                                         values=["Best available"], state="readonly",
                                         style="Neo.TCombobox", width=16)
        self.quality_menu.pack(side="left", padx=(10, 20))
        ttk.Checkbutton(qrow, text="Download entire playlist", variable=self.playlist_var,
                        style="Neo.TCheckbutton").pack(side="left")

        drow = tk.Frame(opt_card, bg=SURFACE)
        drow.pack(fill="x", padx=14, pady=(4, 12))
        neo_label(drow, "Save to:", font=FONT_BODY_B).pack(side="left")
        self.dir_label = neo_label(drow, self._short_path(self.download_dir.get()))
        self.dir_label.pack(side="left", padx=(10, 10))
        NeoButton(drow, "CHANGE", command=self._choose_dir, bg=YELLOW,
                  width=90, height=32, font=("Arial", 9, "bold")).pack(side="left")

        # Action row
        action_row = tk.Frame(body, bg=BG)
        action_row.pack(fill="x", pady=(0, 12))
        self.download_btn = NeoButton(action_row, "DOWNLOAD NOW", command=self._start_download,
                                      bg=GREEN, width=220, height=52, font=("Arial Black", 13))
        self.download_btn.pack(side="left")
        self.cancel_btn = NeoButton(action_row, "CANCEL", command=self._cancel_download,
                                    bg=RED, fg="white", width=140, height=52)
        self.cancel_btn.pack(side="left", padx=(10, 0))
        self.cancel_btn.set_enabled(False)

        # Progress card
        prog_card = self._card(body)
        prog_card.pack(fill="x", pady=(0, 12))
        pinner = tk.Frame(prog_card, bg=SURFACE)
        pinner.pack(fill="x", padx=14, pady=12)
        self.progress_bar = NeoProgressBar(pinner, width=690)
        self.progress_bar.pack(fill="x")
        self.status_label = neo_label(pinner, "Idle — waiting for a link.", fg="#555555")
        self.status_label.pack(anchor="w", pady=(8, 0))

        # History card
        hist_card = self._card(body)
        hist_card.pack(fill="both", expand=True)
        hrow = tk.Frame(hist_card, bg=SURFACE)
        hrow.pack(fill="x", padx=14, pady=(12, 4))
        neo_label(hrow, "DOWNLOAD HISTORY", font=FONT_HEAD).pack(side="left")
        NeoButton(hrow, "OPEN FOLDER", command=self._open_download_folder, bg=BLUE,
                  width=130, height=30, font=("Arial", 9, "bold")).pack(side="right")
        list_frame = tk.Frame(hist_card, bg=SURFACE)
        list_frame.pack(fill="both", expand=True, padx=14, pady=(4, 12))
        self.history_list = tk.Listbox(list_frame, font=FONT_MONO, bg="#FAFAFA",
                                       highlightbackground=BLACK, highlightthickness=2,
                                       relief="flat", height=6)
        self.history_list.pack(fill="both", expand=True)
        self._refresh_history_ui()

    # ---------------- SMALL HELPERS ----------------
    def _short_path(self, path):
        return path if len(path) < 46 else "..." + path[-43:]

    def _paste_clipboard(self):
        try:
            self.url_var.set(self.root.clipboard_get().strip())
        except tk.TclError:
            pass

    def _choose_dir(self):
        d = filedialog.askdirectory(initialdir=self.download_dir.get())
        if d:
            self.download_dir.set(d)
            self.dir_label.config(text=self._short_path(d))

    def _open_download_folder(self):
        path = self.download_dir.get()
        try:
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            messagebox.showerror("Error", f"Couldn't open folder:\n{e}")

    # ---------------- FETCH INFO ----------------
    def _looks_like_youtube_url(self, url):
        url = url.strip()
        if len(url) > 300 or "\n" in url:
            return False
        return url.startswith(("http://", "https://")) and (
                "youtube.com" in url or "youtu.be" in url)

    def _fetch_info_thread(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a YouTube link first.")
            return
        if not self._looks_like_youtube_url(url):
            messagebox.showwarning(
                "That doesn't look right",
                "The URL box doesn't contain a valid YouTube link.\n\n"
                "Tip: click the box, press Cmd+A then Delete to clear it "
                "fully before pasting a new link — pasting normally "
                "inserts at the cursor instead of replacing.")
            return
        if yt_dlp is None:
            messagebox.showerror("Missing dependency", "Install it with: pip install yt-dlp")
            return
        self.status_label.config(text="Fetching video info...")
        threading.Thread(target=self._fetch_info, args=(url,), daemon=True).start()

    def _fetch_info(self, url):
        try:
            opts = {"quiet": True, "no_warnings": True, "skip_download": True}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            self.info = info
            if "entries" in info:
                entries = list(info.get("entries") or [])
                self.msg_queue.put(("playlist_detected", len(entries)))
                info_display = entries[0] if entries else info
            else:
                info_display = info
            self.msg_queue.put(("info_ready", info_display))
        except Exception as e:
            self.msg_queue.put(("error", str(e)))

    def _on_info_ready(self, info):
        title = info.get("title", "Unknown title")
        duration = info.get("duration") or 0
        mins, secs = divmod(int(duration), 60)
        uploader = info.get("uploader", "Unknown channel")
        self.title_label.config(text=title[:70] + ("..." if len(title) > 70 else ""))
        self.meta_label.config(text=f"{uploader}  •  {mins}:{secs:02d}")
        self.status_label.config(text="Info loaded. Choose options and hit download.")

        formats = info.get("formats", [])
        heights = sorted({f.get("height") for f in formats if f.get("height")}, reverse=True)
        options = ["Best available"] + [f"{h}p" for h in heights]
        self.quality_menu["values"] = options
        self.quality_var.set("Best available")

        thumb_url = info.get("thumbnail")
        if thumb_url and requests and Image:
            threading.Thread(target=self._load_thumbnail, args=(thumb_url,), daemon=True).start()

    def _load_thumbnail(self, url):
        try:
            r = requests.get(url, timeout=8)
            img = Image.open(BytesIO(r.content)).resize((140, 90))
            photo = ImageTk.PhotoImage(img)
            self.msg_queue.put(("thumb_ready", photo))
        except Exception:
            pass

    # ---------------- DOWNLOAD ----------------
    def _build_format_string(self):
        mode = self.mode_var.get()
        quality = self.quality_var.get()
        height_filter = f"[height<={quality.replace('p', '')}]" if quality != "Best available" else ""

        if mode == "audio_only":
            return "bestaudio/best"
        elif mode == "video_only":
            return f"bestvideo{height_filter}/best{height_filter}"
        else:
            return f"bestvideo{height_filter}+bestaudio/best{height_filter}/best"

    def _start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Missing URL", "Paste a YouTube link first.")
            return
        if not self._looks_like_youtube_url(url):
            messagebox.showwarning("That doesn't look right",
                                   "The URL box doesn't contain a valid YouTube link.")
            return
        if yt_dlp is None:
            messagebox.showerror("Missing dependency", "Install it with: pip install yt-dlp")
            return

        self.cancel_requested = False
        self.download_btn.set_enabled(False)
        self.cancel_btn.set_enabled(True)
        self.progress_bar.set_progress(0, GREEN)
        self.status_label.config(text="Starting download...")
        threading.Thread(target=self._download_worker, args=(url,), daemon=True).start()

    def _cancel_download(self):
        self.cancel_requested = True
        self.status_label.config(text="Cancelling after current file...")

    def _progress_hook(self, d):
        if self.cancel_requested:
            raise yt_dlp.utils.DownloadError("Cancelled by user")
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            pct = (downloaded / total * 100) if total else 0
            speed = d.get("speed")
            eta = d.get("eta")
            speed_str = f"{speed / 1024 / 1024:.2f} MB/s" if speed else "—"
            eta_str = f"{eta}s" if eta is not None else "—"
            self.msg_queue.put(("progress", (pct, speed_str, eta_str)))
        elif d["status"] == "finished":
            self.msg_queue.put(("progress", (100, "—", "0s")))
            self.msg_queue.put(("status", "Processing / merging..."))

    def _download_worker(self, url):
        outdir = self.download_dir.get()
        os.makedirs(outdir, exist_ok=True)
        mode = self.mode_var.get()

        ydl_opts = {
            "format": self._build_format_string(),
            "outtmpl": os.path.join(outdir, "%(title).100s.%(ext)s"),
            "noplaylist": not self.playlist_var.get(),
            "progress_hooks": [self._progress_hook],
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        if mode == "audio_only":
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                result = ydl.extract_info(url, download=True)
            title = result.get("title", "video")
            self.msg_queue.put(("done", title))
            self._add_history(title, outdir)
        except Exception as e:
            if "Cancelled" in str(e):
                self.msg_queue.put(("cancelled", None))
            else:
                self.msg_queue.put(("error", str(e)))

    # ---------------- HISTORY ----------------
    def _load_history(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_history(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history[-50:], f, indent=2)
        except Exception:
            pass

    def _add_history(self, title, path):
        self.history.append({"title": title, "path": path,
                             "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
        self._save_history()
        self.msg_queue.put(("refresh_history", None))

    def _refresh_history_ui(self):
        self.history_list.delete(0, "end")
        for e in reversed(self.history[-50:]):
            self.history_list.insert("end", f"[{e['date']}]  {e['title'][:60]}")

    # ---------------- QUEUE POLL (thread-safe UI updates) ----------------
    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "info_ready":
                    self._on_info_ready(payload)
                elif kind == "playlist_detected":
                    self.meta_label.config(text=f"Playlist detected — {payload} videos")
                elif kind == "thumb_ready":
                    self.thumb_img = payload
                    self.thumb_label.config(image=self.thumb_img, width=140, height=90)
                elif kind == "progress":
                    pct, speed, eta = payload
                    self.progress_bar.set_progress(pct)
                    self.status_label.config(text=f"Downloading... {speed}  |  ETA {eta}")
                elif kind == "status":
                    self.status_label.config(text=payload)
                elif kind == "done":
                    self.progress_bar.set_progress(100, GREEN)
                    self.status_label.config(text=f"Done: {payload}")
                    self.download_btn.set_enabled(True)
                    self.cancel_btn.set_enabled(False)
                elif kind == "cancelled":
                    self.status_label.config(text="Cancelled.")
                    self.progress_bar.set_progress(0, RED)
                    self.download_btn.set_enabled(True)
                    self.cancel_btn.set_enabled(False)
                elif kind == "error":
                    self.status_label.config(text=f"Error: {payload}")
                    self.download_btn.set_enabled(True)
                    self.cancel_btn.set_enabled(False)
                    messagebox.showerror("Download error", payload)
                elif kind == "refresh_history":
                    self._refresh_history_ui()
        except queue.Empty:
            pass
        self.root.after(150, self._poll_queue)


def main():
    if yt_dlp is None:
        print("yt-dlp not found. Install with: pip install yt-dlp")
    root = tk.Tk()
    YTDownloaderApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()