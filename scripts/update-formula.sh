#!/usr/bin/env bash
# Point the Homebrew formula at a published tag: rewrite its url and sha256.
# Usage: scripts/update-formula.sh vX.Y.Z [formula]
# The tag must already exist on GitHub; its source archive is hashed as Homebrew will.
set -euo pipefail
tag="${1:-}"
formula="${2:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/packaging/homebrew/cmail.rb}"
printf '%s\n' "$tag" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+$' || { printf 'usage: %s vX.Y.Z [formula]\n' "$0" >&2; exit 2; }
[ -f "$formula" ] || { printf 'formula not found: %s\n' "$formula" >&2; exit 1; }
url="https://github.com/luongnv89/cmail/archive/refs/tags/$tag.tar.gz"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' -o "$tmp" "$url" \
  || { printf 'could not download %s; push the tag first\n' "$url" >&2; exit 1; }
if command -v sha256sum >/dev/null; then sum="$(sha256sum "$tmp" | cut -d' ' -f1)"; else sum="$(shasum -a 256 "$tmp" | cut -d' ' -f1)"; fi
out="$(mktemp "$formula.XXXXXX")"
sed -e "s|^  url \".*\"$|  url \"$url\"|" -e "s|^  sha256 \".*\"$|  sha256 \"$sum\"|" "$formula" > "$out"
mv -f "$out" "$formula"
printf 'Updated %s\n  url    %s\n  sha256 %s\n' "$formula" "$url" "$sum"
