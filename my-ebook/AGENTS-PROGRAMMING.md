# Programming Books - Agent Guidelines

This file contains guidelines for when you're working on **programming/technical books**. For non-fiction books, refer to the main `AGENTS-BOOK.md` file.

---

You are writing a technical programming book, not source code documentation.

Primary goal:

- Explain concepts, motivations, trade-offs, and mental models clearly.
- Assume the reader learns by understanding, not by copying code.

Code policy:

- Code is illustrative, not authoritative.
- Avoid full implementations; show fragments only.

Explanations:

- Every code snippet must be preceded by an explanation of _why_ it exists.
- Every code snippet must be followed by a discussion of consequences, limits, or alternatives.

If unsure whether code is needed, prefer prose.

## Technical Programming Books

- **Audience**: Assume readers are beginners to intermediate programmers unless specified otherwise.
- **Content Style**:
  - Explain programming concepts clearly, starting with simple explanations before diving into technical details.
  - Use analogies or real-world examples to make complex topics accessible.
  - Break down code into small, digestible snippets with explanations for each part.
- **Code Standards**:
  - Include code examples in the programming language specified in the prompt (default to Python if unspecified).
  - Use consistent formatting: 4-space indentation, clear variable names (camelCase or snake_case based on language conventions).
  - Comment code to explain functionality, especially for beginners.
  - Ensure all code is syntactically correct and executable.
  - Avoid deprecated functions or outdated practices (e.g., use `f-strings` instead of `.format()` in Python).
- **Structure**:
  - Start each chapter with an overview of the topic and its relevance.
  - Include practical examples, exercises, or challenges at the end of sections to reinforce learning.
  - Use tables or lists to summarize key concepts, syntax, or comparisons (e.g., loops vs. conditionals).
- **Example Prompt Response**:
  - If asked to "write a section on Python loops," generate:
    - An introduction explaining loops and their purpose.
    - Code examples for `for` and `while` loops with comments.
    - A table comparing loop types.
    - A short exercise for readers to practice.
- **Language**: Write books primarily in English. Spanish may be used less commonly. Avoid other languages unless illustrating a specific concept.

## Code Style Guidelines

- **Java**: Use google-java-format for code blocks
- **C++**: Use clang-format with .clang-format config (4 spaces, 80 char limit)
- **Markdown**: Use prettier with embedded-language-formatting off
- **File naming**: Use kebab-case for markdown files (e.g., `01-introduction.md`)
- **Structure**: Each chapter in separate file, metadata in 00-metadata.yaml
