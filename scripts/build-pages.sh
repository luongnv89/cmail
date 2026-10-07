#!/usr/bin/env bash
# Run from the repository root. Never publish the whole repository or docs tree.
set -euo pipefail

if [[ -e _site || -L _site ]]; then
  printf '%s\n' 'Refusing to overwrite an existing _site; use a fresh staging directory.' >&2
  exit 1
fi

files=(index.html setup.html setup.md distribution.md assets/styles.css assets/checklist.js)
for file in "${files[@]}"; do
  if [[ ! -f "docs/$file" || -L "docs/$file" ]]; then
    printf 'Missing or symlinked public site input: %s\n' "$file" >&2
    exit 1
  fi
done
if [[ -L docs || -L docs/assets ]]; then
  printf '%s\n' 'Refusing symlinked site source directories.' >&2
  exit 1
fi

mkdir -p _site/assets
for file in "${files[@]}"; do
  cp "docs/$file" "_site/$file"
done
