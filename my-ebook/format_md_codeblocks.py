#!/bin/python3

import re
import subprocess
import sys
from pathlib import Path

def format_code(code, language):
    if language in ["cpp", "c++"]:
        try:
            p = subprocess.run(["clang-format"], input=code.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return p.stdout.decode()
        except subprocess.CalledProcessError as e:
            print("clang-format error:", e.stderr.decode(), file=sys.stderr)
            return code
    elif language in ["java"]:
        try:
            p = subprocess.run(["google-java-format", "-"], input=code.encode(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            return p.stdout.decode()
        except subprocess.CalledProcessError as e:
            print("google-java-format error:", e.stderr.decode(), file=sys.stderr)
            return code
    # Add more languages here as needed
    return code

def process_file(filepath):
    text = Path(filepath).read_text(encoding='utf-8')

    def replacer(match):
        comment = match.group(1)
        lang = match.group(2)
        code = match.group(3)
        formatted_code = format_code(code, lang)
        if comment:
            # Preserve the existing comment and whitespace
            return f"{comment}```{lang}\n{formatted_code}```"
        else:
            # Add the comment
            return f"<!-- prettier-ignore -->\n```{lang}\n{formatted_code}```"

    # Optional group for the prettier-ignore comment allows us to match blocks
    # with or without the comment.
    # Group 1: The optional comment, including surrounding whitespace and newline.
    # Group 2: The language identifier.
    # Group 3: The code block content.
    new_text = re.sub(
        r'(<!--\s*prettier-ignore\s*-->\s*\n)?```(\w+)\n(.*?)```',
        replacer,
        text,
        flags=re.DOTALL
    )

    Path(filepath).write_text(new_text, encoding='utf-8')
    print(f"Formatted code blocks in: {filepath}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python format_md_codeblocks.py yourfile.md")
        sys.exit(1)
    process_file(sys.argv[1])

