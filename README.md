# Tidy

Let Claude organize the folders on your Windows PC or Mac.

Say "tidy my Downloads folder" in Claude. Claude looks through the folder and shows you a simple plan:
new folders, what moves where, better file names, and anything worth deleting. Nothing changes until you say yes,
and every change can be undone.

![Tidy logo](assets/tidy_128.png)

## Get it on Windows

1. You need **Windows 10 or 11** and **[Claude Desktop](https://claude.ai/download)**. Tidy works with the Claude
   desktop app only; the Claude website and phone app can't reach your PC's folders.
2. Download **TidySetup-x.y.z.exe** from the [latest release](https://github.com/davidguillermoborges-ui/tidy/releases/latest) and run it.
   The installer isn't signed yet, so Windows may show "Windows protected your PC". Click **More info**, then **Run anyway**.
3. Leave **Connect Tidy to Claude Desktop now** ticked.
4. Quit Claude Desktop fully (right-click its icon by the clock, then **Quit**) and open it again.
5. In Claude, type **tidy** and a folder, for example: `tidy C:\Users\me\Downloads`.

## Get it on a Mac

1. You need an **Apple Silicon Mac** (M1 or newer) with **macOS 12 or later**, and **[Claude Desktop](https://claude.ai/download)**.
2. Download **Tidy-x.y.z.dmg** from the [latest release](https://github.com/davidguillermoborges-ui/tidy/releases/latest),
   open it and drag **Tidy** into **Applications**.
3. Open Tidy from Applications. The first time, macOS blocks it because it isn't signed yet: open
   **System Settings > Privacy & Security**, scroll down, click **Open Anyway** next to Tidy, and confirm.
4. Click **Connect to Claude**, then quit Claude (Cmd+Q) and open it again.
5. In Claude, type **tidy** and a folder, for example: `tidy ~/Downloads`. The first time Claude opens your
   Desktop, Documents or Downloads, macOS asks whether Claude may access it. Click **Allow**.

## Using it

The Tidy window (Windows: Start menu > Tidy; Mac: Applications > Tidy) shows whether Claude is connected and has **Connect / Disconnect** and
**History & undo**. On Windows it stays in the tray by the clock when you close it; on a Mac it keeps running
in the Dock.

## Tidy learns how you work

Tell Claude things like "Lipbalm is the project with the pink hoodie images" or "never touch my camera card folders".
Claude asks **"Save this to your Tidy notes?"** and saves it only if you say yes. Before every plan Claude reads your
notes and follows them. Your notes stay on your computer, so everyone's Tidy learns them separately.
Open them from **⚙ Settings > Open my notes** to read, edit or delete them.

## Updates

**⚙ Settings** (under the Tidy window) checks for updates once a day. Click **Update now** when one is ready.
On Windows, Tidy installs it and opens again by itself. On a Mac, drag the new Tidy onto Applications and choose
Replace. Quit and reopen Claude after an update.

## How Tidy keeps your files safe

- Claude proposes, you approve. Claude is told never to move, rename or delete before you say yes in chat.
- Every move and rename is saved as a job you can undo ("undo the last tidy").
- Nothing is overwritten: if a name is taken, the new file gets " (2)".
- Deleting only sends to the Recycle Bin (Mac: Trash), and only after you click **Yes** in a box on your computer.
- System folders can be read but never changed (Windows, Program Files, ProgramData, AppData; on a Mac: System,
  Library, Applications and your own Library folder).
- Each job saves a relink list (old path → new path) for video and 3D projects that need to find moved media.
- Tidy runs only on your computer. Your files are not uploaded anywhere by Tidy; Claude sees file names, and small
  contact-sheet previews of photos when you ask it to sort pictures.

History and relink lists: `%LOCALAPPDATA%\Tidy\jobs` (Mac: `~/Library/Application Support/Tidy/jobs`).
Log: `tidy_log.txt` in the same Tidy folder.

## Uninstall

Mac: open Tidy, click **Disconnect**, quit it, then drag Tidy from Applications to the Trash.

Windows: Settings > Apps > Tidy > Uninstall. This also removes Tidy from Claude's settings. Your history files stay in
`%LOCALAPPDATA%\Tidy` (delete that folder if you don't want them).

## For developers

| Path | What |
| --- | --- |
| `src/tidy_server.py` | The MCP server Claude runs (built as `tidy-server.exe`) |
| `src/tidy_app.py` | The Tidy window with "Connect to Claude" (built as `Tidy.exe`; `--connect` / `--disconnect` work without the window) |
| `installer/tidy.iss` | Inno Setup script for `TidySetup-<version>.exe` |
| `tidy.json` | Version number (bump it for every release) |
| `tidy.spec` | PyInstaller build (Windows: both EXEs in one `Tidy` folder; Mac: `Tidy.app`) |
| `.github/release_notes.py` | Download steps + the version's CHANGES.md section for the Releases page |
| `.github/workflows/build.yml` | Windows build (tests, EXEs, installer, install/connect/uninstall test, `dist` branch on main) and Mac build (tests, app, connect test, DMG); a GitHub Release with both on `v*` tags or "Run workflow" with release ticked |
| `tests/` | `python -m unittest discover -s tests -v`; `tests/mcp_smoke.py` checks the server answers like Claude expects |

Release: bump `tidy.json`, add a `CHANGES.md` entry, merge to main, then push a tag `v<version>` (or run the workflow on main with "release" ticked).
