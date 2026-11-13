# Tidy changes

## 1.4.1 (2026-11-13)
- Fix: moving folders "into" a folder that doesn't exist yet. Before, the first folder moved became the new folder itself, so its files ended up loose (this happened to Captioner when tidying Downloads). Now Tidy creates the target folder first and puts every item inside it with its own name. Undo removes the new folder again.

## 1.4.0 (2026-11-12)
- **Tidy learns each person (My Tidy notes).** Each person has their own notes, saved only on their own computer: project names and what belongs to them, where kinds of files go, naming styles, folders to leave alone.
  - Claude reads them before every plan, follows them, and says when a note decided something.
  - When you teach Claude something like that, it asks "Save this to your Tidy notes?" and only saves after you say yes. You can also say "forget the note about…".
  - New tools for Claude: `notes`, `save_note`, `forget_note`.
  - The notes are a plain text file you can edit yourself: Settings > Open my notes.
- **Settings** (the ⚙ Settings link under the Tidy window):
  - Shows your version and checks for updates, by itself once a day (you can turn that off) or with **Check now**.
  - When there's a new version, **Update now** downloads it. On Windows, Tidy installs it quietly and opens again by itself. On a Mac, the new DMG opens and you drag Tidy onto Applications.
  - The "Tidy x.y is out" line in the main window now opens Settings.
- **New delete box in the Tidy look.** The Yes/No box before anything goes to the Recycle Bin / Trash is now a Tidy window: the logo, how many items, Claude's reason, the list of files with sizes, and **Keep them** / **Move to Recycle Bin** buttons. Closing it or pressing Esc keeps the files. If it can't open, Tidy falls back to the old system box.
- GitHub's build machines now also open the window and Settings and click both answers in the delete box, on Windows and Mac.

## 1.3.0 (2026-11-12)
- **Tidy for Mac:** `Tidy-1.3.0.dmg` for Apple Silicon Macs (M1 or newer, macOS 12 or later). Drag Tidy into Applications, open it, click **Connect to Claude**. Not signed yet, so the first open needs **System Settings > Privacy & Security > Open Anyway**.
- On a Mac, Tidy works like a normal Mac app: closing the window keeps it running, its Dock icon opens it again, and Cmd+Q quits.
- Mac versions of the Windows-only parts:
  - Connects to Mac Claude's settings file (`~/Library/Application Support/Claude`).
  - Deleting uses a Mac Yes/No dialog and sends files to the Trash.
  - System, Library, Applications and your own Library folder can be read but never changed.
  - `drives` lists the startup disk and the disks in `/Volumes`.
  - History, undo and the log live in `~/Library/Application Support/Tidy`.
- If Tidy was opened straight from the DMG or from Downloads, it asks you to drag it into Applications first, so Claude doesn't lose it later. Connecting also clears macOS's "downloaded" mark on the app so macOS doesn't block Tidy when Claude starts it.
- Each release now has the Windows installer and the Mac DMG together. GitHub's Mac machine tests every build: the tests, the app starting, connect and disconnect from Applications, and the DMG.
- Windows: no changes apart from the version number.

## 1.2.0 (2026-11-12)
- **Installer for anyone:** `TidySetup-1.2.0.exe`. Installs for the current Windows user (no admin password) with Start menu and desktop shortcuts, and shows up in Windows "Apps" for uninstalling. A ticked "Connect Tidy to Claude Desktop now" box connects it during install (the normal and the Microsoft Store versions of Claude). Updating stops a running Tidy first. Uninstalling removes Tidy from Claude's settings and keeps your history and undo files.
- Download it from the GitHub Releases page. Each version tag (`v1.2.0`) builds and publishes the installer automatically, after the build machine has test-installed, connected and uninstalled it.
- The Tidy window now says when Claude Desktop isn't installed (with a link to get it) and when a newer Tidy is out (with a link to download it).
- Nothing in Tidy is specific to one person any more: Claude's instructions and the recycle box talk about "the user". The Higgsfield rename rule stays built in as an example rule.
- `Tidy.exe --connect` and `Tidy.exe --disconnect` connect and disconnect without opening the window (used by the installer).
- Connecting keeps every other connector already in Claude's settings (tested, including files Notepad saved with a BOM).

## 1.1.0 (2026-11-11)
- New look for the Tidy window (design "A"): logo, "Connected to Claude" status pill, a short how-to line, and two buttons: History & undo, and Connect/Disconnect.
- Tidy now lives in the Windows tray. Closing or minimizing the window hides it there; click the tray icon to open it; right-click for Open Tidy, History & undo, Quit. Starting Tidy again while it runs just shows the open window.
- "Connected" now checks only the settings file Claude really reads (%APPDATA%\\Claude). Before, it also counted Windows' private Store copy, so it could say Connected while Claude didn't load Tidy. Connect writes the real file (and keeps the Store copy in step).
- New tools for Claude: `photo_sheets` makes numbered contact sheets of a folder's photos (thumbnails only, originals untouched) so Claude can see what's in them and sort by character, project or kind; `clear_photo_sheets` removes them. Scans skip the `_Tidy sheets` folder.

## 1.0.0 (2026-11-11)
- First version. Claude can scan folders, find duplicates by content, move and rename (single or by pattern, with preview),
  make folders, remove empty folders, send to the Recycle Bin (only after a Yes on the PC), undo any job, and find files by name.
- Saved rename rules (Higgsfield `hf_...` names built in). Every job saves a relink list (old path -> new path).
- Windows, Program Files, ProgramData and AppData can be read but never changed. Names are never overwritten.
- Built as Windows EXEs: Tidy.exe (window with the "Connect to Claude" button) and tidy-server.exe (what Claude runs).
- Installed and updated by HMNS Dev (product `tidy`).
