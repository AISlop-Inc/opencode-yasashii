# opencode-yasashii

An OpenCode skill and CLI that finish Japanese prose in easy Japanese with a local
[PLaMo 3 Translate](https://huggingface.co/pfnet/plamo-3-translate-0.8b) model (MLX, Apple Silicon).

Use it for final replies, explanations, email drafts and document/slide prose
before rendering them. Existing text, Markdown and HTML files can also be rewritten.
The original file is never modified.

```
yasashii report.html
yasashii notes.md
yasashii message.txt
printf '当該機能を無効化する必要があります。' | yasashii
```

## Why this exists

Reports are written for people who already know the domain. The same report is then
read by people who do not. This skill produces a second copy where the body text is
rewritten in easy Japanese, while code, links, attributes and markup are protected.
Table prose may change; numerical literals and their units must be preserved.

It is a **reading aid**, not a replacement: the original stays the source of truth.

## How it works

- Shares one rewriting/validation pipeline across plain text, Markdown and HTML.
  stdin/stdout lets agents finish prose before putting it into any final format.
- Text files become `name.yasashii.txt`, Markdown becomes `name.yasashii.md`,
  and HTML becomes `name.yasashii.html`.
- Uses official PFML3 `target_lang="ja-easy"`, explicit `source_lang="ja"` and
  temperature-zero greedy decoding. This
  rewrites Japanese into Japanese instead of translating to another language.
- Uses HTMLParser source offsets, not text searching: repeated text in an
  attribute, comment or script cannot redirect an edit there.
- Skips links, code, scripts, styles, SVG, attributes, non-sentence labels,
  URL/path/backtick-containing nodes and continuations starting with particles.
- Markdown uses CommonMark parsing (`markdown-it-py`) and source offsets to keep
  fences, indented code, quotes, links, emphasis and embedded HTML intact.
  YAML front matter and pipe tables are also kept. Complex marked-up paragraphs
  are preserved rather than partially rewritten without context.
- Reverts a sentence to the original when:
  - numbers or units changed (including added `1`s),
  - a code identifier or backticked string disappeared,
  - Japanese turned into English, or a new Latin word appeared,
  - the length ratio falls outside 0.5–2.2x,
  - a label of 15 chars or fewer became a sentence,
  - a complete sentence was cut off without terminal punctuation.
- Preserves capitalized Latin names and reverts suspected loss of an explicit
  removal action (`除外` / `削除` / `落とし`). This is a conservative lexical check,
  not a general semantic validator.
- Prints a JSON summary: nodes, chars, reverted sentences with reasons, unmatched positions.

## Install

```bash
git clone git@github.com:AISlop-Inc/opencode-yasashii.git
cd opencode-yasashii
./install.sh          # links skills/yasashii into ~/.config/opencode/skills/yasashii
./install.sh --copy   # copies instead of symlinking
```

`install.sh` also links the `yasashii` command into `~/.local/bin`, so it can be
called from any shell.

First run of the converter needs its Python environment:

```bash
bash ~/.config/opencode/skills/yasashii/setup.sh
```

This creates `~/.local/share/yasashii/venv` with `mlx-lm`, `transformers`, `numba`,
`numpy`, `beautifulsoup4`, `markdown-it-py` and `huggingface_hub`.
Model weights download on first use.

## Usage

```bash
yasashii report.html
yasashii notes.md
yasashii message.txt
cat draft.md | yasashii --format markdown
yasashii draft.md --stdout
yasashii report.html --model 2b --glossary terms.json
yasashii report.html --context background.txt
yasashii report.html --limit 20      # try the first 20 sentences
yasashii report.html --dry-run       # count target sentences only
```

| Option | Meaning |
|---|---|
| `--model 0.8b` | Default. Small, fast; technical jargon often remains |
| `--model 2b` | Alternative; not automatically more faithful |
| `--model 8b` | 6GB, not benchmarked here |
| `--glossary terms.json` | Fix terminology (see below) |
| `--context background.txt` | Optional reference context; not enabled by default |
| `--format text/markdown/html` | Override detection; stdin defaults to text |
| `--stdout` | Return rewritten file content to stdout |
| `--out path` | Output path |
| `--limit N` | Convert only the first N sentences |
| `--dry-run` | Report counts without converting |

For stdin or `--stdout`, stdout contains only the rewritten document and stderr
contains diagnostics. If no eligible prose exists, the input passes through unchanged
without loading the model. Unknown file extensions are refused, not silently treated
as text. JSON/config/code files are not prose.

### Other deliverables and agent replies

Use the `yasashii` skill before finalizing Japanese replies, Markdown, email drafts,
document text or slide text. Compare the proposed rewrite with the original for
changed actors, negation, conditions or certainty, then use the accepted wording
in the target authoring tool. Do not display both drafts in every chat reply.

This is a shared finishing workflow, not an OpenCode hook that silently intercepts
every message. PDF, DOCX and PPTX binaries are not edited directly: rewrite the prose
before rendering them, or use their format-aware authoring tools.
Exact quotations and complex Markdown blocks may intentionally remain unchanged.

## Glossary

Pass a JSON list to lock terminology. The model uses it as context, so inflections
and particles are still handled:

```json
[
  {"source": "オーバーヘッド", "target": "余分にかかる時間"},
  {"source": "レイテンシ", "target": "応答時間"}
]
```

Without a glossary the 0.8B model leaves katakana loanwords untouched, and can mistranslate
technical terms (`埋め込みベクトル` → `埋め込まれたベクトル`).

## Measured results (2026-11-11)

18 diagnostic inputs (13 prose, 2 labels, 3 protected inputs), Apple M3 Pro,
three sequential sweeps per variant. Times are medians, excluding model loading.
The safer variants rewrite 13 inputs; the others are intentionally preserved.

| Model / variant | Time | Observed language outcome |
|---|---|---|
| 0.8b / safer default | 1.135s | Keeps embedding terminology, jargon remains |
| 0.8b / glossary | 1.466s | Rewrites all four selected technical terms |
| 2b / safer default | 6.378s | Confuses latency with availability in one example |
| 2b / glossary | 7.869s | Fixes that example; embedding jargon remains |
| 2b / glossary + context | 8.365s | That latency error returns |

All 18 inputs preserve numeric literals; outputs match across all three repeats.
These checks are not an overall meaning-accuracy score or a reader study.

A separate end-to-end report run (one run each, 71,912 input bytes):

| Variant | Candidate nodes | Time | Protected elements / numbers preserved |
|---|---|---|---|
| Old CLI (`0038c01`) | 265 | 32.536s | No / No |
| Safer default | 135 | 19.429s | Yes / Yes |
| Safer + glossary | 135 | 21.532s | Yes / Yes |

The safer selection processes 6,099 chars vs the old 9,799: the lower runtime
does **not** establish faster inference. Safety is gained partly by preserving
more source text. The old run rewrote a title and an anchor and introduced two
extra `1`s; earlier informal preservation claims were incomplete.
An adversarial repeated-text HTML suite passes 1/8 old vs 8/8 new.
The current suite has 21 passing unit tests, including stdin/stdout, Markdown
protection and original-file preservation. Semantic changes beyond lexical
checks still require review.

## Accuracy regression benchmark

```bash
python -m unittest discover -s tests -v
python bench/safety.py
python bench/run.py --model 0.8b --output /mounted-storage/0.8b.json
python bench/run.py --model 2b --output /mounted-storage/2b.json
python bench/report.py report.html --output-dir /mounted-storage/report-bench
python bench/formats.py --output-dir /mounted-storage/formats-bench
```

Use the Python environment created by `setup.sh`.
The benchmark freezes the old implementation at commit `0038c01`.
It compares the old language-code path, explicit source/target, conservative HTML
selection, glossary, context, and glossary+context on 18 diagnostic examples.
Safety, numeric preservation, rewrite coverage and observed semantic errors are
separate measures: an unchanged sentence is safe, but not a simplification.
Glossaries help technical vocabulary; context+glossary can still make a sentence
worse. Neither is a hard constraint or an automatic guarantee of meaning.

The format benchmark checks the same four prose inputs in text, Markdown and HTML
three times each. All three produce the same rewritten prose; numeric literals
and the Markdown code/quote/link/table fixture are preserved. This verifies shared
processing and format protection, not general language accuracy.

### Why these changes

- [Official MLX chat template](https://huggingface.co/pfnet/plamo-3-translate-2b-MLX-4bit/blob/main/chat_template.jinja)
  normalizes `ja(easy)` to PFML3 `ja-easy`. The older mixed34 template did not,
  so using the canonical code avoids relying on the alias implementation.
- [Official MLX model card](https://huggingface.co/pfnet/plamo-3-translate-2b-MLX-4bit)
  documents glossary and reference context, and uses temperature-zero sampling.
  They are translation inputs, not hard fidelity constraints.
- [Japanese simplification research (Urakawa et al., 2024)](https://aclanthology.org/2024.lrec-main.57/)
  and [READI 2024](https://aclanthology.org/2024.readi-1.1/) motivate inspecting
  additions/omissions and evaluating simplicity separately from meaning.

Larger models, more context and a larger glossary are not automatically better.
Use a short, reviewed glossary; inspect negation, conditions, actions and uncertainty.

## Requirements

- Apple Silicon Mac (MLX), Python 3.12+
- Weights: ~423MB (0.8b), ~2.4GB (2b), ~6GB (8b), plus the Python environment

## License

Code: MIT.

Model: PLaMo 3 Translate is distributed under the
[PLaMo Community License](https://plamo.preferredai.jp/info/plamo-community-license-en).
Non-commercial use is free. Commercial use requires prior registration with Preferred
Networks and is limited to companies with annual revenue under 1 billion yen.
Weights are not redistributed here; they are downloaded from Hugging Face at runtime.
