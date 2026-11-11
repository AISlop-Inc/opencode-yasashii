#!/usr/bin/env bash
# yasashii の実行環境を作る（初回のみ）
set -euo pipefail

ROOT="${YASASHII_HOME:-$HOME/.local/share/yasashii}"
mkdir -p "$ROOT"

if [ ! -x "$ROOT/venv/bin/python" ]; then
  echo "venv を作成: $ROOT/venv"
  python3 -m venv "$ROOT/venv"
fi

"$ROOT/venv/bin/pip" install -q -U pip
"$ROOT/venv/bin/pip" install -q -U mlx-lm transformers numba numpy beautifulsoup4 huggingface_hub

echo "完了: $ROOT/venv"
echo "試す: $(cd "$(dirname "$0")" && pwd)/bin/yasashii --help"
