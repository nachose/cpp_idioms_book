#!/usr/bin/env bash
set -euo pipefail

REPORT="spell_report.txt"
> "$REPORT" # clear previous report

found_errors=0

# Find all markdown files recursively
mapfile -d '' -t files < <(find . -path './.git' -prune -o -type f -name "*.md" -print0 | sort -z)

if [ ${#files[@]} -eq 0 ]; then
  echo "No Markdown files found." | tee -a "$REPORT"
  exit 0
fi

for f in "${files[@]}"; do
  echo "== $f ==" | tee -a "$REPORT"

  miss=$(aspell --mode=markdown --personal=.aspell.en.pws list < "$f" | sort | uniq -c | sort -nr)
  if [ -z "$miss" ]; then
    echo "  ✅ No misspellings found." | tee -a "$REPORT"
  else
    echo "$miss" | tee -a "$REPORT"
    found_errors=1
  fi

  echo "" >> "$REPORT"
done

if (( found_errors != 0 )); then
  echo "Spelling issues detected. See $REPORT for details." >&2
  exit 1
else
  echo "All Markdown files passed spell check." | tee -a "$REPORT"
fi
