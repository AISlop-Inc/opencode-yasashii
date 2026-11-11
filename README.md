# opencode-yasashii

An OpenCode skill that rewrites HTML deliverables into easy Japanese with a local
[PLaMo 3 Translate](https://huggingface.co/pfnet/plamo-3-translate-0.8b) model (MLX, Apple Silicon).

`report.html` → `report.yasashii.html`. The original is never modified.

```
yasashii report.html
```

## Why this exists

Reports are written for people who already know the domain. The same report is then
read by people who do not. This skill produces a second copy where the body text is
rewritten in easy Japanese, while code, numbers, tables, links and layout stay byte-identical.

It is a **reading aid**, not a replacement: the original stays the source of truth.

## How it works

- Translates only HTML text nodes, sentence by sentence (chunks of ~250 chars).
- Uses `target_lang="ja(easy)"`, an undocumented mode of PLaMo 3 Translate that
  rewrites Japanese into Japanese instead of translating to another language.
- Skips `<code>`, `<pre>`, `<script>`, `<style>`, `<svg>`, all attributes, inline
  fragments split by `<strong>`/`<a>` and sentence fragments that start with a particle.
- Reverts a sentence to the original when:
  - numbers changed (a newly introduced `1` from `単一` → `1つ` is allowed),
  - a code identifier or backticked string disappeared,
  - Japanese turned into English, or a new Latin word appeared,
  - the length ratio falls outside 0.5–2.2x,
  - a label of 15 chars or fewer became a sentence.
- Prints a JSON summary: nodes, chars, reverted sentences with reasons, unmatched positions.

## Install

```bash
git clone git@github.com:AISlop-Inc/opencode-yasashii.git
cd opencode-yasashii
./install.sh          # symlinks skills/yasashii into ~/.config/opencode/skills/yasashii
./install.sh --copy   # copies instead of symlinking
```

First run of the converter needs its Python environment:

```bash
bash ~/.config/opencode/skills/yasashii/setup.sh
```

This creates `~/.local/share/yasashii/venv` with `mlx-lm`, `transformers`, `numba`,
`numpy`, `beautifulsoup4` and `huggingface_hub`. Model weights download on first use.

## Usage

```bash
yasashii report.html
yasashii report.html --model 2b --glossary terms.json
yasashii report.html --limit 20      # try the first 20 sentences
yasashii report.html --dry-run       # count target sentences only
```

| Option | Meaning |
|---|---|
| `--model 0.8b` | Default. ~40s for a 10k-char report on M3 Pro |
| `--model 2b` | Keeps technical terms, fewer reverts, ~4 min for the same report |
| `--model 8b` | 6GB, not benchmarked here |
| `--glossary terms.json` | Fix terminology (see below) |
| `--out path.html` | Output path |
| `--limit N` | Convert only the first N sentences |
| `--dry-run` | Report counts without converting |

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

## Measured on a real report

9,800 characters / 265 sentences, Apple M3 Pro:

| Model | Weights | Time | Sentences reverted |
|---|---|---|---|
| 0.8b | 0.98GB | 37s | 6 |
| 2b | 2.42GB | 231s | 2 |

Tags, links and numbers were identical to the original in both runs.

0.8B stays close to the original sentence structure; 2B splits sentences and explains
more, but occasionally adds a claim that was not in the source. Both need a human read.

## Requirements

- Apple Silicon Mac (MLX), Python 3.12+
- ~1GB of disk per model, plus ~650MB for the venv

## License

Code: MIT.

Model: PLaMo 3 Translate is distributed under the
[PLaMo Community License](https://plamo.preferredai.jp/info/plamo-community-license-en).
Non-commercial use is free. Commercial use requires prior registration with Preferred
Networks and is limited to companies with annual revenue under 1 billion yen.
Weights are not redistributed here; they are downloaded from Hugging Face at runtime.
