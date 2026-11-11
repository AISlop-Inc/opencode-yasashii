"""Save actual candidates and accepted outputs for proposition-by-proposition review."""
import argparse
import json
import time
from pathlib import Path

from run import new, GLOSSARY


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--cases", default=str(Path(__file__).with_name("quality_cases.json")))
    args = ap.parse_args()
    cases = json.loads(Path(args.cases).read_text())
    results = []
    for model, glossary in [("0.8b", None), ("0.8b", GLOSSARY), ("2b", GLOSSARY)]:
        engine = new.load_engine(model)
        rows = []
        for case in cases:
            candidates = []

            def capture(*a, **kw):
                output = engine(*a, **kw)
                candidates.append(output)
                return output

            start = time.perf_counter()
            output, stats = new.convert_document(case["source"], capture, glossary)
            rows.append({**case, "candidates": candidates, "output": output,
                         "changed": case["source"] != output, "stats": stats,
                         "seconds": round(time.perf_counter() - start, 3)})
        result = {"model": model, "glossary": bool(glossary), "rows": rows}
        results.append(result)
        print(model, "glossary", bool(glossary), "cases", len(rows),
              "rewritten", sum(r["changed"] for r in rows),
              "reverted", sum(r["stats"]["reverted"] for r in rows), flush=True)
    Path(args.output).write_text(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
