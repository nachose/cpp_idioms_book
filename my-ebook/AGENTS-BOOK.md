# Non-Fiction Books - Agent Guidelines

You are writing a non-fiction book.

Primary goal:

- Explain concepts, motivations, trade-offs, and mental models clearly.
- Engage readers with compelling narratives and informative prose.

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
- While American English is the primary language, Spanish may be used in specific, approved cases. Avoid other languages unless illustrating a concept.

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
- For emphasis, use **bold** for key terms and _italics_ for subtle emphasis.
- Include page breaks or section dividers (e.g., `---`) for long chapters.
- Number lists for step-by-step instructions; use bullets for general points.

## Additional Instructions

- If a specific style guide (e.g., APA, Chicago) is mentioned, apply it for citations and formatting.
- For large content requests (e.g., full chapters), generate an outline first and ask if the user wants to proceed with the full text.
- Save generated content in `.md` files in the current directory unless instructed otherwise.
- You can use mermaid diagrams if needed. Pipeline is prepared to handle them.
- For programming/technical books, refer to `AGENTS-PROGRAMMING.md` instead.

## File Naming

- Use kebab-case for markdown files (e.g., `01-introduction.md`)
- Structure: Each chapter in separate file, metadata in 00-metadata.yaml
