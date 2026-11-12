# PyInstaller build.
#   Windows: one folder "Tidy" with Tidy.exe (the window) and tidy-server.exe (what Claude runs).
#   Mac:     Tidy.app, with Tidy (the window) and tidy-server (what Claude runs) in Contents/MacOS.
#   pyinstaller --noconfirm tidy.spec   ->  dist/Tidy/  (Mac also dist/Tidy.app)
import json
import sys

from PyInstaller.utils.hooks import collect_submodules

MAC = sys.platform == "darwin"
VERSION = json.load(open("tidy.json", encoding="utf-8"))["version"]
ICON = "assets/tidy.icns" if MAC else "assets/tidy.ico"

datas = [("tidy.json", "."), ("assets/tidy.ico", "assets"), ("assets/tidy_128.png", "assets"), ("assets/tidy.png", "assets")]

server = Analysis(["src/tidy_server.py"], datas=datas,
                  hiddenimports=collect_submodules("mcp", filter=lambda n: not n.startswith("mcp.cli")) + ["send2trash", "PIL.Image", "PIL.ImageDraw", "PIL.ImageFont", "PIL.ImageOps"], excludes=["tkinter"])
app = Analysis(["src/tidy_app.py"], datas=datas, hiddenimports=["PIL.ImageTk"] + ([] if MAC else ["pystray._win32"]),
               excludes=["mcp", "pydantic", "starlette", "uvicorn", "anyio"] + (["pystray"] if MAC else []))

server_pyz = PYZ(server.pure)
app_pyz = PYZ(app.pure)

server_exe = EXE(server_pyz, server.scripts, [], exclude_binaries=True, name="tidy-server",
                 console=True, icon=ICON)
app_exe = EXE(app_pyz, app.scripts, [], exclude_binaries=True, name="Tidy",
              console=False, icon=ICON)

# Tidy (the window) comes first: on a Mac the first program is what the app opens.
coll = COLLECT(app_exe, app.binaries, app.datas,
               server_exe, server.binaries, server.datas, name="Tidy")

if MAC:
    BUNDLE(coll, name="Tidy.app", icon=ICON, bundle_identifier="com.hmns.tidy",
           info_plist={
               "CFBundleName": "Tidy",
               "CFBundleDisplayName": "Tidy",
               "CFBundleShortVersionString": VERSION,
               "CFBundleVersion": VERSION,
               "LSMinimumSystemVersion": "12.0",
               "NSHighResolutionCapable": True,
               "NSHumanReadableCopyright": "HMNS",
           })
