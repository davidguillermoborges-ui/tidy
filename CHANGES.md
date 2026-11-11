# Tidy changes

## 1.0.0 (2026-11-11)
- First version. Claude can scan folders, find duplicates by content, move and rename (single or by pattern, with preview),
  make folders, remove empty folders, send to the Recycle Bin (only after a Yes on the PC), undo any job, and find files by name.
- Saved rename rules (Higgsfield `hf_...` names built in). Every job saves a relink list (old path -> new path).
- Windows, Program Files, ProgramData and AppData can be read but never changed. Names are never overwritten.
- Built as Windows EXEs: Tidy.exe (window with the "Connect to Claude" button) and tidy-server.exe (what Claude runs).
- Installed and updated by HMNS Dev (product `tidy`).
