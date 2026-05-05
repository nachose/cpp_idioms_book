# book_template

This is a robust template for writing and generating technical programming and non-fiction books using Markdown and Pandoc, with a strong emphasis on a containerized (Docker-first) build process. It includes syntax-highlighted code, automated quality checks, and CI/CD integration for EPUB, PDF, and DOCX outputs.

---

# **Your Complete Guide: Markdown + Pandoc for Technical eBooks (Docker-First Approach)**

---

## 1. Project Structure

The core content of your book resides in the `my-ebook/` directory:

```
my-ebook/
  00-metadata.yaml       # Book metadata (title, author, language, etc.)
  01-introduction.md     # Your first chapter
  02-getting-started.md  # Another chapter
  03-advanced-topics.md  # And so on...
  cover.png              # Optional (for EPUB/Kindle covers)
  Makefile               # Automates the build process
  epub-fix.css           # Custom CSS for EPUB
  ... (other build-related files)
```

Your Markdown files (e.g., `01-introduction.md`) should use standard Markdown:
- `#` for chapters
- `##` for sections
- Triple backticks + language name for syntax-highlighted code.

## 2. Write Your Book Content

Create and edit your `.md` files within the `my-ebook/` directory.

### Example: `my-ebook/01-introduction.md`

```markdown
# Introduction

Welcome to **My Programming Book**.

In this book, you'll learn how to write code like a pro.

## Example Code

```java
public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
```

## 3. Configure Book Metadata (`my-ebook/00-metadata.yaml`)

Edit this file to define your book's properties:

```yaml
title: "My Programming Book"
author: "Nacho"
language: "en"
cover-image: cover.png    # Optional: provide a 1600x2560 cover if you want
rights: "© 2025 Nacho"
```

---

## 4. Build Your Book with Docker Compose

This project uses Docker Compose to provide a consistent and isolated build environment. You do **not** need to install Pandoc, LaTeX, or other dependencies directly on your machine.

From the project root directory (where `docker-compose.yml` is located), use the `make` commands within the `my-ebook` directory via Docker Compose:

### Build EPUB:

```bash
docker compose run book-builder-epub
# Or, if you prefer using make directly within the container context:
# docker compose run book-builder-epub make epub
```

### Build PDF:

```bash
docker compose run book-builder-pdf
# Or:
# docker compose run book-builder-pdf make pdf
```

### Build DOCX:

```bash
docker compose run book-builder-docx
# Or:
# docker compose run book-builder-docx make docx
```

The generated book files (e.g., `my-programming-book.epub`, `my-programming-book.pdf`, `my-programming-book.docx`) will be located in the `my-ebook/make_output` directory after a successful build.

---

## 5. Convert EPUB to Kindle (Optional)

To distribute to Kindle readers:

1.  **Install Kindle Previewer** (free, Windows/Mac).
2.  Open your generated `.epub` file in Kindle Previewer. It will auto-convert to **KPF** (Kindle Publishing Format).
3.  Alternatively, use **Calibre** to convert to **MOBI/AZW3**.

---

## 6. Automated Formatting and Quality Checks

This template includes automated tools to ensure consistent code style and book quality:

*   **`prettier`**: Formats Markdown files for consistent style.
*   **`google-java-format`, `clang-format`**: Ensures code blocks for Java and C/C++ are consistently formatted.
*   **`mermaid-cli`**: Generates images from Mermaid diagrams.
*   **`epubcheck`**: Validates EPUB files against industry standards (integrated into GitHub Actions).
*   **`pdfinfo`**: Provides details about PDF files (integrated into GitHub Actions).

---

## 7. Continuous Integration (CI)

The `.github/workflows/build-epub.yml` file sets up GitHub Actions to automatically build and validate your book formats (EPUB, PDF, DOCX) whenever changes are pushed or manually triggered. This ensures that your book always builds correctly and meets quality standards.