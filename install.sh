#!/usr/bin/env bash
# Install the yasashii skill into the OpenCode skills directory.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/skills/yasashii"
DEST="$(cd "${OPENCODE_SKILLS:-$HOME/.config/opencode/skills}" 2>/dev/null && pwd || echo "${OPENCODE_SKILLS:-$HOME/.config/opencode/skills}")/yasashii"
MODE="link"

case "${1:-}" in
  --copy) MODE="copy" ;;
  --link|"") ;;
  *) echo "usage: $0 [--link|--copy]" >&2; exit 1 ;;
esac

mkdir -p "$(dirname "$DEST")"

if [ -L "$DEST" ]; then
  current="$(readlink "$DEST")"
  if [ "$current" != "$SRC" ]; then
    rm "$DEST"
  else
    echo "スキルは導入済み: $DEST"
  fi
elif [ -e "$DEST" ]; then
  backup="$DEST.bak-$(date +%Y%m%d%H%M%S)"
  mv "$DEST" "$backup"
  echo "既存のスキルを退避: $backup"
fi

if [ ! -e "$DEST" ]; then
  if [ "$MODE" = "copy" ]; then
    cp -R "$SRC" "$DEST"
    echo "コピーしました: $DEST"
  else
    ln -s "$SRC" "$DEST"
    echo "リンクしました: $DEST -> $SRC"
  fi
fi

chmod +x "$DEST/bin/yasashii" "$DEST/bin/yasashii.py" "$DEST/setup.sh"

# どこからでも yasashii を呼べるようにする
BINDIR="${YASASHII_BINDIR:-$HOME/.local/bin}"
if mkdir -p "$BINDIR" 2>/dev/null; then
  ln -sfn "$DEST/bin/yasashii" "$BINDIR/yasashii"
  echo "コマンドを配置: $BINDIR/yasashii"
  case ":$PATH:" in
    *":$BINDIR:"*) ;;
    *) echo "注意: $BINDIR が PATH にありません" ;;
  esac
fi

echo "初回のみ: bash $DEST/setup.sh"
