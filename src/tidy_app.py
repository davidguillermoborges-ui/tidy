"""Tidy window (look "A"): status, History & undo, Connect/Disconnect. Lives in the Windows tray.

Closing or minimizing the window hides it to the tray; the tray icon opens it again, and its menu has
Open, History & undo and Quit. Starting Tidy.exe while it already runs just shows the open one.

Command line (used by the installer):  Tidy.exe --connect   /   Tidy.exe --disconnect
"""
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
ASSETS = Path(getattr(sys, "_MEIPASS", "")) / "assets" if FROZEN else HERE.parent / "assets"
SERVER_EXE = HERE / "tidy-server.exe"
SERVER_PY = HERE / "tidy_server.py"
NAME = "tidy"
DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Tidy"
SHOW_PORT = 47431   # a second Tidy.exe asks the running one to show itself here
REPO = "davidguillermoborges-ui/tidy"
RELEASES = f"https://github.com/{REPO}/releases/latest"
CLAUDE_DOWNLOAD = "https://claude.ai/download"

GREEN, GREEN_DARK = "#16A37C", "#0F6B51"
INK, MUTED, FAINT, LINE, BG = "#1B2422", "#55615E", "#6B7774", "#DDE3E1", "#FFFFFF"
PILL_ON, PILL_OFF = "#E6F6F0", "#F1F3F2"
FONT = "Segoe UI"


# ---------------------------------------------------------------- Claude's settings
def main_config():
    """The settings file Claude actually reads (%APPDATA%\\Claude). This is what 'Connected' means."""
    return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Claude" / "claude_desktop_config.json"


def store_configs():
    """The Microsoft Store copy, if there is one. Kept in step, but never counted as connected."""
    local = os.environ.get("LOCALAPPDATA")
    if not local:
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


def connect():
    if FROZEN and not SERVER_EXE.exists():
        raise RuntimeError("tidy-server.exe is missing next to Tidy.exe. Reinstall Tidy.")
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
    """Best guess whether Claude Desktop is on this PC (normal installer or Microsoft Store)."""
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
    """Newest version number on GitHub Releases, or None (offline, no releases yet...)."""
    try:
        req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                     headers={"User-Agent": "Tidy", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=6) as r:
            return json.loads(r.read().decode("utf-8")).get("tag_name", "").lstrip("v") or None
    except Exception:
        return None


def version():
    base = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else HERE.parent
    try:
        return json.loads((base / "tidy.json").read_text(encoding="utf-8"))["version"]
    except Exception:
        return "dev"


def open_history():
    p = DATA / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    subprocess.Popen(["explorer", str(p)])


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
        self.create_text(self.w / 2, self.h / 2, text=self.text, fill=fg, font=(FONT, 10, "bold" if self.kind == "primary" else "normal"))


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
        tk.Label(body, text="Tidy", font=(FONT, 22, "bold"), bg=BG, fg=INK).pack(pady=(10, 0))
        tk.Label(body, text="Claude organizes your folders", font=(FONT, 10), bg=BG, fg=MUTED).pack()

        self.pill = tk.Frame(body, bg=PILL_ON)
        self.pill.pack(pady=(14, 0))
        self.dot = tk.Canvas(self.pill, width=10, height=10, bg=PILL_ON, highlightthickness=0)
        self.dot.pack(side="left", padx=(12, 6), pady=7)
        self.pill_text = tk.Label(self.pill, font=(FONT, 10, "bold"), bg=PILL_ON, fg=GREEN_DARK)
        self.pill_text.pack(side="left", padx=(0, 12))

        self.msg = tk.Label(body, font=(FONT, 9), bg=BG, fg=MUTED, wraplength=300, justify="center")
        self.msg.pack(pady=(12, 0))
        self.link = tk.Label(body, font=(FONT, 9, "underline"), bg=BG, fg=GREEN_DARK, cursor="hand2")
        self.link.pack(pady=(6, 0))
        self.link.bind("<Button-1>", lambda e: self.link_url and webbrowser.open(self.link_url))
        self.link_url = None
        self.update_to = None

        tk.Frame(body, bg=BG).pack(fill="both", expand=True)
        row = tk.Frame(body, bg=BG)
        row.pack(fill="x")
        self.history_btn = RoundButton(row, "History & undo", open_history)
        self.history_btn.pack(side="left")
        self.connect_btn = RoundButton(row, "", self.toggle)
        self.connect_btn.pack(side="right")
        tk.Label(body, text=f"version {version()}", font=(FONT, 8), bg=BG, fg=FAINT).pack(pady=(12, 0))

        # closing or minimizing hides to the tray
        root.protocol("WM_DELETE_WINDOW", self.hide)
        root.bind("<Unmap>", self.on_unmap)
        self.tray = None
        self.start_tray()
        listen_for_show(lambda: root.after(0, self.show))
        self.refresh()
        threading.Thread(target=self.check_update, daemon=True).start()

    def check_update(self):
        v = latest_release()
        if v and newer(v, version()):
            self.update_to = v
            self.root.after(0, self.refresh)

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
        default = ("In Claude chat, say “tidy” and the folder. Claude shows a plan, you approve, it's done."
                   if on else "One click and Claude can look at, move and rename your files. Every change can be undone.")
        self.msg.config(text=note or default, fg="#B03A2E" if error else MUTED)
        if not claude_installed():
            self.link_url, text = CLAUDE_DOWNLOAD, "Tidy needs Claude Desktop. Get it here"
        elif self.update_to:
            self.link_url, text = RELEASES, f"Tidy {self.update_to} is out. Download the update"
        else:
            self.link_url, text = None, ""
        self.link.config(text=text)

    def toggle(self):
        try:
            if is_connected():
                disconnect()
                self.refresh("Disconnected. Quit Claude from its tray icon and open it again to finish.")
            else:
                connect()
                self.refresh("Connected! Quit Claude from its tray icon and open it again. Then say “tidy” + a folder.")
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
        if event.widget is self.root and self.root.state() == "iconic" and self.tray:
            self.root.after(0, self.hide)

    def hide(self):
        if self.tray:
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


def main():
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
    if ask_running_tidy_to_show():
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    sys.exit(main())
