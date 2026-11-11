"""Adversarial HTML preservation checks, independent of model quality."""
from run import new, old

S = "処理時間は2秒です。"
T = "待つ時間は2秒です。"
CASES = {
    "attribute": f'<p title="{S}">{S}</p>',
    "comment": f'<!--{S}--><p>{S}</p>',
    "script": f'<script>const a="{S}";</script><p>{S}</p>',
    "style": f'<style>/*{S}*/</style><p>{S}</p>',
    "code": f'<code>{S}</code><p>{S}</p>',
    "pre": f'<pre>{S}</pre><p>{S}</p>',
    "anchor": f'<a href="/x">{S}</a><p>{S}</p>',
    "normal": f'<p>{S}</p>',
}


def main():
    counts = {"baseline": 0, "safe": 0}
    for name, raw in CASES.items():
        nodes = old.collect_nodes(raw)
        baseline, _ = old.replace_sequential(raw, nodes, [T for _ in nodes])
        safe, _ = new.convert_html(raw, lambda *a, **kw: T)
        prefix, suffix = raw.rsplit(S, 1)
        expected = prefix + T + suffix
        for label, out in [("baseline", baseline), ("safe", safe)]:
            ok = out == expected
            counts[label] += ok
            print(name, label, "PASS" if ok else "FAIL")
    print("total", counts, "/", len(CASES))


if __name__ == "__main__":
    main()
