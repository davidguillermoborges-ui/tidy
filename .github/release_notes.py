"""Release notes for the GitHub Releases page: download steps + this version's CHANGES.md section.
   python .github/release_notes.py 1.3.0 > notes.md
"""
import re
import sys

ver = sys.argv[1]
text = open("CHANGES.md", encoding="utf-8").read()
m = re.search(r"(?ms)^## " + re.escape(ver) + r"\b[^\n]*\n(.*?)(?=^## |\Z)", text)
section = m.group(1).strip() if m else ""

print(f"""## Download

- **Windows 10 / 11:** `TidySetup-{ver}.exe`. Run it, leave "Connect Tidy to Claude Desktop now" ticked, then quit and reopen Claude Desktop. If Windows says "Windows protected your PC", click **More info**, then **Run anyway**.
- **Mac (Apple Silicon: M1 or newer, macOS 12 or later):** `Tidy-{ver}.dmg`. Open it and drag Tidy into Applications, then open Tidy from Applications. The first time, macOS blocks it because it isn't signed yet: open **System Settings > Privacy & Security**, scroll down, click **Open Anyway** next to Tidy, and confirm. Then click **Connect to Claude**, and quit (Cmd+Q) and reopen Claude.

You need [Claude Desktop](https://claude.ai/download). Then type "tidy" and a folder in Claude, for example: tidy my Downloads folder.

## What's new

{section}""")
