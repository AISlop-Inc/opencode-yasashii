import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_html import y


class QualityRegressions(unittest.TestCase):
    def test_numeric_roles_not_just_multiset(self):
        self.assertIsNotNone(y.verify("時間は2秒から4秒に増えました。",
                                      "時間は4秒から2秒に増えました。"))

    def test_signed_and_scientific_numbers(self):
        for source, candidate in [
            ("差分は-2秒です。", "差分は2秒です。"),
            ("確率は.5です。", "確率は5です。"),
            ("しきい値は1e-3です。", "しきい値は1e+3です。"),
        ]:
            self.assertEqual(y.verify(source, candidate), "numbers-changed")

    def test_checklist_does_not_become_assertion(self):
        self.assertEqual(y.verify("誰が何をするかが変わっていないか。",
                                  "誰が何をするかは変わっていません。"), "question-lost")
        self.assertEqual(y.verify("説明が利用者への指示に変わっていないか。",
                                  "説明が利用者への指示に変わっていますか。"), "negative-question-changed")

    def test_calendar_units(self):
        self.assertIsNotNone(y.verify("2026年11月の結果です。", "2026年11日の結果です。"))
        self.assertIsNotNone(y.verify("期間は2年です。", "期間は2月です。"))

    def test_inline_html_context_not_fragment(self):
        raw = "<p>これは<strong>重要な条件</strong>別の内容が入ります。</p>"
        out, stats = y.convert_html(raw, lambda *a, **kw: self.fail("fragment rewritten"))
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_html_quotation(self):
        raw = "<p>説明には「元の文章を引用します。」を含めます。</p>"
        out, stats = y.convert_html(raw, lambda *a, **kw: self.fail("quotation rewritten"))
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_entities_not_fragment(self):
        raw = "<p>この会社は甲&amp;乙株式会社です。</p>"
        out, stats = y.convert_html(raw, lambda *a, **kw: self.fail("entity fragment rewritten"))
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_crlf_unchanged_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notes.md"
            raw = b"```python\r\nprint('hello')\r\n```\r\n"
            path.write_bytes(raw)
            subprocess.run([sys.executable, y.__file__, str(path), "--limit", "0"],
                           capture_output=True, check=True)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(path.with_name("notes.yasashii.md").read_bytes(), raw)

    def test_meaning_regressions(self):
        self.assertEqual(y.verify("機能を無効化しない設定では有効なままです。",
                                  "機能を使えない設定では有効なままです。"), "complex-negation-review")
        self.assertEqual(y.verify("ファイルを直接編集せず、文章を仕上げます。",
                                  "ファイルを直接編集しないでください。文章を仕上げます。"), "instruction-added")
        self.assertEqual(y.verify("文章を共通で仕上げる形に変えました。",
                                  "文章を共通の形に変えました。"), "finishing-action-lost")

    def test_crlf_stdin(self):
        raw = b"```\r\ncode\r\n```\r\n"
        result = subprocess.run([sys.executable, y.__file__, "--format", "markdown"],
                                input=raw, capture_output=True, check=True)
        self.assertEqual(result.stdout, raw)

    def test_review_not_a_semantic_certificate(self):
        _, stats = y.convert_document("結果を確認します。", lambda *a, **kw: "結果を確かめます。")
        self.assertTrue(stats["review_required"])

    def test_soft_wrapped_sentence(self):
        raw = "文書ファイルを直接編集せず、\n組み込む前の文章を仕上げます。\n"
        for format in ["text", "markdown"]:
            out, stats = y.convert_document(raw, lambda *a, **kw: self.fail("fragment rewritten"), format=format)
            self.assertEqual(raw, out)
            self.assertEqual(stats["nodes"], 0)

    def test_unconverted_html_heading_requires_review(self):
        heading = "起動平均は2.50秒、追加千環境でも3.25秒"
        raw = f"<h2>{heading}</h2><span>追加千環境のCold平均</span>"
        out, stats = y.convert_html(raw, lambda *a, **kw: self.fail("label rewritten"))
        self.assertEqual(raw, out)
        self.assertEqual(stats["changed_parts"], 0)
        self.assertTrue(stats["review_required"])
        self.assertEqual(stats["unconverted_labels"][0]["text"], heading)
        self.assertEqual(len(stats["unconverted_labels"]), 2)

    def test_unconverted_markdown_heading_requires_review(self):
        raw = "# 追加千環境でも3.25秒\n"
        out, stats = y.convert_document(raw, None, format="markdown")
        self.assertEqual(raw, out)
        self.assertTrue(stats["review_required"])
        self.assertEqual(stats["unconverted_labels"][0]["tag"], "heading")

    def test_formatted_heading_and_metric_label_require_review(self):
        raw = '<h2><strong>追加千環境でも3.25秒</strong></h2><span class="label"><em>追加測定の平均時間</em></span>'
        _, stats = y.convert_html(raw, None)
        self.assertTrue(stats["review_required"])
        self.assertEqual(len(stats["unconverted_labels"]), 2)

    def test_unconverted_text_label_requires_review(self):
        raw = "追加千環境のCold平均\n"
        out, stats = y.convert_document(raw, None)
        self.assertEqual(raw, out)
        self.assertTrue(stats["review_required"])

    def test_contents_link_label_requires_review(self):
        for raw, format in [
            ('<nav><a href="#long-run">千環境の追加測定</a></nav>', "html"),
            ("- [千環境の追加測定](#long-run)\n", "markdown"),
        ]:
            out, stats = y.convert_document(raw, None, format=format)
            self.assertEqual(raw, out)
            self.assertTrue(stats["review_required"])
            self.assertIn("千環境", stats["unconverted_labels"][0]["text"])

    def test_dry_run_can_audit_finished_document(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.yasashii.md"
            path.write_text("# 追加千環境でも3.25秒\n")
            result = subprocess.run([sys.executable, y.__file__, str(path), "--dry-run"],
                                    capture_output=True, text=True, check=True)
            self.assertIn("unconverted_labels", result.stdout)
            self.assertIn('"review_required": true', result.stdout)

    def test_protected_code_is_not_an_unconverted_label(self):
        for raw, format in [("<pre>追加千環境でも3.25秒</pre>", "html"),
                            ("```\n# 追加千環境でも3.25秒\n```\n", "markdown")]:
            _, stats = y.convert_document(raw, None, format=format)
            self.assertEqual(stats["unconverted_labels"], [])
            self.assertFalse(stats["review_required"])


if __name__ == "__main__":
    unittest.main()
