#!/usr/bin/env python3
import re
import sys
from pathlib import Path

MAX_LINES = 1800


def extract_chapter_number(filename):
    match = re.search(r"(?:chapter_|^)(\d+)", filename)
    return match.group(1) if match else None


def get_section_level(line):
    if line.startswith("# "):
        return 1
    elif line.startswith("## "):
        return 2
    elif line.startswith("### "):
        return 3
    return 0


def split_chapter(filepath, max_lines=MAX_LINES):
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    filename = Path(filepath).stem
    chapter_num = extract_chapter_number(filepath.name)

    if not chapter_num:
        print(f"Could not extract chapter number from {filename}")
        return

    parts = []
    current_part = []

    for line in lines:
        level = get_section_level(line)

        if level in (1, 2) and current_part:
            if len(current_part) + 1 > max_lines:
                parts.append(current_part)
                current_part = [line]
            else:
                current_part.append(line)
        else:
            current_part.append(line)
    i = 0

    if current_part:
        parts.append(current_part)

    base_output = f"chapter_{chapter_num}"

    for idx, part in enumerate(parts):
        suffix = f"{idx + 1:02d}"
        output_name = f"{base_output}_{suffix}.md"
        output_path = filepath.parent / output_name

        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(part)

        line_count = len(part)
        print(f"Created {output_name} ({line_count} lines)")


def main():
    if len(sys.argv) < 2:
        print("Usage: python split_chapter.py <chapter_file> [max_lines]")
        sys.exit(1)

    filepath = Path(sys.argv[1])
    max_lines = int(sys.argv[2]) if len(sys.argv) > 2 else MAX_LINES

    if not filepath.exists():
        print(f"File not found: {filepath}")
        sys.exit(1)

    print(f"Splitting {filepath.name} (max {max_lines} lines per part)...\n")
    split_chapter(filepath, max_lines)


if __name__ == "__main__":
    main()
