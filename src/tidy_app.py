"""Tidy window (look "A"): status, History & undo, Connect/Disconnect.

Windows: lives in the tray. Closing or minimizing the window hides it to the tray; the tray icon opens it
again, and its menu has Open, History & undo and Quit. Starting Tidy.exe while it already runs shows the open one.
Mac: a normal Mac app. Closing the window keeps Tidy running; click its Dock icon to open it again; Cmd+Q quits.

Command line:  Tidy.exe --connect  /  --disconnect   (used by the installer)
               Tidy.exe --confirm <request.json>     (the Tidy-style Yes/No box tidy-server shows before deleting;
                                                      exit code 10 = yes, 11 = no)
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import threading
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
MAC = sys.platform == "darwin"
HERE = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
ASSETS = Path(getattr(sys, "_MEIPASS", "")) / "assets" if FROZEN else HERE.parent / "assets"
SERVER_EXE = HERE / ("tidy-server" if MAC else "tidy-server.exe")
SERVER_PY = HERE / "tidy_server.py"
NAME = "tidy"
if os.environ.get("LOCALAPPDATA"):
    DATA = Path(os.environ["LOCALAPPDATA"]) / "Tidy"
elif MAC:
    DATA = Path.home() / "Library" / "Application Support" / "Tidy"
else:
    DATA = Path.home() / "AppData" / "Local" / "Tidy"
SHOW_PORT = 47431   # a second Tidy.exe asks the running one to show itself here
REPO = "davidguillermoborges-ui/tidy"
RELEASES = f"https://github.com/{REPO}/releases/latest"
CLAUDE_DOWNLOAD = "https://claude.ai/download"

GREEN, GREEN_DARK = "#16A37C", "#0F6B51"
INK, MUTED, FAINT, LINE, BG = "#1B2422", "#55615E", "#6B7774", "#DDE3E1", "#FFFFFF"
PILL_ON, PILL_OFF = "#E6F6F0", "#F1F3F2"
FONT = "Helvetica Neue" if MAC else "Segoe UI"


def F(size, *style):
    """Mac draws points smaller than Windows, so the same look needs bigger numbers there."""
    return (FONT, round(size * 1.3) if MAC else size) + style


RESTART = ("Quit Claude (Claude menu > Quit, or Cmd+Q) and open it again" if MAC
           else "Quit Claude from its tray icon and open it again")


# ---------------------------------------------------------------- Claude's settings
def main_config():
    """The settings file Claude actually reads (%APPDATA%\\Claude; Mac: ~/Library/Application Support/Claude).
    This is what 'Connected' means."""
    if MAC:
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"


def store_configs():
    """The Microsoft Store copy, if there is one. Kept in step, but never counted as connected."""
    local = os.environ.get("LOCALAPPDATA")
    if MAC or not local:
        return []
    return [Path(d) / "claude_desktop_config.json"
            for d in glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude"))]


def read_cfg(p):
    if p.exists():
        txt = p.read_text(encoding="utf-8-sig").strip()
        return json.loads(txt) if txt else {}
    return {}


def write_cfg(p, cfg):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, p.with_suffix(".json.before-tidy"))
    tmp = p.with_suffix(".json.tidy-new")
    tmp.write_text(json.dumps(cfg, indent=2), encoding="utf-8")   # UTF-8 without BOM
    os.replace(tmp, p)


def server_entry():
    """What Claude runs for Tidy (the same entry HMNS Dev writes)."""
    if FROZEN:
        return {"command": str(SERVER_EXE), "args": []}
    return {"command": sys.executable, "args": [str(SERVER_PY)]}


def is_connected():
    try:
        return read_cfg(main_config()).get("mcpServers", {}).get(NAME) == server_entry()
    except Exception:
        return False


def app_bundle():
    """Mac: the Tidy.app folder this copy runs from (None when not built as an app)."""
    if MAC and FROZEN:
        for p in HERE.parents:
            if p.suffix == ".app":
                return p
    return None


def location_problem():
    """Mac: Tidy must run from Applications, not from the DMG or Downloads, or Claude loses it later."""
    b = app_bundle()
    if b is None:
        return None
    s = str(b)
    if "/AppTranslocation/" in s or s.startswith("/Volumes/"):
        return "Drag Tidy into your Applications folder first, then open it from there."
    return None


def unquarantine():
    """Mac: an unsigned download is marked 'quarantined'. Once the user opened Tidy, clear the mark on the whole
    app so macOS doesn't block tidy-server when Claude starts it."""
    b = app_bundle()
    if b:
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(b)], capture_output=True)


