"""Reproducible regression benchmark. Writes raw results only to --output."""
import argparse
import importlib.util
import json
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("new", ROOT / "skills/yasashii/bin/yasashii.py")
new = importlib.util.module_from_spec(spec)
spec.loader.exec_module(new)
# Frozen pre-improvement baseline, loaded from git, not a moving working copy.
import types
old = types.ModuleType("old")
exec(subprocess.check_output(["git", "show", "0038c01:skills/yasashii/bin/yasashii.py"],
                             cwd=ROOT, text=True), old.__dict__)

CASES = [
    ("numbers", "2026年11月時点では、応答時間が1,240msから860msへ約31%改善しました。"),
    ("negation", "この変更は処理を速くするものではありません。"),
    ("condition", "接続数が50を超えた場合に限り、処理を中止します。"),
    ("uncertainty", "改善する可能性がありますが、実測による確認はできていません。"),
    ("deletion", "会話からツール出力本文をすべて除外した抜粋だけを使います。"),
    ("async", "起動時のウォームアップを非同期化する必要があります。"),
    ("terms", "埋め込みベクトルを再計算するため、約1.8秒のオーバーヘッドが発生します。"),
    ("latency", "レイテンシを許容できない環境では無効化してください。"),
    ("permission", "承認を得るまではファイルを書き換えてはいけません。"),
    ("notdone", "返信案を作りましたが、送信はしていません。"),
    ("contrast", "メモリ使用量は減りましたが、処理時間は増えました。"),
    ("scope", "調査した範囲では不具合は確認できませんでした。"),
    ("retry", "失敗した場合は最大3回まで再試行し、それでも失敗したら終了します。"),
    ("label", "却下記憶の欠如"),
    ("label2", "保留6件の評価"),
    ("path", "設定ファイルは/Users/example/config.jsonに保存します。"),
    ("url", "詳細はhttps://example.com/docsを参照してください。"),
    ("code", "実行前に`event.error.status === 429`を確認します。"),
]
GLOSSARY = [
    {"source": "埋め込みベクトル", "target": "意味を数値で表したデータ"},
    {"source": "オーバーヘッド", "target": "余分にかかる時間"},
    {"source": "レイテンシ", "target": "応答時間"},
    {"source": "非同期化", "target": "他の処理を待たせずに進められるようにすること"},
]
CONTEXT = "ソフトウェアの技術報告。非同期処理は、準備の完了を待たずに他の処理を進める方式。レイテンシは応答時間。"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", default="0.8b", choices=["0.8b", "2b"])
    args = ap.parse_args()
    easy = new.load_engine(args.model)
    results = []
    for variant in ["baseline", "target-only", "safe", "glossary", "context", "both"]:
        t = time.perf_counter()
        rows = []
        for name, src in CASES:
            raw = f"<p>{src}</p>"
            if variant in {"baseline", "target-only"}:
                nodes = old.collect_nodes(raw)
                output = src
                for node in nodes:
                    out = easy(node, target="ja(easy)" if variant == "baseline" else "ja-easy",
                               source=None if variant == "baseline" else "ja").strip()
                    output = node if old.verify(node, out) else out
            else:
                g = GLOSSARY if variant in {"glossary", "both"} else None
                c = CONTEXT if variant in {"context", "both"} else None
                converted, _ = new.convert_html(raw, easy, g, context=c)
                output = new.html_mod.unescape(re.sub(r"</?p>", "", converted))
            rows.append({"id": name, "source": src, "output": output,
                         "changed": src != output,
                         "numbers_ok": sorted(new.NUM.findall(src)) == sorted(new.NUM.findall(output))})
        results.append({"variant": variant, "seconds": round(time.perf_counter() - t, 3), "rows": rows})
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": args.model, "results": results}, ensure_ascii=False, indent=2))
    for r in results:
        print(r["variant"], r["seconds"], "s; numeric", sum(x["numbers_ok"] for x in r["rows"]),
              "/", len(CASES), "changed", sum(x["changed"] for x in r["rows"]))


if __name__ == "__main__":
    main()
