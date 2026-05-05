#!/usr/bin/env bash
set -euo pipefail

PDF="$1"

if [[ -z "${PDF:-}" ]]; then
  echo "Usage: $0 book.pdf"
  exit 1
fi

if [[ ! -f "$PDF" ]]; then
  echo "ERROR: File not found: $PDF"
  exit 1
fi

echo "== Checking print readiness for: $PDF =="
echo

# -------------------------------------------------
# 1. Basic PDF info
# -------------------------------------------------
echo "-- PDF info --"
pdfinfo -- "$PDF"
echo

# -------------------------------------------------
# 2. Page size check (example: 6x9 inches)
# -------------------------------------------------
EXPECTED_WIDTH_PTS=442   # 6.19 in * 72
EXPECTED_HEIGHT_PTS=663  # 9.41 in * 72

PAGE_SIZE=$(pdfinfo "$PDF" | grep "Page size" | head -n1)
WIDTH=$(echo "$PAGE_SIZE" | awk '{print int($3)}')
HEIGHT=$(echo "$PAGE_SIZE" | awk '{print int($5)}')

if [[ "$WIDTH" -ne "$EXPECTED_WIDTH_PTS" || "$HEIGHT" -ne "$EXPECTED_HEIGHT_PTS" ]]; then
  echo "WARNING: Page size is ${WIDTH}x${HEIGHT} pts"
  echo "         Expected ${EXPECTED_WIDTH_PTS}x${EXPECTED_HEIGHT_PTS} pts (6x9 in)"
else
  echo "OK: Page size matches expected trim size (6x9 in)"
fi

echo

# -------------------------------------------------
# 3. Font embedding check
# -------------------------------------------------
echo "-- Font embedding --"
pdffonts_output=$(pdffonts "$PDF")
echo "$pdffonts_output"
echo

#The types column of pdffonts might have spaces, so it might be one or two columns
# so we need to check the colums starting from the last one, as that is stable
UNEMBEDDED=$(echo "$pdffonts_output" | awk 'NR>2 && $(NF-4)!="yes"')
TYPE3=$(echo "$pdffonts_output" | awk 'NR>2 && substr($0, 38, 17) ~ /Type3/')


if [[ -n "$UNEMBEDDED" ]] || [[ -n "$TYPE3" ]]; then
  if [[ -n "$UNEMBEDDED" ]]; then
    echo "ERROR: Unembedded fonts detected"
    echo "$UNEMBEDDED"
  fi
  if [[ -n "$TYPE3" ]]; then
    echo "ERROR: Type 3 fonts detected (bad for print)"
    echo "$TYPE3"
  fi
  exit 1
fi

echo "OK: All fonts embedded, no Type 3 fonts"
echo

# -------------------------------------------------
# 4. PDF/X preflight via Ghostscript
# -------------------------------------------------
echo "-- PDF/X preflight (Ghostscript) --"

TMP_PDF=$(mktemp --suffix=.pdf)
trap 'rm -f "$TMP_PDF"' EXIT

if ! gs -dSAFER -dBATCH -dNOPAUSE -sDEVICE=pdfwrite \
        -dPDFX \
        -sOutputFile="$TMP_PDF" \
        -- "$PDF" 2>&1; then
  echo "ERROR: Ghostscript PDF/X conversion failed"
  exit 1
fi
echo "OK: PDF/X preflight passed"
echo

# -------------------------------------------------
# 5. Color sanity (informational)
# -------------------------------------------------
echo "-- Color information --"
pdfinfo "$PDF" | grep -i color || echo "No explicit color info"
echo

# -------------------------------------------------
# Final verdict
# -------------------------------------------------
echo "========================================"
echo "PRINT PREFLIGHT PASSED"
echo "This PDF is structurally safe for KDP Print"
echo "========================================"

