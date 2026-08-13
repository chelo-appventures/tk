#!/usr/bin/env python3
import os
import sys
import unittest
import tempfile
import subprocess
from diffcomm import parse_diffc, serialize_diffc, strip_comments, find_target_line, Comment

SAMPLE_UNIFIED_DIFF = """diff --git a/src/app.py b/src/app.py
index e69de29..b831295 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,4 +10,5 @@ def calculate_total(items):
     total = 0
     for item in items:
-        total += item.price
+        if item.is_valid():
+            total += item.price
     return total
"""

class TestDiffcomm(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.diffc_path = os.path.join(self.temp_dir.name, "test.diffc")
        with open(self.diffc_path, "w", encoding="utf-8") as f:
            f.write(SAMPLE_UNIFIED_DIFF)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_and_serialize_roundtrip(self):
        doc = parse_diffc(SAMPLE_UNIFIED_DIFF)
        output = serialize_diffc(doc)
        self.assertEqual(output.strip(), SAMPLE_UNIFIED_DIFF.strip())

    def test_add_comment(self):
        doc = parse_diffc(SAMPLE_UNIFIED_DIFF)
        diff_file, hunk, line = find_target_line(doc, "src/app.py", "+12")
        self.assertIsNotNone(line)
        self.assertEqual(line.new_lineno, 12)
        
        line.comments.append(Comment(author="HUMAN", timestamp="2026-08-13 14:00", text="Log invalid items.", depth=1))
        serialized = serialize_diffc(doc)
        
        self.assertIn("> [HUMAN @ 2026-08-13 14:00]: Log invalid items.", serialized)

    def test_add_reply(self):
        doc = parse_diffc(SAMPLE_UNIFIED_DIFF)
        _, _, line = find_target_line(doc, "src/app.py", "+12")
        line.comments.append(Comment(author="HUMAN", timestamp="2026-08-13 14:00", text="Check null", depth=1))
        line.comments.append(Comment(author="AI", timestamp="2026-08-13 14:01", text="Fixed in commit", depth=2))
        
        serialized = serialize_diffc(doc)
        self.assertIn("> [HUMAN @ 2026-08-13 14:00]: Check null", serialized)
        self.assertIn("> > [AI @ 2026-08-13 14:01]: Fixed in commit", serialized)

    def test_strip_comments(self):
        doc = parse_diffc(SAMPLE_UNIFIED_DIFF)
        _, _, line = find_target_line(doc, "src/app.py", "+12")
        line.comments.append(Comment(author="HUMAN", timestamp="2026-08-13 14:00", text="Check null", depth=1))
        annotated = serialize_diffc(doc)
        
        cleaned = strip_comments(annotated)
        self.assertEqual(cleaned.strip(), SAMPLE_UNIFIED_DIFF.strip())

    def test_cli_integration(self):
        script = os.path.join(os.path.dirname(__file__), "diffcomm.py")
        
        # 1. init
        init_file = os.path.join(self.temp_dir.name, "cli_test.diffc")
        proc = subprocess.run([sys.executable, script, "init", init_file, "--input", self.diffc_path], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        
        # 2. comment
        proc = subprocess.run([sys.executable, script, "comment", init_file, "--file", "src/app.py", "--line", "+12", "--author", "HUMAN", "--text", "Test comment"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        
        # 3. reply
        proc = subprocess.run([sys.executable, script, "reply", init_file, "--file", "src/app.py", "--line", "+12", "--author", "AI", "--text", "Test reply"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)

        # 4. list
        proc = subprocess.run([sys.executable, script, "list", init_file], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("HUMAN", proc.stdout)
        self.assertIn("Test reply", proc.stdout)

        # 5. validate
        proc = subprocess.run([sys.executable, script, "validate", init_file], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Validation PASSED", proc.stdout)

        # 6. strip
        proc = subprocess.run([sys.executable, script, "strip", init_file], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertNotIn("Test comment", proc.stdout)
        self.assertIn("def calculate_total", proc.stdout)


if __name__ == "__main__":
    unittest.main()
