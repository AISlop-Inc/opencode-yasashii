"""End-to-end on a user-supplied report; never writes next to the source."""
import argparse
import hashlib
import json
import time
from pathlib import Path

from bs4 import BeautifulSoup
from run import new, old, GLOSSARY


def signature(raw):
    soup = BeautifulSoup(raw, "html.parser")
    return {
        "tags_attrs": [(t.name, t.attrs) for t in soup.find_all()],
        "protected": [str(t) for t in soup.find_all(list(new.SKIP_TAGS | {"a"}))],
        "numbers": sorted(new.NUM.findall(soup.get_text())),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    raw = Path(args.input).read_text()
    outdir = Path(args.output_dir)
    outdir.mkdir(parents=True, exist_ok=True)
    results = []
    for variant in ["baseline", "safe", "glossary"]:
        t = time.perf_counter()
        engine = old.load_engine("0.8b") if variant == "baseline" else new.load_engine("0.8b")
        load_s = time.perf_counter() - t
        t = time.perf_counter()
        if variant == "baseline":
            nodes = old.collect_nodes(raw)
            translated, reverted = [], 0
            for text in nodes:
                lead, core, trail = old.split_lead_trail(text)
                pieces = []
                for part in old.chunk(core):
                    out = engine(part, max_tokens=max(96, min(2048, int(len(part) * 2.5))))
                    reason = old.verify(part, out)
                    reverted += bool(reason)
                    pieces.append(part if reason else out.strip())
                translated.append(lead + "".join(pieces) + trail)
            converted, unmatched = old.replace_sequential(raw, nodes, translated)
            stats = {"nodes": len(nodes), "reverted": reverted, "unmatched": unmatched}
        else:
            converted, stats = new.convert_html(raw, engine, GLOSSARY if variant == "glossary" else None)
        elapsed = time.perf_counter() - t
        before, after = signature(raw), signature(converted)
        result = {"variant": variant, "load_s": round(load_s, 3),
                  "seconds": round(elapsed, 3), **stats,
                  "preserved": {k: before[k] == after[k] for k in before}}
        (outdir / f"{variant}.html").write_text(converted)
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)
    (outdir / "report-results.json").write_text(json.dumps({
        "input_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "input_bytes": len(raw.encode()), "results": results,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
