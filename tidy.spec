# PyInstaller build: one folder "Tidy" with Tidy.exe (the window) and tidy-server.exe (what Claude runs).
#   pyinstaller --noconfirm tidy.spec   ->  dist/Tidy/
from PyInstaller.utils.hooks import collect_submodules

datas = [("tidy.json", "."), ("assets/tidy.ico", "assets"), ("assets/tidy_128.png", "assets"), ("assets/tidy.png", "assets")]

server = Analysis(["src/tidy_server.py"], datas=datas,
                  hiddenimports=collect_submodules("mcp", filter=lambda n: not n.startswith("mcp.cli")) + ["send2trash", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageOps"], excludes=["tkinter"])
app = Analysis(["src/tidy_app.py"], datas=datas, hiddenimports=["pystray._win32", "PIL.ImageTk"],
               excludes=["mcp", "pydantic", "starlette", "uvicorn", "anyio"])

server_pyz = PYZ(server.pure)
app_pyz = PYZ(app.pure)

server_exe = EXE(server_pyz, server.scripts, [], exclude_binaries=True, name="tidy-server",
                 console=True, icon="assets/tidy.ico")
app_exe = EXE(app_pyz, app.scripts, [], exclude_binaries=True, name="Tidy",
              console=False, icon="assets/tidy.ico")

coll = COLLECT(server_exe, server.binaries, server.datas,
               app_exe, app.binaries, app.datas, name="Tidy")
