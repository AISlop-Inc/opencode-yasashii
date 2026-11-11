#!/usr/bin/env python3
"""文章共通のやさしい日本語コンバータ。

PLaMo 3 Translate の target_lang="ja-easy" で、文章を言い換えて検査する。
テキスト・Markdown・HTMLの保護対象を残し、ファイルは別名で併産する。
標準入力では、変換した文章を標準出力に返す。

使い方:
    yasashii report.html
    yasashii report.html --model 2b --glossary terms.json
"""

from __future__ import annotations

import argparse
import html as html_mod
import importlib.util
import json
import re
import sys
import time
from html.parser import HTMLParser
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
    from mlx_lm.sample_utils import make_sampler

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
    wrap.add_eos_token("<|plamo:bos|>")

    def easy(text: str, glossary=None, max_tokens: int = 512, context=None,
             target="ja-easy", source="ja") -> str:
        kw = {"glossary": glossary} if glossary else {}
        if context:
            kw["context"] = context
        if source:
            kw["source_lang"] = source
        prompt = tok.apply_chat_template(
            [{"role": "user", "content": text}],
            target_lang=target,
            add_generation_prompt=True,
            tokenize=False,
            **kw,
        )
        return generate(model, wrap, prompt=prompt, max_tokens=max_tokens, verbose=False,
                        sampler=make_sampler(temp=0))

    return easy


# 文の途中で分断された断片の先頭に来る助詞・接続（前のノードの続きなので単独変換しない）
CONT_START = ("を", "が", "は", "に", "で", "と", "も", "へ", "や", "の", "から", "まで", "より", "であり")


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
    toks |= set(re.findall(r"(?<![A-Za-z0-9])[A-Z][A-Za-z0-9-]*(?![A-Za-z0-9])", text))
    toks |= set(re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)+", text))
    toks |= set(re.findall(r"[A-Za-z][A-Za-z0-9]*\(\)", text))
    return toks


def verify(src: str, out: str) -> str | None:
    """問題があれば理由を返す。None なら合格。"""
    if not out.strip():
        return "empty"
    if FORBIDDEN in out:
        return "special-token"
    if src.endswith(("。", "！", "？")) and not out.strip().endswith(("。", "！", "？")):
        return "incomplete-sentence"
    if sorted(NUM.findall(src)) != sorted(NUM.findall(out)):
        return "numbers-changed"
    quantities = r"\d+(?:[.,]\d+)*\s*(?:ms|[kMGT]?B|秒|分|時間|日|回|件|%|％)"
    if sorted(re.findall(quantities, src)) != sorted(re.findall(quantities, out)):
        return "units-changed"
    # 「出力を落とす→出力を取る」で除外が取得に反転した実例を保守的に戻す。
    if re.search(r"除外|削除|取り除|落とし", src) and not re.search(
            r"除外|削除|取り除|除い|除き|消し|削っ|外し|落と", out):
        return "removal-action-lost"
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


class TextSpans(HTMLParser):
    """Keep source offsets; never search for text inside tags or protected content."""

    def __init__(self, raw):
        super().__init__(convert_charrefs=False)
        self.starts = [0]
        for m in re.finditer("\n", raw):
            self.starts.append(m.end())
        self.stack = []
        self.spans = []
        self.feed(raw)

    def handle_starttag(self, tag, attrs):
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input",
                       "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.stack:
            self.stack = self.stack[:len(self.stack) - 1 - self.stack[::-1].index(tag)]

    def handle_data(self, data):
        line, col = self.getpos()
        start = self.starts[line - 1] + col
        if any(t in SKIP_TAGS | {"a"} for t in self.stack):
            return
        # Only complete sentences are rewritten. Fragment rewriting loses referents.
        text = data.strip()
        if len(text) < 6 or not JP.search(text) or not text.endswith(("。", "！", "？")):
            return
        if text.startswith(CONT_START):
            return
        if re.search(r"https?://|(?:~|/)[\w./-]+|`", text):
            return
        self.spans.append((start, start + len(data), data))


def prose_spans(raw, markdown=False):
    """Select complete prose lines, keeping document syntax outside edit ranges."""
    lines = raw.splitlines(keepends=True)
    allowed = set(range(len(lines)))
    if markdown:
        from markdown_it import MarkdownIt

        allowed = set()
        ancestors = []
        for token in MarkdownIt("commonmark").parse(raw):
            if token.nesting == -1:
                ancestors.pop()
            if token.type == "inline" and token.map and "blockquote_open" not in ancestors:
                if all(c.type in {"text", "softbreak"} for c in token.children or []):
                    allowed.update(range(*token.map))
            if token.nesting == 1:
                ancestors.append(token.type)
        # CommonMark has no YAML front matter; don't mistake metadata for prose.
        if lines and lines[0].strip() == "---":
            for i, line in enumerate(lines[1:], 1):
                allowed.discard(i)
                if line.strip() in {"---", "..."}:
                    break
            allowed.discard(0)
    spans, offset = [], 0
    fence = None
    for i, line in enumerate(lines):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            value = marker.group(1)
            if fence is None:
                fence = value
            elif value[0] == fence[0] and len(value) >= len(fence):
                fence = None
            offset += len(line)
            continue
        if fence is not None:
            offset += len(line)
            continue
        prefix = re.match(r"^[ \t]*(?:(?:#{1,6}|[-+*]|\d+[.)])[ \t]+)?", line).end()
        content = line[prefix:].rstrip("\r\n")
        text = content.strip()
        protected = re.search(r'https?://|(?:~|/)[\w./-]+|[`<>\\「『]|"[^"]+"', content)
        if markdown and "|" in content:
            protected = True
        if (i in allowed and len(text) >= 6 and JP.search(text)
                and text.endswith(("。", "！", "？"))
                and not text.startswith(CONT_START + (">", "「", "『", '"'))
                and not protected):
            spans.append((offset + prefix, offset + prefix + len(content), content))
        offset += len(line)
    return spans


