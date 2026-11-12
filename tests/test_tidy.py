"""Tidy tests on a throw-away folder: scan, duplicates, rename preview/apply, move, undo, protected folders."""
import json, os, shutil, sys, tempfile, unittest

TMP = tempfile.mkdtemp(prefix="tidy-test-")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "LocalAppData")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import tidy_server as T  # noqa: E402

REC = {"progress": ""}
HF = "hf_20261001_175428_1c15bc50-6ce4-462c-a60d-a16ec77c3be6.mp4"


class TidyTest(unittest.TestCase):
    def setUp(self):
        self.root = os.path.join(TMP, "work")
        shutil.rmtree(self.root, ignore_errors=True)
        os.makedirs(os.path.join(self.root, "Video"))
        os.makedirs(os.path.join(self.root, "Moc"))
        os.makedirs(os.path.join(self.root, "Empty", "Sub"))
        data = os.urandom(1_500_000)
        for p in (os.path.join(self.root, "Video", HF), os.path.join(self.root, "Moc", "copy.mp4")):
            with open(p, "wb") as f:
                f.write(data)
        with open(os.path.join(self.root, "notes.txt"), "w") as f:
            f.write("hi")

    def p(self, *a):
        return os.path.join(self.root, *a)

    def test_version_read(self):
        self.assertRegex(T.VERSION, r"^\d+\.\d+\.\d+$")

    def test_scan(self):
        r = T._do_scan(REC, self.root, True)
        self.assertEqual(r["total_files"], 3)
        self.assertIn(os.path.join("Empty", "Sub"), r["empty_folders"])
        self.assertEqual(r["messy_names"]["Higgsfield auto-name"]["count"], 1)

    def test_duplicates_by_content(self):
        r = T._do_dups(REC, [self.root], 1)
        self.assertEqual(r["duplicate_groups"], 1)
        self.assertEqual(len(r["groups"][0]["files"]), 2)

    def test_rename_preview_then_apply_then_undo(self):
        rule = T.rename_rules()["Higgsfield"]
        prev = T.rename_pattern(self.p("Video"), rule["find_regex"], rule["replace_with"])
        self.assertEqual(prev["preview"][0]["new"], "Higgsfield 2026-10-01 175428.mp4")
        self.assertTrue(os.path.exists(self.p("Video", HF)))   # preview changes nothing
        r = T.rename_pattern(self.p("Video"), rule["find_regex"], rule["replace_with"], apply=True)
        self.assertEqual(r["moved"], 1)
        self.assertTrue(os.path.exists(self.p("Video", "Higgsfield 2026-10-01 175428.mp4")))
        T.undo_job(r["job_id"])
        self.assertTrue(os.path.exists(self.p("Video", HF)))

    def test_move_makes_folders_never_overwrites_and_undoes(self):
        with open(self.p("taken.txt"), "w") as f:
            f.write("x")
        r = T.move([{"from": self.p("Video"), "to": self.p("01 Projects", "Clips", "Video")},
                    {"from": self.p("notes.txt"), "to": self.p("taken.txt")}], "test")
        self.assertEqual(r["moved"], 2)
        self.assertTrue(os.path.isdir(self.p("01 Projects", "Clips", "Video")))
        self.assertTrue(os.path.exists(self.p("taken (2).txt")))
        u = T.undo_job(r["job_id"])
        self.assertEqual(u["items_put_back"], 2)
        self.assertTrue(os.path.isdir(self.p("Video")))
        self.assertFalse(os.path.exists(self.p("01 Projects")))

    def test_remove_empty_folders(self):
        r = T._do_rm_empty(REC, self.root)
        self.assertEqual(r["count"], 2)
        self.assertFalse(os.path.exists(self.p("Empty")))

    def test_protected_locations_refused(self):
        r = T.move([{"from": os.path.join(os.environ["LOCALAPPDATA"], "x"), "to": self.p("x")}], "bad")
        self.assertEqual(r["moved"], 0)

    @unittest.skipUnless(sys.platform == "darwin", "Mac only")
    def test_mac_protected_and_drives(self):
        self.assertTrue(T._is_protected("/System/Library/x"))
        self.assertTrue(T._is_protected(T.HOME / "Library" / "Preferences"))
        self.assertTrue(T._is_protected("/"))
        self.assertFalse(T._is_protected(T.HOME / "Desktop" / "stuff"))
        self.assertEqual(T.drives()[0]["drive"], "/")

    def test_recycle_needs_yes(self):
        T._confirm_box = lambda title, text: False
        r = T._do_recycle(REC, [self.p("notes.txt")], "test")
        self.assertIn("No", r["status"])
        self.assertTrue(os.path.exists(self.p("notes.txt")))

    def test_photo_sheets_number_every_photo(self):
        from PIL import Image
        pics = os.path.join(self.root, "Pics")
        os.makedirs(os.path.join(pics, "sub"))
        for i in range(7):
            Image.new("RGB", (300 + i * 10, 200), (i * 30, 90, 160)).save(os.path.join(pics, f"p{i}.jpg"))
        Image.new("RGB", (50, 80)).save(os.path.join(pics, "sub", "deep.png"))
        with open(os.path.join(pics, "raw.dng"), "wb") as f:
            f.write(b"raw")
        r = T._do_sheets(REC, pics, True, 6, 120)
        self.assertEqual(r["photos"], 8)
        self.assertEqual(len(r["sheets"]), 2)
        self.assertEqual(r["not_photos_skipped"], {".dng": 1})
        self.assertEqual(r["index"][8], os.path.join("sub", "deep.png"))
        again = T._do_sheets(REC, pics, True, 48, 120)   # the sheets folder itself is never drawn
        self.assertEqual(again["photos"], 8)
        self.assertEqual(T.clear_photo_sheets(pics)["status"], "cleared")
        self.assertFalse(os.path.exists(os.path.join(pics, T.SHEETS_DIR)))