def connect():
    problem = location_problem()
    if problem:
        raise RuntimeError(problem)
    if FROZEN and not SERVER_EXE.exists():
        raise RuntimeError(f"{SERVER_EXE.name} is missing next to Tidy. Reinstall Tidy.")
    unquarantine()
    for p in [main_config()] + [s for s in store_configs() if s.exists()]:
        cfg = read_cfg(p)
        cfg.setdefault("mcpServers", {})[NAME] = server_entry()
        write_cfg(p, cfg)


def disconnect():
    for p in [main_config()] + store_configs():
        cfg = read_cfg(p)
        if NAME in cfg.get("mcpServers", {}):
            del cfg["mcpServers"][NAME]
            write_cfg(p, cfg)


def claude_installed():
    """Best guess whether Claude Desktop is on this computer (normal installer or Microsoft Store)."""
    if MAC:
        return any(p.exists() for p in (Path("/Applications/Claude.app"), Path.home() / "Applications" / "Claude.app",
                                        main_config().parent))
    local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return ((local / "AnthropicClaude").exists() or bool(glob.glob(str(local / "Packages" / "Claude_*")))
            or main_config().parent.exists())


def newer(a, b):
    """True if version a is newer than version b ('1.10.0' > '1.9.2')."""
    def parts(v):
        try:
            return tuple(int(x) for x in v.strip().lstrip("v").split("."))
        except ValueError:
            return ()
    return parts(a) > parts(b) != ()


