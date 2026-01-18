# ChatConverter: AI Chat to Obsidian: The Universal Archive

A robust Python-based conversion pipeline designed to liberate your AI conversations from proprietary "walled gardens" and transform them into future-proof, searchable Markdown files for your Obsidian PKM system.

## The Vision

Most AI platforms treat your data as a secondary concern. This tool allows you to:

- Own your data: Move from proprietary JSON/HTML to local Markdown.
- Centralize Research: Search across ChatGPT, Claude, and Gemini in a single Obsidian vault.
- Maintain Context: Preserve complex elements like ChatGPT’s branching trees, Claude’s "extended thinking," and Gemini’s image assets.

## Supported Chat Providers

Provider | Export Method | Notes 
---------|---------------|-------
ChatGPT | Native JSON  | Export	Handles complex tree-traversal and local asset mapping.
Claude | Native JSON  | Export	Supports "thinking" blocks, tool use, and embedded Base64 images.
Gemini | Manual WebArchive | Extracts HTML from .webarchive files and downloads high-res CDN images.

## Project Architecture

The system is built on an extensible, object-oriented architecture:
- `bin/providers/base.py`: Abstract base class for all converters.
- `bin/providers/`: Specific implementations for parsing and data cleaning.
- *Schema Fingerprinting:* Automatically detects changes in provider export formats to prevent data loss.

## Installation & Usage

### Prerequisites

- Python 3.10+
- `pip install beautifulsoup4 python-magic`

### Setup

1. Clone the repository: git clone https://github.com/[your-username]/ai-chat-obsidian.git
2. Place your raw exports in the providers/ directory following the structure defined in the blog post.
3. Run the master converter:

```bash
python main.py --all
```

## Markdown Output Format

Files are formatted for immediate use in Obsidian with:
- YAML Frontmatter: Includes provider tags and `relatedTo` fields.  In my PKM, a modification of the [PARA](https://fortelabs.com/blog/para/) method, I use this to link this specific file to `Area` or `Project` or other organizational items (e.g., `Resources/People` or `Resrouces/Organizations` or `Teaching/ClassXYZ`.
- Visual Distinction: User messages are formatted as blockquotes.
- Asset Integration: Images are automatically saved to `attachments/` and linked via Wiki-links.  In my Obsidian vault, I keep all my attachments in the `Resources/Attachments` folder.


## Contributing

As AI providers frequently change their export schemas, contributions are welcome! Please refer to `CLAUDE.md` for coding standards and guide-rails for adding new providers.  This was vibecoded with Claude Code.
