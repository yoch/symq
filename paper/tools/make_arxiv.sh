#!/usr/bin/env bash
# Build the arXiv source package of the paper: TeX sources, generated tables, PDF figures and
# the BibTeX output (main.bbl). Run from anywhere; output in paper/arxiv/ (not committed).
set -euo pipefail
cd "$(dirname "$0")/.."
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
bibtex main >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
rm -rf arxiv && mkdir -p arxiv/src/tables arxiv/src/figures
cp main.tex main.bbl blind_text.tex arxiv/src/
cp tables/*.tex arxiv/src/tables/
cp figures/*.pdf arxiv/src/figures/
if grep -q '\\today' arxiv/src/main.tex; then echo "\\today in main.tex" >&2; exit 1; fi
if find arxiv/src -name '.*' -o -name '*[^A-Za-z0-9_+.,=/-]*' | grep -q .; then
  echo "file names not accepted by arXiv" >&2; exit 1
fi
(cd arxiv/src && pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null \
  && pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null \
  && rm -f main.aux main.log main.out main.pdf)
tar -czf arxiv/symq-paper-arxiv.tar.gz -C arxiv/src .
echo "paper/arxiv/symq-paper-arxiv.tar.gz"
tar -tzf arxiv/symq-paper-arxiv.tar.gz
