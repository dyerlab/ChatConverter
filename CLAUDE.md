# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Converts chat history exports from various AI providers (ChatGPT, Claude, etc.) into Obsidian-compatible markdown files. Designed for maintaining portable, provider-agnostic conversation archives.

## Directory Structure

```
ChatHistory/
├── bin/                          # Conversion scripts
│   ├── convert.py                # Main entry point
│   ├── registry.json             # Tracks processed exports
│   ├── common/                   # Shared utilities
│   │   └── text_transforms.py    # Emoji, math→LaTeX, subscripts
│   ├── providers/                # Provider-specific converters
│   │   ├── base.py               # BaseConverter abstract class
│   │   ├── schema.py             # Schema version detection
│   │   ├── chatgpt/
│   │   │   └── converter.py      # ChatGPT tree traversal, asset mapping
│   │   ├── claude/
│   │   │   └── converter.py      # Claude flat message array
│   │   └── gemini/
│   │       └── converter.py      # Gemini webarchive parsing
│   └── archive/                  # Deprecated scripts
├── providers/                    # Raw data exports (input)
│   ├── chatgpt/
│   │   └── YYYY.MM.DD/           # Date-stamped export folders
│   ├── claude/
│   │   └── YYYY.MM.DD/
│   └── gemini/
│       └── YYYY.MM.DD/           # Contains .webarchive files
└── obsidian_export/              # Converted output (mirrors input structure)
    ├── chatgpt/
    │   └── YYYY.MM.DD/
    │       ├── markdown/
    │       └── attachments/
    ├── claude/
    │   └── YYYY.MM.DD/
    │       ├── markdown/
    │       └── attachments/
    └── gemini/
        └── YYYY.MM.DD/
            ├── markdown/
            └── attachments/
```

## Running Conversions

```bash
cd bin
python3 convert.py
```

The script will:
1. Scan `providers/` for available exports
2. Show status (pending vs. already processed)
3. Validate export schema and warn of format changes
4. Prompt to convert pending exports that have converters
5. Output to `obsidian_export/<provider>/<date>/` (mirrors input structure)

## Output Tags

| Provider | Content Type | Tags |
|----------|--------------|------|
| ChatGPT | Conversations | `chatgpt` |
| Claude | Conversations | `claude` |
| Claude | Memories | `claude`, `chat_memory` |
| Claude | Projects | `claude`, `chat_project` |
| Gemini | Conversations | `gemini` |

## Schema Versioning

Each provider has an expected schema defined in `bin/providers/schema.py`. When converting, the system compares the export structure against the expected schema and warns of differences. This helps detect when providers change their export format.

Current schema versions:
- **ChatGPT**: v1.0 - Tree-structured `mapping` with parent/children nodes
- **Claude**: v1.0 - Flat `chat_messages` array with sender field
- **Gemini**: N/A - Uses Safari webarchive format (no JSON schema)

To update a schema after a format change, modify the `SchemaFingerprint` definitions in `schema.py`.

## Adding New Providers

1. Create `bin/providers/<provider>/converter.py`
2. Implement a class inheriting from `BaseConverter` (see `base.py`)
3. Add schema definition to `schema.py`
4. Register in `bin/convert.py` CONVERTERS dict

Required methods:
- `provider_name` (property): Return provider identifier
- `convert()`: Parse export, write markdown, return stats dict

## Provider Export Formats

**ChatGPT** (v1.0):
- Tree-structured `conversations.json` with `mapping` nodes
- Asset pointers use `sediment://` and `file-service://` URIs
- Images stored as separate files in subdirectories

**Claude** (v1.0):
- `conversations.json`: Flat `chat_messages` array, `sender`: "human"/"assistant"
- `memories.json`: General context + per-project memories
- `projects.json`: Project metadata + embedded docs (CLAUDE.md, code, etc.)
- `content` types: text, tool_use, tool_result, thinking
- Attachments embedded as `extracted_content` in JSON (no separate files)

**Gemini** (webarchive):
- No bulk export available; conversations must be individually shared and saved
- Input: Safari `.webarchive` files (Apple binary plist format)
- User messages extracted from `user-query-container` elements
- Model responses extracted from `markdown markdown-main-panel` elements
- Images: Downloaded as PNG from Google CDN (`lh3.googleusercontent.com/gg/...=s0-rp`)
- Conversation title derived from webarchive filename

**Gemini Export Workflow:**
1. In Gemini, click Share on a conversation to get a shareable URL
2. Open the URL in Safari
3. File → Save As → Format: **Web Archive**
4. Save to `providers/gemini/YYYY.MM.DD/`
5. Run `python3 bin/convert.py`

## Text Transformations (common/text_transforms.py)

- Emoji removal
- Unicode math symbols → LaTeX (`∑` → `$\sum$`)
- Unicode sub/superscripts → LaTeX
- HTML `<sub>`/`<sup>` → LaTeX
- Code block arrow fixes