class AppConfigTest(unittest.TestCase):
    """'Connected' only counts Claude's real settings file, not the Store copy."""

    def setUp(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("no tkinter here")
        import importlib
        os.environ["APPDATA"] = os.path.join(TMP, "Roaming")
        os.environ["LOCALAPPDATA"] = os.path.join(TMP, "LocalAppData")
        store = os.path.join(TMP, "LocalAppData", "Packages", "Claude_test", "LocalCache", "Roaming", "Claude")
        os.makedirs(store, exist_ok=True)
        self.store = os.path.join(store, "claude_desktop_config.json")
        os.environ["HOME"] = os.path.join(TMP, "home")   # Mac keeps Claude's settings under the home folder
        import tidy_app
        self.A = importlib.reload(tidy_app)
        self.main = str(self.A.main_config())
        self.assertTrue(self.main.startswith(TMP))
        shutil.rmtree(os.path.dirname(self.main), ignore_errors=True)

    @unittest.skipIf(sys.platform == "darwin", "no Microsoft Store copy on a Mac")
    def test_store_copy_alone_is_not_connected(self):
        with open(self.store, "w") as f:
            json.dump({"mcpServers": {"tidy": self.A.server_entry()}}, f)
        self.assertFalse(self.A.is_connected())
        self.A.connect()
        self.assertTrue(self.A.is_connected())
        with open(self.main) as f:
            self.assertIn("tidy", json.load(f)["mcpServers"])
        self.A.disconnect()
        self.assertFalse(self.A.is_connected())
        with open(self.store) as f:
            self.assertNotIn("tidy", json.load(f)["mcpServers"])

    def test_command_line_connect_and_disconnect(self):
        sys.argv = ["Tidy.exe", "--connect"]
        self.assertEqual(self.A.main(), 0)
        self.assertTrue(self.A.is_connected())
        sys.argv = ["Tidy.exe", "--disconnect"]
        self.assertEqual(self.A.main(), 0)
        self.assertFalse(self.A.is_connected())

    def test_keeps_other_connectors(self):
        os.makedirs(os.path.dirname(self.main), exist_ok=True)
        with open(self.main, "w", encoding="utf-8-sig") as f:   # BOM, like Notepad saves it
            json.dump({"mcpServers": {"other": {"command": "x"}}, "keep": 1}, f)
        self.A.connect()
        with open(self.main, encoding="utf-8") as f:
            cfg = json.load(f)
        self.assertEqual(set(cfg["mcpServers"]), {"other", "tidy"})
        self.assertEqual(cfg["keep"], 1)

    def test_mac_paths(self):
        if sys.platform != "darwin":
            self.skipTest("Mac only")
        self.assertTrue(self.main.endswith("Library/Application Support/Claude/claude_desktop_config.json"))
        self.assertEqual(self.A.SERVER_EXE.name, "tidy-server")

    def test_version_compare(self):
        self.assertTrue(self.A.newer("1.10.0", "1.9.2"))
        self.assertTrue(self.A.newer("v1.2.0", "1.1.0"))
        self.assertFalse(self.A.newer("1.1.0", "1.1.0"))
        self.assertFalse(self.A.newer("1.2.0", "dev"))


if __name__ == "__main__":
    unittest.main()
