import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_html import y


class Text(unittest.TestCase):
    def rewrite(self, text, **kwargs):
        return y.convert_document(text, lambda *a, **kw: "結果を確かめます。", **kwargs)

    def test_plain_and_blank_lines(self):
        out, stats = self.rewrite("結果を確認します。\n\n結果を確認します。\n")
        self.assertEqual(out, "結果を確かめます。\n\n結果を確かめます。\n")
        self.assertEqual(stats["nodes"], 2)

    def test_list_prefix(self):
        out, _ = self.rewrite("# タイトル\n\n- 結果を確認します。\n  1. 結果を確認します。\n", format="markdown")
        self.assertEqual(out, "# タイトル\n\n- 結果を確かめます。\n  1. 結果を確かめます。\n")

    def test_protected_markdown(self):
        raw = """---
description: 結果を確認します。
---
# タイトル

> 結果を確認します。

```python
# 結果を確認します。
```

    結果を確認します。

[結果を確認します。](https://example.com)

**結果を確認します。**

`結果を確認します。`

| 項目 | 説明 |
| --- | --- |
| 結果 | 結果を確認します。 |

<div>結果を確認します。</div>
"""
        out, stats = self.rewrite(raw, format="markdown")
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_raw_code_fences(self):
        raw = "~~~text\n結果を確認します。\n~~~\n"
        out, stats = self.rewrite(raw)
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_markdown_injection(self):
        raw = "- 結果を確認します。\n"
        for candidate in ["# 結果を確かめます。", "**結果を確かめます。**", "結果を確かめます。\n次に進みます。"]:
            out, stats = y.convert_document(raw, lambda *a, **kw: candidate, format="markdown")
            self.assertEqual(out, raw)
            self.assertEqual(stats["reverted"], 1)

    def test_protected_literals(self):
        raw = "URLはhttps://example.comを見てください。\n設定は/Users/example/config.jsonに保存します。\n「原文を引用します。」\n説明中の「原文の引用」は残します。\n"
        self.assertEqual(self.rewrite(raw)[0], raw)

    def test_numbers(self):
        raw = "結果は12件あります。\n"
        out, stats = y.convert_document(raw, lambda *a, **kw: "結果は21件あります。")
        self.assertEqual(out, raw)
        self.assertEqual(stats["reverted"], 1)

    def test_stdio_no_model_for_protected(self):
        raw = "```text\n結果を確認します。\n```\n"
        result = subprocess.run([sys.executable, y.__file__, "-", "--format", "markdown"],
                                input=raw, capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, raw)
        self.assertIn('"nodes": 0', result.stderr)

    def test_dry_run(self):
        result = subprocess.run([sys.executable, y.__file__, "--format", "markdown", "--dry-run"],
                                input="- 結果を確認します。\n", capture_output=True, text=True, check=True)
        self.assertIn('"nodes": 1', result.stdout)

    def test_file_copy_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "notes.md"
            source.write_text("# タイトル\n\n結果を確認します。\n")
            before = source.read_bytes()
            subprocess.run([sys.executable, y.__file__, str(source), "--limit", "0"],
                           capture_output=True, check=True)
            self.assertEqual(source.with_name("notes.yasashii.md").read_bytes(), before)
            result = subprocess.run([sys.executable, y.__file__, str(source), "--out", str(source)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_bytes(), before)

    def test_unknown_format(self):
        result = subprocess.run([sys.executable, y.__file__, "config.json"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("未対応", result.stderr)


if __name__ == "__main__":
    unittest.main()
