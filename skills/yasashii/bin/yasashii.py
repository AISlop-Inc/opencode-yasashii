#!/usr/bin/env python3
"""やさしい日本語コンバータ（HTML）

PLaMo 3 Translate の target_lang="ja(easy)" で、HTML のテキストノードだけを
文単位でやさしい日本語に変換し、<name>.yasashii.html を併産する。
原文ファイルは変更しない。

使い方:
    yasashii report.html
    yasashii report.html --model 2b --glossary terms.json
"""

from __future__ import annotations

import argparse
import glob
import html as html_mod
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

MODELS = {
    "0.8b": "sizumita/plamo-3-translate-0.8b-mlx-mixed34",
    "2b": "pfnet/plamo-3-translate-2b-MLX-4bit",
    "8b": "pfnet/plamo-3-translate-8b-MLX-4bit",
}

SKIP_TAGS = {
    "script", "style", "code", "pre", "kbd", "samp", "var", "textarea",
    "svg", "math", "head", "title", "template", "noscript",
}
JP = re.compile(r"[ぁ-んァ-ヶー一-龠]")
SENT = re.compile(r"(?<=[。！？])")
NUM = re.compile(r"\d+(?:[.,]\d+)*")
FORBIDDEN = "<|plamo:"


def die(msg: str, code: int = 1):
    print(f"yasashii: {msg}", file=sys.stderr)
    raise SystemExit(code)


