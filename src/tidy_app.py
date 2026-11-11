"""Tidy window: one button that connects Tidy to the Claude desktop app."""
import glob
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
HERE = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent
ASSETS = Path(getattr(sys, "_MEIPASS", "")) / "assets" if FROZEN else HERE.parent / "assets"
SERVER_EXE = HERE / "tidy-server.exe"
SERVER_PY = HERE / "tidy_server.py"
NAME = "tidy"
GREEN = "#16A37C"
DATA = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "Tidy"


def config_paths():
    paths = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    local = os.environ.get("LOCALAPPDATA")
    if local:  # Microsoft Store install of Claude
        for d in glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude")):
            paths.append(Path(d) / "claude_desktop_config.json")
    existing = [p for p in paths if p.exists() or p.parent.exists()]
    return existing or paths[:1]


def read_cfg(p):
    if p.exists():
        txt = p.read_text(encoding="utf-8-sig").strip()
        return json.loads(txt) if txt else {}
    return {}


def write_cfg(p, cfg):
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, p.with_suffix(".json.before-tidy"))
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def is_connected():
    for p in config_paths():
        try:
            if read_cfg(p).get("mcpServers", {}).get(NAME) == server_entry():
                return True
        except Exception:
            pass
    return False


def server_entry():
    """Same entry HMNS Dev writes, so both agree on what 'connected' means."""
    if FROZEN:
        return {"command": str(SERVER_EXE), "args": []}
    return {"command": sys.executable, "args": [str(SERVER_PY)]}


def connect():
    if FROZEN and not SERVER_EXE.exists():
        raise RuntimeError("tidy-server.exe is missing next to Tidy.exe. Reinstall Tidy.")
    entry = server_entry()
    for p in config_paths():
        cfg = read_cfg(p)
        cfg.setdefault("mcpServers", {})[NAME] = entry
        write_cfg(p, cfg)


def disconnect():
    for p in config_paths():
        cfg = read_cfg(p)
        if NAME in cfg.get("mcpServers", {}):
            del cfg["mcpServers"][NAME]
            write_cfg(p, cfg)


def version():
    base = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else HERE.parent
    try:
        return json.loads((base / "tidy.json").read_text(encoding="utf-8"))["version"]
    except Exception:
        return "dev"


class App:
    def __init__(self, root):
        self.root = root
        root.title("Tidy")
        root.configure(bg="white")
        root.resizable(False, False)
        try:
            root.iconbitmap(str(ASSETS / "tidy.ico"))
        except Exception:
            pass
        self.logo = tk.PhotoImage(file=str(ASSETS / "tidy_128.png"))
        tk.Label(root, image=self.logo, bg="white").pack(pady=(28, 6))
        tk.Label(root, text="Tidy", font=("Segoe UI", 22, "bold"), bg="white", fg="#1f2a2a").pack()
        tk.Label(root, text=f"version {version()}", font=("Segoe UI", 8), bg="white", fg="#9aa3a3").pack()
        tk.Label(root, text="Claude organizes your folders", font=("Segoe UI", 10),
                 bg="white", fg="#6b7676").pack(pady=(0, 18))
        self.btn = tk.Button(root, font=("Segoe UI", 12, "bold"), relief="flat", bd=0,
                             padx=28, pady=10, cursor="hand2", command=self.toggle)
        self.btn.pack()
        self.msg = tk.Label(root, font=("Segoe UI", 9), bg="white", fg="#6b7676",
                            wraplength=300, justify="center")
        self.msg.pack(pady=(14, 4), padx=24)
        link = tk.Label(root, text="Open history and relink lists", font=("Segoe UI", 9, "underline"),
                        bg="white", fg=GREEN, cursor="hand2")
        link.pack(pady=(4, 22))
        link.bind("<Button-1>", lambda e: self.open_history())
        self.refresh()
        root.geometry("360x440")

    def refresh(self, note=None):
        if is_connected():
            self.btn.config(text="Connected to Claude  ✓", bg="#e8f6f1", fg=GREEN,
                            activebackground="#d5efe6", activeforeground=GREEN)
            self.msg.config(text=note or "In Claude chat, just say “tidy” and the folder.\n"
                                         "Click the button again to disconnect.")
        else:
            self.btn.config(text="Connect to Claude", bg=GREEN, fg="white",
                            activebackground="#128a69", activeforeground="white")
            self.msg.config(text=note or "One click and Claude can look at, move and rename "
                                         "files for you. Every change can be undone.")

    def toggle(self):
        try:
            if is_connected():
                disconnect()
                self.refresh("Disconnected. Restart the Claude app to finish.")
            else:
                connect()
                self.refresh("Connected! Close the Claude app completely (also from the tray) "
                             "and open it again. Then say “tidy” + a folder in chat.")
        except Exception as e:
            self.msg.config(text=f"Problem: {e}", fg="#c0392b")

    def open_history(self):
        p = DATA / "jobs"
        p.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(["explorer", str(p)])


if __name__ == "__main__":
    r = tk.Tk()
    App(r)
    r.mainloop()
