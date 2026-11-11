"""Exercise shared rewriting across formats with real inference and safe literals."""
import argparse
import json
import time
from pathlib import Path

from run import new, GLOSSARY

PROSE = [
    "当該機能を無効化する必要があります。",
    "接続数が50を超えた場合に限り、処理を中止します。",
    "返信案を作りましたが、送信はしていません。",
    "埋め込みベクトルを再計算するため、約1.8秒のオーバーヘッドが発生します。",
]
PROTECTED = """# 実行結果

> これは原文の引用です。

```python
message = "当該機能を無効化する必要があります。"
```

[詳しい説明](https://example.com/docs)

| 項目 | 値 |
| --- | --- |
| 処理時間 | 1.8秒 |
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    easy = new.load_engine("0.8b")
    inputs = {
        "text": "\n\n".join(PROSE) + "\n",
        "markdown": PROTECTED + "\n" + "\n".join("- " + text for text in PROSE) + "\n",
        "html": "<!doctype html><meta charset=\"utf-8\">" + "".join("<p>" + t + "</p>" for t in PROSE),
    }
    results = []
    for format, raw in inputs.items():
        times = []
        outputs = []
        for _ in range(3):
            t = time.perf_counter()
            converted, stats = new.convert_document(raw, easy, GLOSSARY, format=format)
            times.append(round(time.perf_counter() - t, 3))
            outputs.append(converted)
        assert len(set(outputs)) == 1
        assert sorted(new.NUM.findall(raw)) == sorted(new.NUM.findall(converted))
        if format == "markdown":
            assert converted.startswith(PROTECTED)
        suffix = {"text": "txt", "markdown": "md", "html": "html"}[format]
        (outdir / f"input.{suffix}").write_text(raw)
        (outdir / f"output.{suffix}").write_text(converted)
        row = {"format": format, "times_s": times, "stable": True, "numbers_preserved": True, **stats}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    (outdir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
