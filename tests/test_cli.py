"""End-to-end tests for ds2terminal.py (the done check: every hard gate passes for every theme)."""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _path  # noqa: E402
from dsterm import terminal as T  # noqa: E402

CLI = os.path.join(_path.SCRIPTS, "ds2terminal.py")
HARBOR = os.path.join(_path.SAMPLE, "harbor.tokens.json")


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def run(*args):
    p = subprocess.run([sys.executable, "-I", CLI] + list(args), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True)
    return p.returncode, p.stdout, p.stderr


class TestCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = os.path.join(cls.tmp, "harbor")
        cls.rc, _o, cls.err = run(HARBOR, "--name", "Harbor", "--out", cls.out, "--quiet")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_harbor_done_check(self):
        self.assertEqual(self.rc, 0, self.err)
        for f in ("Harbor Light.terminal", "Harbor Dark.terminal", "report.md", "report.json", "preview.html"):
            self.assertTrue(os.path.isfile(os.path.join(self.out, f)), f)
        md = read(os.path.join(self.out, "report.md"))
        self.assertIn("every hard gate passes for every theme", md)

    def test_terminal_files_match_report(self):
        rep = json.loads(read(os.path.join(self.out, "report.json")))
        self.assertEqual(len(rep["themes"]), 2)
        for th in rep["themes"]:
            self.assertTrue(th["pass"])
            with open(os.path.join(self.out, th["file"]), "rb") as fh:
                prof = plistlib.load(fh)
            self.assertEqual(prof["name"], th["name"])
            self.assertEqual(th["file"], th["name"] + ".terminal")
            for row in th["slots"]:
                r, g, b, _a, info = T.decode_color(prof[row["key"]])
                self.assertEqual("#%02x%02x%02x" % tuple(int(round(x * 255)) for x in (r, g, b)), row["hex"], row["key"])
                self.assertEqual(info["NSID"], 7)
        dark = [t for t in rep["themes"] if t["mode"] == "dark"][0]
        self.assertTrue(dark["derived"])

    def test_needs_tool_link(self):
        rc, _o, err = run("https://claude.ai/artifact/abc", "--out", os.path.join(self.tmp, "x"), "--quiet")
        self.assertEqual(rc, 2)
        self.assertIn("Artifact", err)

    def test_bad_override(self):
        rc, _o, err = run(HARBOR, "--set", "purple=#ff00ff", "--out", os.path.join(self.tmp, "y"), "--quiet")
        self.assertEqual(rc, 2)

    def test_single_mode_and_options(self):
        out = os.path.join(self.tmp, "pidgin")
        rc, _o, err = run(os.path.join(_path.FIXTURES, "pidgin", "pidgin-editorial.dtcg.json"), "--name", "Pidgin",
                          "--modes", "dark", "--cursor", "bar", "--font-size", "14", "--out", out, "--quiet",
                          "--no-preview", "--report", "json")
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(os.listdir(out)), ["Pidgin Dark.terminal", "report.json"])
        with open(os.path.join(out, "Pidgin Dark.terminal"), "rb") as fh:
            prof = plistlib.load(fh)
        self.assertEqual(prof["CursorType"], 2)
        self.assertEqual(T.decode_font(prof["Font"]), ("SFMonoTerminal-Regular", 14.0))
        rep = json.loads(read(os.path.join(out, "report.json")))
        self.assertFalse(rep["themes"][0]["derived"])


class TestFolderSource(unittest.TestCase):
    """A folder is a source. The script reads every token file below it."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_folder_with_token_files(self):
        src = os.path.join(self.tmp, "design-system", "tokens")
        os.makedirs(src)
        shutil.copy(HARBOR, os.path.join(src, os.path.basename(HARBOR)))
        with open(os.path.join(self.tmp, "design-system", "LICENSE"), "w") as f:
            f.write("not a token file\n")
        out = os.path.join(self.tmp, "out")
        rc, _o, err = run(os.path.join(self.tmp, "design-system"), "--name", "Folder", "--out", out, "--quiet")
        self.assertEqual(rc, 0, err)
        self.assertTrue(os.path.exists(os.path.join(out, "Folder Light.terminal")))
        self.assertTrue(os.path.exists(os.path.join(out, "Folder Dark.terminal")))

    def test_folder_without_token_files(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty)
        rc, _o, err = run(empty, "--out", os.path.join(self.tmp, "out2"), "--quiet")
        self.assertEqual(rc, 2)
        self.assertIn("no token files", err)


if __name__ == "__main__":
    unittest.main()
