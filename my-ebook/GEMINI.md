# GEMINI.md for Book Writing Projects

This file provides instructions for Gemini CLI to assist in writing technical programming and non-fiction books in English. Follow these guidelines to ensure consistent, high-quality content generation.

## General Writing Guidelines

- Write all content in clear, concise, and professional **American English**.
- Use a **formal but approachable tone** suitable for book readers.
- Structure content with proper headings (e.g., `#`, `##`, `###`) for chapters, sections, and subsections.
- Ensure logical flow: introduce concepts, provide details, and summarize where appropriate.
- Avoid jargon unless explained, especially for beginner audiences.
- Use active voice unless passive voice enhances clarity or emphasis.
- Proofread for grammar, spelling, and punctuation before finalizing content.
- When editing existing content, preserve the original tone and style unless explicitly instructed to change.
- Avoid including sensitive information (e.g., personal details, API keys) in generated content.
- I want you to operate directly with the files. Do not show the results to me, but write them to the file. Ask for confirmation and I will review it.

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

## Non-Fiction Books

- **Audience**: Assume a general adult audience with no specific expertise unless specified.
- **Content Style**:
  - Use an **engaging, narrative-driven tone** for storytelling or informative prose.
  - Include vivid descriptions, anecdotes, or case studies to support key points.
  - Avoid overly academic language; prioritize clarity and relatability.
  - You should not be terse, write as if for people that like reading long format content.
- **Structure**:
  - Organize chapters with a clear narrative arc: introduction, main content, and conclusion.
  - Use subheadings to break up long sections for readability.
  - Include transitions between sections to maintain flow.
  - If relevant, incorporate quotes, statistics, or references to credible sources (but do not fabricate data).
- **Example Prompt Response**:
  - If asked to "write a chapter on the history of space exploration," generate:
    - An engaging introduction to spark reader interest (e.g., a key moment like the Moon landing).
    - Chronological sections covering major milestones.
    - Anecdotes about key figures (e.g., astronauts, scientists).
    - A conclusion summarizing the impact and future of space exploration.

## Formatting Guidelines

- Use Markdown for all generated content unless specified otherwise.
- For code blocks in technical books, use triple backticks with the language identifier (e.g., ```python).
- For emphasis, use **bold** for key terms and _italics_ for subtle emphasis.
- Include page breaks or section dividers (e.g., `---`) for long chapters.
- Number lists for step-by-step instructions; use bullets for general points.

## Additional Instructions

- When unsure about the book type, ask for clarification in the response (e.g., "Is this for a technical programming or non-fiction book?").
- If a specific style guide (e.g., APA, Chicago) is mentioned, apply it for citations and formatting.
- For large content requests (e.g., full chapters), generate an outline first and ask if the user wants to proceed with the full text.
- Save generated content in `.md` files in the current directory unless instructed otherwise.
