# Tidy changes

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
