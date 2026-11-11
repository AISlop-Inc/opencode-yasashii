import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "yasashii", Path(__file__).parents[1] / "skills/yasashii/bin/yasashii.py")
y = importlib.util.module_from_spec(spec)
spec.loader.exec_module(y)


class Safety(unittest.TestCase):
    def test_offsets_and_escaping(self):
        sentence = "処理時間は2秒です。"
        raw = f'<style>/*{sentence}*/</style><p title="{sentence}">{sentence}</p>'
        out, stats = y.convert_html(raw, lambda *a, **kw: "待つ時間は2秒です。")
        self.assertEqual(out, f'<style>/*{sentence}*/</style><p title="{sentence}">待つ時間は2秒です。</p>')
        self.assertEqual(stats["nodes"], 1)

    def test_protected(self):
        raw = '<p>結果の評価</p><pre>実行は必要です。</pre><a href="/a">詳細を確認します。</a>'
        out, stats = y.convert_html(raw, lambda *a, **kw: self.fail("called"))
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_numeric_addition(self):
        self.assertEqual(y.verify("結果を確認します。", "1つの結果を確認します。"), "numbers-changed")

    def test_units_and_truncation(self):
        self.assertEqual(y.verify("時間は2秒かかります。", "時間は2分かかります。"), "units-changed")
        self.assertEqual(y.verify("結果を確認します。", "結果を確認"), "incomplete-sentence")

    def test_removal_and_names(self):
        self.assertEqual(y.verify("本文をすべて落とした抜粋を使います。",
                                  "本文をすべて取った抜粋を使います。"), "removal-action-lost")
        self.assertIsNone(y.verify("本文を削除して使います。", "本文を取り除いて使います。"))
        self.assertTrue(y.verify("Hermesの結果を確認します。",
                                 "ヘルメスの結果を確認します。").startswith("code-changed"))

    def test_html_in_output(self):
        raw = "<p>これは処理の結果です。</p>"
        out, _ = y.convert_html(raw, lambda *a, **kw: "これは<処理>の結果です。")
        self.assertIn("&lt;処理&gt;", out)

    def test_numbers_reverted(self):
        raw = "<p>時間は12秒かかります。</p>"
        out, stats = y.convert_html(raw, lambda *a, **kw: "時間は21秒かかります。")
        self.assertEqual(raw, out)
        self.assertEqual(stats["reverted"], 1)

    def test_comments_and_entity(self):
        raw = "<!--結果を確認します。--><p>A&amp;Bの結果を確認します。</p>"
        out, _ = y.convert_html(raw, lambda *a, **kw: a[0])
        self.assertEqual(raw, out)

    def test_heading_and_continuation(self):
        raw = "<h2>保留6件の評価</h2><p><code>run()</code>を実行した結果です。</p>"
        out, stats = y.convert_html(raw, lambda *a, **kw: self.fail("called"))
        self.assertEqual(raw, out)
        self.assertEqual(stats["nodes"], 0)

    def test_duplicate_body(self):
        raw = "<p>結果を確認します。</p><p>結果を確認します。</p>"
        out, stats = y.convert_html(raw, lambda *a, **kw: "結果を確かめます。")
        self.assertEqual(out.count("結果を確かめます。"), 2)
        self.assertEqual(stats["nodes"], 2)


if __name__ == "__main__":
    unittest.main()