def load_engine(model_key: str):
    from huggingface_hub import snapshot_download
    from mlx_lm import generate
    from mlx_lm.tokenizer_utils import TokenizerWrapper
    from mlx_lm.utils import load_model

    repo = MODELS[model_key]
    snap = Path(snapshot_download(repo))
    tok_file = snap / "tokenization_plamo.py"
    if not tok_file.exists():
        die(f"{repo} に tokenization_plamo.py がありません（未対応のモデルです）")

    spec = importlib.util.spec_from_file_location("tokenization_plamo", tok_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tok = mod.Plamo3Tokenizer(
        vocab_file=str(snap / "tokenizer.jsonl"),
        break_around_consecutive_spaces_threshold=2,
        break_around_repeated_chars_threshold=4,
        clean_up_tokenization_spaces=False,
    )
    tok.chat_template = (snap / "chat_template.jinja").read_text(encoding="utf-8")
    try:
        loaded = load_model(snap)
    except Exception:
        # 2b/8b は同梱の modeling_plamo_mlx.py を読み込む
        loaded = load_model(snap, trust_remote_code=True)
    model = loaded[0] if isinstance(loaded, tuple) else loaded
    wrap = TokenizerWrapper(tok)
    wrap.add_eos_token("<|plamo:tag|>")

    def easy(text: str, glossary=None, max_tokens: int = 512) -> str:
        kw = {"glossary": glossary} if glossary else {}
        prompt = tok.apply_chat_template(
            [{"role": "user", "content": text}],
            target_lang="ja(easy)",
            add_generation_prompt=True,
            tokenize=False,
            **kw,
        )
        return generate(model, wrap, prompt=prompt, max_tokens=max_tokens, verbose=False)

    return easy


INLINE = {
    "strong", "em", "b", "i", "span", "a", "small", "sup", "sub", "mark", "time", "label",
}
# 文の途中で分断された断片の先頭に来る助詞・接続（前のノードの続きなので単独変換しない）
CONT_START = ("を", "が", "は", "に", "で", "と", "も", "へ", "や", "の", "から", "まで", "より", "であり")


def collect_nodes(raw: str):
    from bs4 import BeautifulSoup, NavigableString

    soup = BeautifulSoup(raw, "html.parser")
    out = []
    for s in soup.find_all(string=True):
        if not isinstance(s, NavigableString):
            continue
        if any(p.name in SKIP_TAGS for p in s.parents if getattr(p, "name", None)):
            continue
        text = str(s)
        if len(text.strip()) < 6 or not JP.search(text):
            continue
        # インライン要素に分断された短い断片は文脈がなく誤変換しやすい
        parent = getattr(s.parent, "name", None)
        if parent in INLINE and len(text.strip()) < 15:
            continue
        if text.strip().startswith(CONT_START):
            continue
        out.append(text)
    return out


def split_lead_trail(text: str):
    core = text.strip()
    lead = text[: len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    return lead, core, trail


def chunk(core: str, size: int = 250):
    parts, buf = [], ""
    for s in SENT.split(core):
        if not s:
            continue
        if buf and len(buf) + len(s) > size:
            parts.append(buf)
            buf = s
        else:
            buf += s
    if buf:
        parts.append(buf)
    return parts


def protected_tokens(text: str):
    toks = set(re.findall(r"`[^`]+`", text))
    toks |= set(re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)+", text))
    toks |= set(re.findall(r"[A-Za-z][A-Za-z0-9]*\(\)", text))
    return toks


def verify(src: str, out: str) -> str | None:
    """問題があれば理由を返す。None なら合格。"""
    if not out.strip():
        return "empty"
    if FORBIDDEN in out:
        return "special-token"
    src_nums = sorted(NUM.findall(src))
    out_nums = sorted(NUM.findall(out))
    if src_nums != out_nums:
        # 単一→1つ のように新しく立つ「1」だけは許す
        if not (sorted(src_nums + ["1"] * (len(out_nums) - len(src_nums))) == out_nums
                and len(out_nums) > len(src_nums)):
            return "numbers-changed"
    missing = protected_tokens(src) - set(protected_tokens(out))
    if missing:
        return f"code-changed:{sorted(missing)[:2]}"
    # 日本語が英語に化けた・原文にない英単語が増えた場合は戻す
    if JP.search(src) and not JP.search(out):
        return "lost-japanese"
    latin_src = set(re.findall(r"[A-Za-z]{3,}", src))
    if set(re.findall(r"[A-Za-z]{3,}", out)) - latin_src:
        return "new-latin"
    ratio = len(out) / max(len(src), 1)
    if not 0.5 <= ratio <= 2.2:
        return f"length-{ratio:.1f}x"
    # 短い見出し・ラベルを勝手に文へ変えない（事実の追加を防ぐ）
    src_s = src.strip()
    if len(src_s) <= 15 and not re.search(r"[。！？]", src_s):
        if re.search(r"(しました|します|です|でした|ます|ください|ません|でしょう)$", out.strip()):
            return "label-became-sentence"
    return None


def replace_sequential(raw: str, nodes, translated):
    """本文中のテキストを出現順に置換する。戻り値は (変換後, 未一致件数)。"""
    pos = 0
    unmatched = 0
    for original, new in zip(nodes, translated):
        idx = raw.find(original, pos)
        if idx < 0:
            esc = html_mod.escape(original, quote=False)
            idx = raw.find(esc, pos)
            if idx >= 0:
                original = esc
        if idx < 0:
            unmatched += 1
            continue
        raw = raw[:idx] + new + raw[idx + len(original):]
        pos = idx + len(new)
    return raw, unmatched


def main():
    ap = argparse.ArgumentParser(description="HTMLをやさしい日本語に変換する")
    ap.add_argument("file")
    ap.add_argument("--model", default="0.8b", choices=sorted(MODELS))
    ap.add_argument("--glossary", help="用語集JSON（[{\"source\":..,\"target\":..}]）")
    ap.add_argument("--out", help="出力先（既定: <name>.yasashii.html）")
    ap.add_argument("--limit", type=int, help="先頭N件だけ変換（試用）")
    ap.add_argument("--dry-run", action="store_true", help="対象件数だけ表示")
    args = ap.parse_args()

    src_path = Path(args.file).expanduser()
    if not src_path.exists():
        die(f"ファイルがありません: {src_path}")
    if src_path.name.endswith(".yasashii.html"):
        die("やさしい版を入力にしています")

    raw = src_path.read_text(encoding="utf-8")
    nodes = collect_nodes(raw)
    if args.limit:
        nodes = nodes[: args.limit]
    if not nodes:
        die("変換対象の日本語テキストがありません")
    if args.dry_run:
        print(json.dumps({"nodes": len(nodes), "chars": sum(len(n) for n in nodes)},
                         ensure_ascii=False))
        return

    glossary = None
    if args.glossary:
        glossary = json.loads(Path(args.glossary).expanduser().read_text(encoding="utf-8"))

    t0 = time.time()
    easy = load_engine(args.model)
    load_s = time.time() - t0

    translated, reverted = [], []
    t1 = time.time()
    for i, text in enumerate(nodes, 1):
        lead, core, trail = split_lead_trail(text)
        pieces = []
        for part in chunk(core):
            out = easy(part, glossary, max_tokens=max(96, min(2048, int(len(part) * 2.5))))
            reason = verify(part, out)
            if reason:
                reverted.append({"reason": reason, "src": part, "out": out.strip()})
                pieces.append(part)
            else:
                pieces.append(out.strip())
            if sys.stderr.isatty():
                print(f"\r  {i}/{len(nodes)}", end="", file=sys.stderr, flush=True)
        translated.append(lead + "".join(pieces) + trail)
    if sys.stderr.isatty():
        print("", file=sys.stderr)

    out_raw, unmatched = replace_sequential(raw, nodes, translated)
    out_path = Path(args.out).expanduser() if args.out else \
        src_path.with_name(src_path.name[:-5] + ".yasashii.html")
    out_path.write_text(out_raw, encoding="utf-8")

    elapsed = time.time() - t1
    chars = sum(len(n) for n in nodes)
    print(json.dumps({
        "input": str(src_path),
        "output": str(out_path),
        "model": args.model,
        "nodes": len(nodes),
        "chars": chars,
        "reverted": len(reverted),
        "unmatched": unmatched,
        "reverted_detail": reverted[:5],
        "load_s": round(load_s, 2),
        "convert_s": round(elapsed, 2),
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
