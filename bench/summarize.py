"""Aggregate repeats without treating string matches as overall language accuracy."""
import argparse
import json
import statistics
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    args = ap.parse_args()
    root = Path(args.directory)
    summary = []
    for model in ["0.8b", "2b"]:
        runs = [json.loads((root / f"{model}-run{i}.json").read_text()) for i in [1, 2, 3]]
        for k, variant in enumerate(runs[0]["results"]):
            rows = variant["rows"]
            by_id = {r["id"]: r["output"] for r in rows}
            # Only previously observed error signatures; NOT an accuracy score.
            known_errors = []
            if "埋め込まれた" in by_id["terms"]:
                known_errors.append("embedding-mistranslated")
            if "が使えない環境" in by_id["latency"]:
                known_errors.append("latency-confused-with-availability")
            remaining_terms = sum(term in by_id[case] for term, case in [
                ("非同期", "async"), ("埋め込みベクトル", "terms"),
                ("オーバーヘッド", "terms"), ("レイテンシ", "latency")])
            summary.append({
                "model": model, "variant": variant["variant"],
                "seconds": [run["results"][k]["seconds"] for run in runs],
                "median_seconds": statistics.median(run["results"][k]["seconds"] for run in runs),
                "stable": all(run["results"][k]["rows"] == rows for run in runs),
                "numbers_preserved": sum(r["numbers_ok"] for r in rows),
                "changed": sum(r["changed"] for r in rows),
                "known_error_signatures": known_errors,
                "remaining_technical_terms_of_4": remaining_terms,
            })
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    for row in summary:
        print(json.dumps(row, ensure_ascii=False))


if __name__ == "__main__":
    main()