def document_spans(raw, format):
    if format == "html":
        return TextSpans(raw).spans
    return prose_spans(raw, markdown=format == "markdown")


def convert_document(raw, easy, glossary=None, limit=None, context=None, format="text"):
    spans = document_spans(raw, format)
    if limit is not None:
        spans = spans[:limit]
    edits, reverted = [], []
    for start, end, text in spans:
        lead, core, trail = split_lead_trail(text)
        parts = []
        for part in chunk(core):
            out = easy(part, glossary, max_tokens=max(96, min(2048, int(len(part) * 2.5))),
                       context=context).strip()
            reason = verify(part, out)
            if format == "markdown" and not reason:
                from markdown_it import MarkdownIt

                tokens = MarkdownIt("commonmark").parse(out)
                if ("\n" in out or "\r" in out
                        or [t.type for t in tokens] != ["paragraph_open", "inline", "paragraph_close"]
                        or any(c.type != "text" for t in tokens for c in t.children or [])):
                    reason = "markdown-changed"
            if reason:
                reverted.append({"reason": reason, "src": part, "out": out})
            parts.append(part if reason else out)
        rewritten = "".join(parts)
        if format == "html":
            rewritten = html_mod.escape(rewritten, quote=False)
        edits.append((start, end, lead + rewritten + trail))
    for start, end, replacement in reversed(edits):
        raw = raw[:start] + replacement + raw[end:]
    return raw, {
        "nodes": len(spans), "chars": sum(len(t) for _, _, t in spans),
        "reverted": len(reverted), "unmatched": 0, "reverted_detail": reverted[:5],
    }


def convert_html(raw, easy, glossary=None, limit=None, context=None):
    return convert_document(raw, easy, glossary, limit, context, format="html")


def main():
    ap = argparse.ArgumentParser(description="文章・Markdown・HTMLをやさしい日本語に変換する")
    ap.add_argument("file", nargs="?", default="-", help="入力ファイル。省略または - で標準入力")
    ap.add_argument("--format", choices=["text", "markdown", "html"], help="省略時は拡張子で判定。標準入力はtext")
    ap.add_argument("--stdout", action="store_true", help="変換した文章を標準出力に返す")
    ap.add_argument("--model", default="0.8b", choices=sorted(MODELS))
    ap.add_argument("--glossary", help="用語集JSON（[{\"source\":..,\"target\":..}]）")
    ap.add_argument("--out", help="出力先（既定: <name>.yasashii.<元の拡張子>）")
    ap.add_argument("--limit", type=int, help="先頭N件だけ変換（試用）")
    ap.add_argument("--dry-run", action="store_true", help="対象件数だけ表示")
    ap.add_argument("--context", help="用語や背景の参照テキスト（指示文ではない）")
    args = ap.parse_args()

    if args.stdout and args.out:
        ap.error("--stdout と --out は同時に指定できません")
    if args.limit is not None and args.limit < 0:
        ap.error("--limit は0以上で指定してください")
    src_path = Path(args.file).expanduser() if args.file != "-" else None
    formats = {".html": "html", ".htm": "html", ".md": "markdown",
               ".markdown": "markdown", ".txt": "text", ".text": "text"}
    format = args.format or (formats.get(src_path.suffix.lower()) if src_path else "text")
    if format is None:
        die("未対応の拡張子です。文章なら --format text を指定してください")
    if src_path and ".yasashii" in src_path.stem:
        die("やさしい版を入力にしています")
    stream = args.stdout or (src_path is None and args.out is None)
    out_path = Path(args.out).expanduser() if args.out else (
        src_path.with_name(src_path.stem + ".yasashii" + src_path.suffix) if src_path and not stream else None)
    if src_path and out_path and out_path.resolve() == src_path.resolve():
        die("出力先に原文は指定できません")

    raw = src_path.read_text(encoding="utf-8") if src_path else sys.stdin.read()
    nodes = [text for _, _, text in document_spans(raw, format)]
    if args.limit is not None:
        nodes = nodes[: args.limit]
    if args.dry_run:
        print(json.dumps({"nodes": len(nodes), "chars": sum(len(n) for n in nodes)},
                         ensure_ascii=False))
        return

    glossary = None
    if args.glossary:
        glossary = json.loads(Path(args.glossary).expanduser().read_text(encoding="utf-8"))

    t0 = time.time()
    easy = load_engine(args.model) if nodes else None
    load_s = time.time() - t0

    t1 = time.time()
    context = Path(args.context).expanduser().read_text(encoding="utf-8") if args.context else None
    out_raw, stats = convert_document(raw, easy, glossary, args.limit, context, format)
    if stream:
        sys.stdout.write(out_raw)
    else:
        out_path.write_text(out_raw, encoding="utf-8")

    elapsed = time.time() - t1
    print(json.dumps({
        "input": str(src_path) if src_path else "-",
        "output": "-" if stream else str(out_path),
        "format": format,
        "model": args.model,
        **stats,
        "load_s": round(load_s, 2),
        "convert_s": round(elapsed, 2),
    }, ensure_ascii=False, indent=1), file=sys.stderr if stream else sys.stdout)


if __name__ == "__main__":
    main()
