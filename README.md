# Tidy

Let Claude organize the folders on your Windows PC.

Say "tidy my Downloads folder" in Claude. Claude looks through the folder and shows you a simple plan:
new folders, what moves where, better file names, and anything worth deleting. Nothing changes until you say yes,
and every change can be undone.

![Tidy logo](assets/tidy_128.png)

## Get it

1. You need **Windows 10 or 11** and **[Claude Desktop](https://claude.ai/download)**. Tidy works with the Claude
   desktop app only; the Claude website and phone app can't reach your PC's folders.
2. Download **TidySetup-x.y.z.exe** from the [latest release](https://github.com/davidguillermoborges-ui/tidy/releases/latest) and run it.
   The installer isn't signed yet, so Windows may show "Windows protected your PC". Click **More info**, then **Run anyway**.
3. Leave **Connect Tidy to Claude Desktop now** ticked.
4. Quit Claude Desktop fully (right-click its icon by the clock, then **Quit**) and open it again.
5. In Claude, type **tidy** and a folder, for example: `tidy C:\Users\me\Downloads`.

The Tidy window (Start menu > Tidy) shows whether Claude is connected and has **Connect / Disconnect** and
**History & undo**. It stays in the tray by the clock when you close it.

## How Tidy keeps your files safe

- Claude proposes, you approve. Claude is told never to move, rename or delete before you say yes in chat.
- Every move and rename is saved as a job you can undo ("undo the last tidy").
- Nothing is overwritten: if a name is taken, the new file gets " (2)".
- Deleting only sends to the Recycle Bin, and only after you click **Yes** in a box on your PC.
- Windows, Program Files, ProgramData and AppData can be read but never changed.
- Each job saves a relink list (old path → new path) for video and 3D projects that need to find moved media.
- Tidy runs only on your PC. Your files are not uploaded anywhere by Tidy; Claude sees file names, and small
  contact-sheet previews of photos when you ask it to sort pictures.

History and relink lists: `%LOCALAPPDATA%\Tidy\jobs`. Log: `%LOCALAPPDATA%\Tidy\tidy_log.txt`.

## Uninstall

Windows Settings > Apps > Tidy > Uninstall. This also removes Tidy from Claude's settings. Your history files stay in
`%LOCALAPPDATA%\Tidy` (delete that folder if you don't want them).

## For developers

| Path | What |
| --- | --- |
| `src/tidy_server.py` | The MCP server Claude runs (built as `tidy-server.exe`) |
| `src/tidy_app.py` | The Tidy window with "Connect to Claude" (built as `Tidy.exe`; `--connect` / `--disconnect` work without the window) |
| `installer/tidy.iss` | Inno Setup script for `TidySetup-<version>.exe` |
| `tidy.json` | Version number (bump it for every release) |
| `tidy.spec` | PyInstaller build (both EXEs in one `Tidy` folder) |
| `.github/workflows/build.yml` | Windows build: tests, EXEs, installer, an install/connect/uninstall test; `dist` branch on main; a GitHub Release on `v*` tags |
| `tests/` | `python -m unittest discover -s tests -v`; `tests/mcp_smoke.py` checks the server answers like Claude expects |

Release: bump `tidy.json`, add a `CHANGES.md` entry, merge to main, then push a tag `v<version>` (or run the workflow on main with "release" ticked).
