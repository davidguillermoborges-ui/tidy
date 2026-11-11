# Tidy

Lets Claude look at, move, rename and organize folders on David's PC. You say "tidy <folder>" in Claude chat,
Claude scans it and proposes a simple plan, you approve, Claude does it. Every job can be undone.

| Path | What |
| --- | --- |
| `src/tidy_server.py` | The MCP server Claude runs (built as `tidy-server.exe`) |
| `src/tidy_app.py` | The small window with "Connect to Claude" (built as `Tidy.exe`) |
| `tidy.json` | Version number (bump it for every release; HMNS Dev reads it) |
| `tidy.spec` | PyInstaller build (both EXEs in one `Tidy` folder) |
| `.github/workflows/build.yml` | Builds on Windows for every push to main and force-pushes the app to the `dist` branch |
| `tests/` | `python -m unittest discover -s tests -v`; `tests/mcp_smoke.py` checks the server answers like Claude expects |

Install / update: HMNS Dev `pull` then `install product=tidy` (copies the `dist` branch to `%LOCALAPPDATA%\Programs\Tidy`,
adds Start menu and desktop shortcuts, and registers the `tidy` connector in Claude). Restart Claude after.

History and relink lists: `%LOCALAPPDATA%\Tidy\jobs`. Log: `%LOCALAPPDATA%\Tidy\tidy_log.txt`.
