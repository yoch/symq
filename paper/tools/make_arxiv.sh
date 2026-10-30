#!/usr/bin/env bash
# Build a LOCAL source bundle. This script never uploads, submits or announces it.
# A compiled package establishes neither author consent nor scientific readiness.
set -euo pipefail
cd "$(dirname "$0")/.."
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex >/dev/null
mkdir -p arxiv
staging=$(mktemp -d arxiv/build-XXXXXX)
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/src/tables" "$staging/src/qualification"
cp main.tex main.bbl references.bib "$staging/src/"
cp tables/numbers.tex "$staging/src/tables/"
cp qualification/*.tex qualification/*.pdf "$staging/src/qualification/"
if grep -q '\\today' "$staging/src/main.tex"; then
  echo "\\today in main.tex" >&2
  exit 1
fi
if find "$staging/src" -name '.*' -o -name '*[^A-Za-z0-9_+.,=/-]*' | grep -q .; then
  echo "unsupported source-bundle file name" >&2
  exit 1
fi
(cd "$staging/src" && pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null \
  && pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null \
  && rm -f main.aux main.log main.out main.pdf)
tar -czf arxiv/symq-paper-arxiv.tar.gz -C "$staging/src" .
printf '%s\n' 'Local draft source bundle: paper/arxiv/symq-paper-arxiv.tar.gz'
printf '%s\n' 'Not submitted; external publication and authorship/licensing approval remain separate.'
tar -tzf arxiv/symq-paper-arxiv.tar.gz
