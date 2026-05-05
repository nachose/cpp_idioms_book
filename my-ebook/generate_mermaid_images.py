#!/usr/bin/env python3
import re
import subprocess
import tempfile
from pathlib import Path

# Directory containing markdown files
MD_DIR = Path(".")
# Directory to store generated images
IMAGES_DIR = Path("images")
# Puppeteer configuration for Docker containers
PUPPETEER_CONFIG = Path("puppeteer-config.json")
# Ensure images directory exists
IMAGES_DIR.mkdir(exist_ok=True)


def extract_and_replace_mermaid(content, filename):
    """
    Extract mermaid code blocks, generate images, and replace them with image references.
    Returns modified content and list of generated images.
    """
    pattern = r"```mermaid\n(.*?)\n```"
    matches = re.findall(pattern, content, re.DOTALL)

    if not matches:
        return content, []

    generated_images = []
    diagram_counter = 1

    for match in matches:
        mermaid_code = match

        # Generate a filename based on the source file and diagram number
        base_name = Path(filename).stem
        if base_name == "." or ".." in base_name or "/" in base_name:
            print(f"Skipping file with invalid name: {filename}")
            return content, []
        image_filename = f"{base_name}_mermaid_{diagram_counter:02d}.png"
        image_path = IMAGES_DIR / image_filename

        # Write mermaid code to temporary file

        temp_mmd = Path(tempfile.NamedTemporaryFile(suffix=".mmd", delete=False).name)
        temp_mmd.write_text(mermaid_code)

        # Generate image using mmdc
        try:
            cmd = ["mmdc", "-i", str(temp_mmd), "-o", str(image_path), "-t", "default"]
            if PUPPETEER_CONFIG.exists():
                cmd.extend(["-p", str(PUPPETEER_CONFIG)])
            else:
                puppeteer_config = Path("puppeteer-config.json")
                puppeteer_config.write_text(
                    '{"args": ["--no-sandbox", "--disable-setuid-sandbox"]}'
                )
                cmd.extend(["-p", str(puppeteer_config)])
            subprocess.run(cmd, check=True, capture_output=True)
            generated_images.append(str(image_path))
            print(f"Generated: {image_path}")
        except subprocess.CalledProcessError as e:
            print(f"Error generating {image_path}: {e}")
            print(f"stderr: {e.stderr.decode()}")
            raise SystemExit(1)
        # finally:
        #     temp_mmd.unlink()

        diagram_counter += 1

    # Replace all mermaid blocks with image references
    image_path_iterator = iter(generated_images)

    def replace_with_image(match):
        image_path = next(image_path_iterator)
        return f"!['Image']({image_path})"

    modified_content = re.sub(pattern, replace_with_image, content, flags=re.DOTALL)

    return modified_content, generated_images


def process_markdown_files():
    """Process all markdown files in the current directory."""
    md_files = list(MD_DIR.glob("*.md"))

    all_generated_images = []

    for md_file in md_files:
        if md_file.name.startswith("00-"):
            continue  # Skip metadata files

        print(f"Processing: {md_file.name}")

        content = md_file.read_text()

        # Check if file contains mermaid
        if "```mermaid" not in content:
            print("  No mermaid diagrams found")
            continue

        modified_content, images = extract_and_replace_mermaid(content, md_file.name)

        if images:
            # Write modified content back to file
            md_file.write_text(modified_content)
            print(f"  Generated {len(images)} image(s)")
            all_generated_images.extend(images)
        else:
            print("  No images generated")

    print(f"\nTotal images generated: {len(all_generated_images)}")
    return all_generated_images


if __name__ == "__main__":
    process_markdown_files()
