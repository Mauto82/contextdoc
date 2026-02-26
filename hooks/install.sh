#!/usr/bin/env bash
#
# Installs ConceptDoc git hooks into the current repository.
# Run from the root of the project where you want to use ConceptDoc.
#
# Usage: bash /path/to/concept-doc/hooks/install.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GIT_HOOKS_DIR="$(git rev-parse --git-dir 2>/dev/null)/hooks"

if [[ -z "$GIT_HOOKS_DIR" ]]; then
  echo "Error: not inside a git repository."
  exit 1
fi

# Install pre-commit hook
TARGET="$GIT_HOOKS_DIR/pre-commit"

if [[ -f "$TARGET" ]]; then
  echo "A pre-commit hook already exists at $TARGET"
  read -r -p "Overwrite? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
  fi
fi

cp "$SCRIPT_DIR/pre-commit" "$TARGET"
chmod +x "$TARGET"

echo "✓ ConceptDoc pre-commit hook installed at $TARGET"
echo ""
echo "The hook will warn (not block) when source files are committed"
echo "without updating their .cdoc companions."