def latest_release():
    """Newest release on GitHub: {"version": "1.4.0", "assets": {file name: download url}}, or None
    (offline, no releases yet...)."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "Tidy", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        v = data.get("tag_name", "").lstrip("v")
        return {"version": v, "assets": {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}} if v else None
    except Exception:
        return None


def update_file_name(v):
    return f"Tidy-{v}.dmg" if MAC else f"TidySetup-{v}.exe"


def download(url, dest, progress=None):
    """Download url to dest; progress(fraction) while it runs."""
    req = urllib.request.Request(url, headers={"User-Agent": "Tidy"})
    with urllib.request.urlopen(req, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        tmp = Path(str(dest) + ".part")
        got = 0
        with open(tmp, "wb") as f:
            while True:
                chunk = r.read(1 << 16)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if progress and total:
                    progress(got / total)
    if total and got != total:
        raise RuntimeError("the download was cut off")
    os.replace(tmp, dest)
    return dest


# ---------------------------------------------------------------- settings + notes files
SETTINGS_FILE = DATA / "settings.json"
NOTES_FILE = DATA / "tidy_notes.md"   # written by tidy-server's save_note; same header there
NOTES_HEAD = ("# My Tidy notes\n\n"
              "What Claude has learned about how you organize your files. Claude reads these before every plan.\n"
              "One note per line starting with \"- \". You can edit or delete lines here.\n\n")


def load_settings():
    s = {"auto_update_check": True}
    try:
        s.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return s


def save_settings(s):
    DATA.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(s, indent=1), encoding="utf-8")


def notes_count():
    try:
        return sum(1 for ln in NOTES_FILE.read_text(encoding="utf-8-sig").splitlines()
                   if ln.startswith("- ") and ln[2:].strip())
    except OSError:
        return 0


def open_notes():
    DATA.mkdir(parents=True, exist_ok=True)
    if not NOTES_FILE.exists():
        NOTES_FILE.write_text(NOTES_HEAD, encoding="utf-8")
    subprocess.Popen(["open", "-t", str(NOTES_FILE)] if MAC else ["notepad.exe", str(NOTES_FILE)])


def version():
    base = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else HERE.parent
    try:
        return json.loads((base / "tidy.json").read_text(encoding="utf-8"))["version"]
    except Exception:
        return "dev"


def open_history():
    p = DATA / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["open" if MAC else "explorer", str(p)])


# ---------------------------------------------------------------- one Tidy at a time
def ask_running_tidy_to_show():
    try:
        with socket.create_connection(("127.0.0.1", SHOW_PORT), timeout=1) as s:
            s.sendall(b"show")
        return True
    except OSError:
        return False


def listen_for_show(callback):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", SHOW_PORT))
    except OSError:
        return
    srv.listen(2)

    def loop():
        while True:
            try:
                c, _ = srv.accept()
                with c:
                    if c.recv(16) == b"show":
                        callback()
            except OSError:
                return
    threading.Thread(target=loop, daemon=True).start()


# ---------------------------------------------------------------- the window
class RoundButton(tk.Canvas):
    """A flat rounded button (tk's own buttons can't round their corners)."""

    def __init__(self, parent, text, command, width=150, height=44):
        super().__init__(parent, width=width, height=height, bg=BG, highlightthickness=0, cursor="hand2")
        self.w, self.h, self.command = width, height, command
        self.style("secondary")
        self.set_text(text)
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Enter>", lambda e: self.draw(hover=True))
        self.bind("<Leave>", lambda e: self.draw())

    def style(self, kind):
        self.kind = kind

    def set_text(self, text):
        self.text = text
        self.draw()

    def draw(self, hover=False):
        self.delete("all")
        if self.kind == "primary":
            fill, outline, fg = (GREEN_DARK if hover else GREEN), "", "#FFFFFF"
        else:
            fill, outline, fg = ("#F4F6F5" if hover else BG), LINE, INK
        r, w, h = 10, self.w - 1, self.h - 1
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h, r, h, 0, h, 0, h - r, 0, r, 0, 0]
        self.create_polygon(pts, smooth=True, fill=fill, outline=outline or fill)
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg, font=F(10, "bold" if self.kind == "primary" else "normal"))


class App:
    def __init__(self, root):
        self.root = root
        root.title("Tidy")
        root.configure(bg=BG)
        root.resizable(False, False)
        root.geometry("380x495")
        try:
            root.iconbitmap(str(ASSETS / "tidy.ico"))
        except Exception:
            pass
        try:
            from PIL import Image, ImageTk
            self.logo = ImageTk.PhotoImage(Image.open(ASSETS / "tidy.png").resize((96, 96), Image.LANCZOS))
        except Exception:
            self.logo = tk.PhotoImage(file=str(ASSETS / "tidy_128.png"))

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=32, pady=(30, 18))
        tk.Label(body, image=self.logo, bg=BG).pack()
        tk.Label(body, text="Tidy", font=F(22, "bold"), bg=BG, fg=INK).pack(pady=(10, 0))
        tk.Label(body, text="Claude organizes your folders", font=F(10), bg=BG, fg=MUTED).pack()

        self.pill = tk.Frame(body, bg=PILL_ON)
        self.pill.pack(pady=(14, 0))
        self.dot = tk.Canvas(self.pill, width=10, height=10, bg=PILL_ON, highlightthickness=0)
        self.dot.pack(side="left", padx=(12, 6), pady=7)
        self.pill_text = tk.Label(self.pill, font=F(10, "bold"), bg=PILL_ON, fg=GREEN_DARK)
        self.pill_text.pack(side="left", padx=(0, 12))

        self.msg = tk.Label(body, font=F(9), bg=BG, fg=MUTED, wraplength=300, justify="center")
        self.msg.pack(pady=(12, 0))
        self.link = tk.Label(body, font=F(9, "underline"), bg=BG, fg=GREEN_DARK, cursor="hand2")
        self.link.pack(pady=(6, 0))
        self.link.bind("<Button-1>", lambda e: self.click_link())
        self.link_url = None
        self.update_to = None

        tk.Frame(body, bg=BG).pack(fill="both", expand=True)
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        self.history_btn = RoundButton(row, "History & undo", open_history)
        self.history_btn.pack(side="left")
        self.connect_btn = RoundButton(row, "", self.toggle)
        self.connect_btn.pack(side="right")
        foot = tk.Frame(body, bg=BG)
        foot.pack(pady=(12, 0))
        tk.Label(foot, text=f"version {version()}  ·", font=F(8), bg=BG, fg=FAINT).pack(side="left")
        gear = tk.Label(foot, text="⚙ Settings", font=F(8), bg=BG, fg=MUTED, cursor="hand2")
        gear.pack(side="left", padx=(4, 0))
        gear.bind("<Button-1>", lambda e: self.open_settings())
        self.settings = load_settings()
        self.release = None          # newest release found on GitHub
        self.settings_win = None

        # closing or minimizing hides to the tray
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.bind("<Unmap>", self.on_unmap)
        self.tray = None
        if MAC:   # normal Mac app: the Dock icon brings the window back, Cmd+Q quits
            root.createcommand("tk::mac::ReopenApplication", self.show)
            root.createcommand("tk::mac::Quit", self.quit)
        else:
            self.start_tray()
            listen_for_show(lambda: root.after(0, self.show))
        self.refresh()
        self.auto_check()

    # ---- updates
    def auto_check(self):
        if self.settings.get("auto_update_check", True):
            self.check_update()
        self.root.after(24 * 3600 * 1000, self.auto_check)   # once a day while Tidy runs

    def check_update(self, done=None):
        def work():
            rel = latest_release()
            def apply():
                if rel:
                    self.release = rel
                    self.update_to = rel["version"] if newer(rel["version"], version()) else None
                self.refresh()
                if done:
                    done(rel)
            self.root.after(0, apply)
        threading.Thread(target=work, daemon=True).start()

    def open_settings(self):
        self.show()
        if self.settings_win and self.settings_win.alive():
            self.settings_win.win.lift()
            return
        self.settings_win = SettingsWindow(self)

    # ---- status
    def refresh(self, note=None, error=False):
        on = is_connected()
        bg = PILL_ON if on else PILL_OFF
        self.pill.config(bg=bg)
        self.dot.config(bg=bg)
        self.dot.delete("all")
        self.dot.create_oval(1, 1, 9, 9, fill=GREEN if on else "#9AA5A2", outline="")
        self.pill_text.config(text="Connected to Claude" if on else "Not connected", bg=bg, fg=GREEN_DARK if on else MUTED)
        self.connect_btn.style("secondary" if on else "primary")
        self.connect_btn.set_text("Disconnect" if on else "Connect to Claude")
        problem = location_problem()
        default = (problem or "In Claude chat, say “tidy” and the folder. Claude shows a plan, you approve, it's done."
                   if on else "One click and Claude can look at, move and rename your files. Every change can be undone.")
        self.msg.config(text=note or default, fg="#B03A2E" if error else MUTED)
        if not claude_installed():
            self.link_url, text = CLAUDE_DOWNLOAD, "Tidy needs Claude Desktop. Get it here"
        elif self.update_to:
            self.link_url, text = "settings", f"Tidy {self.update_to} is out. Update now"
        else:
            self.link_url, text = None, ""
        self.link.config(text=text)

    def click_link(self):
        if self.link_url == "settings":
            self.open_settings()
        elif self.link_url:
            webbrowser.open(self.link_url)

    def toggle(self):
        try:
            if is_connected():
                disconnect()
                self.refresh(f"Disconnected. {RESTART} to finish.")
            else:
                connect()
                self.refresh(f"Connected! {RESTART}. Then say “tidy” + a folder.")
        except Exception as e:
            self.refresh(f"Problem: {e}", error=True)

    # ---- tray
    def start_tray(self):
        try:
            import pystray
            from PIL import Image
        except Exception:
            return   # no tray available: closing quits instead
        menu = pystray.Menu(
            pystray.MenuItem("Open Tidy", lambda: self.root.after(0, self.show), default=True),
            pystray.MenuItem("History & undo", lambda: open_history()),
            pystray.MenuItem("Quit", lambda: self.root.after(0, self.quit)),
        )
        self.tray = pystray.Icon("Tidy", Image.open(ASSETS / "tidy.png"), "Tidy", menu)
        self.tray.run_detached()

    def on_unmap(self, event):
        if MAC:
            return   # minimizing to the Dock is normal on a Mac
        if event.widget is self.root and self.root.state() == "iconic" and self.tray:
            self.root.after(0, self.hide)

    def hide(self):
        if self.tray or MAC:
            self.root.withdraw()
        else:
            self.quit()

    def show(self):
        self.root.deiconify()
        self.root.state("normal")
        self.root.lift()
        self.root.focus_force()
        self.refresh()

    def quit(self):
        if self.tray:
            try:
                self.tray.stop()
            except Exception:
                pass
        self.root.destroy()


class SettingsWindow:
    """Small settings window: updates (check / update now / check every day) and My notes."""

    def __init__(self, app):
        self.app = app
        w = self.win = tk.Toplevel(app.root, bg=BG)
        w.title("Tidy settings")
        w.resizable(False, False)
        w.geometry("360x380")
        w.transient(app.root)
        try:
            w.iconbitmap(str(ASSETS / "tidy.ico"))
        except Exception:
            pass
        body = tk.Frame(w, bg=BG)
        body.pack(fill="both", expand=True, padx=26, pady=22)
        tk.Label(body, text="Settings", font=F(15, "bold"), bg=BG, fg=INK).pack(anchor="w")

        self.section(body, "Updates")
        self.status = tk.Label(body, font=F(9), bg=BG, fg=MUTED, wraplength=300, justify="left", anchor="w")
        self.status.pack(fill="x")
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(10, 0))
        self.check_btn = RoundButton(row, "Check now", self.check, width=120, height=38)
        self.check_btn.pack(side="left")
        self.update_btn = RoundButton(row, "Update now", self.update_now, width=150, height=38)
        self.update_btn.style("primary")
        self.update_btn.draw()
        self.auto = tk.BooleanVar(value=app.settings.get("auto_update_check", True))
        tk.Checkbutton(body, text="Check for updates every day", variable=self.auto, command=self.save_auto,
                       font=F(9), bg=BG, fg=INK, activebackground=BG, selectcolor=BG, anchor="w",
                       highlightthickness=0, bd=0).pack(fill="x", pady=(10, 0))

        self.section(body, "My notes")
        self.notes_text = tk.Label(body, font=F(9), bg=BG, fg=MUTED, wraplength=300, justify="left", anchor="w")
        self.notes_text.pack(fill="x")
        RoundButton(body, "Open my notes", open_notes, width=150, height=38).pack(anchor="w", pady=(10, 0))

        self.busy = False
        self.show_state()
        self.check()

    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def section(self, parent, title):
        tk.Frame(parent, bg=LINE, height=1).pack(fill="x", pady=(16, 10))
        tk.Label(parent, text=title, font=F(10, "bold"), bg=BG, fg=INK).pack(anchor="w", pady=(0, 4))

    def show_state(self, text=None):
        n = notes_count()
        self.notes_text.config(text=(f"{n} note{'s' if n != 1 else ''}. " if n else "No notes yet. ")
                               + "Claude reads them before every plan, and asks before saving a new one.")
        a = self.app
        if a.update_to:
            self.update_btn.pack(side="right")
        else:
            self.update_btn.pack_forget()
        if text:
            self.status.config(text=text)
        elif a.update_to:
            self.status.config(text=f"Tidy {a.update_to} is ready (you have {version()}).")
        elif a.release:
            self.status.config(text=f"You have the newest version ({version()}).")

    def check(self):
        if self.busy:
            return
        self.status.config(text="Checking for updates…")
        self.app.check_update(lambda rel: self.alive() and self.show_state(
            None if rel else "Couldn't reach GitHub to check. Are you online?"))

    def save_auto(self):
        self.app.settings["auto_update_check"] = bool(self.auto.get())
        save_settings(self.app.settings)

    def update_now(self):
        a = self.app
        if self.busy or not a.update_to:
            return
        v = a.update_to
        url = (a.release or {}).get("assets", {}).get(update_file_name(v))
        if not url:
            self.status.config(text="This update has no file for this computer yet. Opening the download page.")
            webbrowser.open(RELEASES)
            return
        self.busy = True
        dest = (Path.home() / "Downloads" if MAC and (Path.home() / "Downloads").exists()
                else Path(tempfile.gettempdir())) / update_file_name(v)

        def progress(f):
            self.win.after(0, lambda: self.alive() and self.status.config(text=f"Downloading Tidy {v}… {int(f * 100)}%"))

        def work():
            try:
                download(url, dest, progress)
                self.win.after(0, lambda: self.install(dest, v))
            except Exception as e:
                def fail(e=e):
                    self.busy = False
                    if self.alive():
                        self.status.config(text=f"The download didn't work ({e}). Try again, or get it from the download page.")
                self.win.after(0, fail)
        threading.Thread(target=work, daemon=True).start()

    def install(self, path, v):
        if MAC:
            subprocess.Popen(["open", str(path)])
            self.busy = False
            self.status.config(text=f"Tidy {v} is open in Finder. Quit Tidy (Cmd+Q), drag the new Tidy onto "
                                    "Applications and choose Replace, then open Tidy again.")
            return
        self.status.config(text=f"Installing Tidy {v}… Tidy closes and opens again by itself. "
                                "Then quit and reopen Claude.")
        self.win.update()
        # /relaunch=1 makes the installer open Tidy again when it's done (see installer/tidy.iss)
        subprocess.Popen([str(path), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/relaunch=1"])
        self.win.after(1500, self.app.quit)


class ConfirmBox:
    """The Tidy-style Yes/No window shown before anything goes to the Recycle Bin / Trash."""

    def __init__(self, root, req):
        self.root, self.answer = root, 11
        trash = req.get("trash", "Trash" if MAC else "Recycle Bin")
        items = req.get("items", [])
        n = len(items)
        root.title("Tidy - OK to delete?")
        root.configure(bg=BG)
        root.resizable(False, False)
        try:
            root.iconbitmap(str(ASSETS / "tidy.ico"))
        except Exception:
            pass
        try:
            from PIL import Image, ImageTk
            self.logo = ImageTk.PhotoImage(Image.open(ASSETS / "tidy.png").resize((44, 44), Image.LANCZOS))
        except Exception:
            self.logo = tk.PhotoImage(file=str(ASSETS / "tidy_128.png")).subsample(3, 3)

        body = tk.Frame(root, bg=BG)
        body.pack(fill="both", expand=True, padx=26, pady=(22, 20))
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x")
        tk.Label(head, image=self.logo, bg=BG).pack(side="left", padx=(0, 12))
        titles = tk.Frame(head, bg=BG)
        titles.pack(side="left", fill="x")
        tk.Label(titles, text=f"Move {n} item{'s' if n != 1 else ''} to the {trash}?", font=F(13, "bold"),
                 bg=BG, fg=INK, anchor="w").pack(anchor="w")
        tk.Label(titles, text="Claude asked to remove these. Nothing happens unless you say yes.",
                 font=F(9), bg=BG, fg=MUTED, anchor="w").pack(anchor="w")

        if req.get("reason"):
            tk.Label(body, text="Why", font=F(9, "bold"), bg=BG, fg=INK).pack(anchor="w", pady=(16, 2))
            tk.Label(body, text=req["reason"], font=F(9), bg=BG, fg=INK, wraplength=410, justify="left",
                     anchor="w").pack(anchor="w", fill="x")

        box = tk.Frame(body, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", pady=(14, 0))
        inner = tk.Frame(box, bg="#F7F9F8")
        inner.pack(fill="both")
        lines = min(max(n, 1), 8)
        text = tk.Text(inner, height=lines, width=56, font=F(9), bg="#F7F9F8", fg=INK, relief="flat",
                       bd=0, padx=12, pady=8, wrap="none", highlightthickness=0, cursor="arrow")
        text.tag_configure("size", foreground=MUTED)
        for name, size, *_ in items:
            text.insert("end", f"{name}", ())
            text.insert("end", f"   {size}\n", ("size",))
        text.delete("end-2c", "end-1c")
        text.config(state="disabled")
        if n > 8:
            sb = tk.Scrollbar(inner, command=text.yview)
            sb.pack(side="right", fill="y")
            text.config(yscrollcommand=sb.set)
        text.pack(side="left", fill="both", expand=True)

        tk.Label(body, text=f"{n} item{'s' if n != 1 else ''} · {req.get('total', '')} · you can get them back "
                            f"from the {trash}", font=F(8), bg=BG, fg=FAINT).pack(anchor="w", pady=(8, 0))

        row = tk.Frame(body, bg=BG)
        row.pack(fill="x", pady=(18, 0))
        yes = RoundButton(row, f"Move to {trash}", lambda: self.done(10), width=190, height=42)
        yes.style("primary")
        yes.draw()
        yes.pack(side="right")
        RoundButton(row, "Keep them", lambda: self.done(11), width=130, height=42).pack(side="right", padx=(0, 10))

        root.protocol("WM_DELETE_WINDOW", lambda: self.done(11))
        root.bind("<Escape>", lambda e: self.done(11))
        root.update_idletasks()
        w, h = root.winfo_reqwidth(), root.winfo_reqheight()
        root.geometry(f"+{(root.winfo_screenwidth() - w) // 2}+{(root.winfo_screenheight() - h) // 3}")
        root.attributes("-topmost", True)
        root.lift()
        root.after(150, root.focus_force)
        auto = os.environ.get("TIDY_TEST_ANSWER")   # build-machine test only: click by itself
        if auto in ("yes", "no"):
            root.after(1500, lambda: self.done(10 if auto == "yes" else 11))

    def done(self, code):
        self.answer = code
        self.root.destroy()


def confirm(req_path):
    try:
        req = json.loads(Path(req_path).read_text(encoding="utf-8"))
    except Exception:
        return 1   # tidy-server falls back to the system's own box
    root = tk.Tk()
    box = ConfirmBox(root, req)
    root.mainloop()
    return box.answer


def selftest():
    """Build machine check: open the window and Settings, then close. Any error -> exit code 1."""
    root = tk.Tk()
    app = App(root)
    app.open_settings()
    root.update()
    assert app.settings_win.alive()
    root.after(3000, app.quit)
    root.mainloop()
    print("selftest OK")
    return 0


def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--confirm" in sys.argv:
        i = sys.argv.index("--confirm")
        return confirm(sys.argv[i + 1]) if i + 1 < len(sys.argv) else 1
    if "--connect" in sys.argv or "--disconnect" in sys.argv:   # the installer / uninstaller
        try:
            connect() if "--connect" in sys.argv else disconnect()
            return 0
        except Exception as e:
            try:
                (DATA).mkdir(parents=True, exist_ok=True)
                (DATA / "connect_error.txt").write_text(str(e), encoding="utf-8")
            except Exception:
                pass
            return 1
    if not MAC and ask_running_tidy_to_show():
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
