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

    def test_recycle_needs_yes(self):
        T._confirm_box = lambda title, text: False
        r = T._do_recycle(REC, [self.p("notes.txt")], "test")
        self.assertIn("No", r["status"])
        self.assertTrue(os.path.exists(self.p("notes.txt")))


if __name__ == "__main__":
    unittest.main()
