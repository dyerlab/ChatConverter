"""
Claude export converter.
Handles the flat message array format from Anthropic data exports.

Schema version: 1.0
Expected files: conversations.json, memories.json, projects.json, users.json
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from providers.base import BaseConverter
from providers.schema import validate_schema
from common.text_transforms import clean_text, normalize_whitespace


class ClaudeConverter(BaseConverter):
    """Converter for Claude/Anthropic data exports."""

    # Schema version this converter is designed for
    SCHEMA_VERSION = '1.0'

    def __init__(self, source_dir: Path, output_dir: Path):
        super().__init__(source_dir, output_dir)
        self.project_memories = {}  # UUID -> memory text

    @property
    def provider_name(self) -> str:
        return 'claude'

    def convert(self) -> dict:
        """Run the full conversion process."""
        stats = {
            'conversations_total': 0,
            'conversations_converted': 0,
            'memories_converted': 0,
            'projects_converted': 0,
            'attachments_copied': 0,
            'errors': []
        }

        self.ensure_output_dirs()

        # Validate schema
        print("  Validating schema...")
        is_valid, version, differences = validate_schema(self.source_dir, 'claude')
        if not is_valid:
            print(f"  WARNING: Schema differences detected (expected v{version}):")
            for diff in differences:
                print(f"    - {diff}")
            print("  Proceeding with conversion, but results may be incomplete.")
        else:
            print(f"  Schema validated (v{version})")

        # Load and cache memories (needed for projects)
        self._load_memories()

        # Convert conversations
        self._convert_conversations(stats)

        # Convert memories
        self._convert_memories(stats)

        # Convert projects
        self._convert_projects(stats)

        # Note: Claude exports don't include separate image files
        print("  No separate attachments to copy (embedded in conversations)")

        return stats

    def _load_memories(self):
        """Load memories.json and cache project memories for later use."""
        memories_file = self.source_dir / 'memories.json'
        if not memories_file.exists():
            return

        with open(memories_file, 'r', encoding='utf-8') as f:
            memories = json.load(f)

        if memories and isinstance(memories, list):
            for mem in memories:
                project_mems = mem.get('project_memories', {})
                self.project_memories.update(project_mems)

    def _convert_conversations(self, stats: dict):
        """Convert all conversations."""
        conversations_file = self.source_dir / 'conversations.json'
        if not conversations_file.exists():
            stats['errors'].append(f"conversations.json not found in {self.source_dir}")
            return

        print(f"  Loading conversations...")
        with open(conversations_file, 'r', encoding='utf-8') as f:
            conversations = json.load(f)

        stats['conversations_total'] = len(conversations)
        print(f"  Found {len(conversations)} conversations")

        used_filenames = {}

        for conv in conversations:
            name = conv.get('name', 'Untitled')
            base_name = self.sanitize_filename(name)

            if base_name in used_filenames:
                used_filenames[base_name] += 1
                filename = f"{base_name} ({used_filenames[base_name]})"
            else:
                used_filenames[base_name] = 0
                filename = base_name

            output_path = self.markdown_dir / f"{filename}.md"

            try:
                if self._convert_conversation(conv, output_path):
                    stats['conversations_converted'] += 1
                    print(f"    Converted: {filename}")
            except Exception as e:
                stats['errors'].append(f"{name}: {str(e)}")

    def _convert_memories(self, stats: dict):
        """Convert memories.json to a single markdown file."""
        memories_file = self.source_dir / 'memories.json'
        if not memories_file.exists():
            print("  No memories.json found")
            return

        print("  Converting memories...")

        with open(memories_file, 'r', encoding='utf-8') as f:
            memories = json.load(f)

        if not memories:
            return

        # Build the memories document
        content = self.create_frontmatter(tags=['claude', 'chat_memory'])
        content += "# Claude Memories\n\n"
        content += "This file contains Claude's learned context from conversations.\n\n"

        for mem in memories:
            # General conversation memory
            conv_memory = mem.get('conversations_memory', '')
            if conv_memory:
                content += "## General Context\n\n"
                content += conv_memory + "\n\n"

            # Project-specific memories
            project_mems = mem.get('project_memories', {})
            if project_mems:
                content += "## Project Memories\n\n"
                for proj_uuid, proj_memory in project_mems.items():
                    # Try to find project name from projects.json
                    proj_name = self._get_project_name(proj_uuid) or proj_uuid[:12] + "..."
                    content += f"### {proj_name}\n\n"
                    content += proj_memory + "\n\n"

        content = normalize_whitespace(content)
        output_path = self.markdown_dir / "Claude Memories.md"
        output_path.write_text(content, encoding='utf-8')

        stats['memories_converted'] = 1
        print(f"    Converted: Claude Memories.md")

    def _get_project_name(self, uuid: str) -> str | None:
        """Look up project name by UUID."""
        projects_file = self.source_dir / 'projects.json'
        if not projects_file.exists():
            return None

        with open(projects_file, 'r', encoding='utf-8') as f:
            projects = json.load(f)

        for proj in projects:
            if proj.get('uuid') == uuid:
                return proj.get('name')
        return None

    def _convert_projects(self, stats: dict):
        """Convert projects.json to markdown files."""
        projects_file = self.source_dir / 'projects.json'
        if not projects_file.exists():
            print("  No projects.json found")
            return

        print("  Converting projects...")

        with open(projects_file, 'r', encoding='utf-8') as f:
            projects = json.load(f)

        print(f"  Found {len(projects)} projects")

        for proj in projects:
            name = proj.get('name', 'Untitled Project')
            filename = self.sanitize_filename(f"Project - {name}")
            output_path = self.markdown_dir / f"{filename}.md"

            try:
                if self._convert_project(proj, output_path):
                    stats['projects_converted'] += 1
                    print(f"    Converted: {filename}")
            except Exception as e:
                stats['errors'].append(f"Project {name}: {str(e)}")

    def _convert_project(self, proj: dict, output_path: Path) -> bool:
        """Convert a single project to markdown."""
        name = proj.get('name', 'Untitled Project')
        uuid = proj.get('uuid', '')
        description = proj.get('description', '')
        docs = proj.get('docs', [])
        created_at = proj.get('created_at', '')

        # Skip starter projects (Claude's built-in examples)
        if proj.get('is_starter_project', False):
            return False

        content = self.create_frontmatter(tags=['claude', 'chat_project'])
        content += f"# {name}\n\n"

        if description:
            content += f"{description}\n\n"

        # Add project memory if available
        if uuid in self.project_memories:
            content += "## Project Memory\n\n"
            content += self.project_memories[uuid] + "\n\n"

        # Add embedded docs
        if docs:
            content += "## Project Documents\n\n"
            for doc in docs:
                doc_filename = doc.get('filename', 'unknown')
                doc_content = doc.get('content', '')

                content += f"### {doc_filename}\n\n"
                if doc_content:
                    lang = self._get_language(doc_filename)
                    content += f"```{lang}\n{doc_content}\n```\n\n"

        content = normalize_whitespace(content)
        output_path.write_text(content, encoding='utf-8')

        if created_at:
            self._set_file_date(output_path, created_at)

        return True

    def _convert_conversation(self, conv: dict, output_path: Path) -> bool:
        """Convert a single conversation to markdown."""
        messages = conv.get('chat_messages', [])
        if not messages:
            return False

        content = self.create_frontmatter(tags=['claude'])
        content += self._format_conversation(messages)
        content = normalize_whitespace(content)

        output_path.write_text(content, encoding='utf-8')

        created_at = conv.get('created_at')
        if created_at:
            self._set_file_date(output_path, created_at)

        return True

    def _format_conversation(self, messages: list) -> str:
        """Format messages with human as quotes, assistant as normal text."""
        parts = []

        for msg in messages:
            text = self._extract_message_text(msg)
            if not text:
                continue

            text = clean_text(text)
            sender = msg.get('sender', 'unknown')

            if sender == 'human':
                lines = text.split('\n')
                quoted = []
                for line in lines:
                    if line.strip():
                        quoted.append('> ' + line)
                    else:
                        quoted.append('>')
                parts.append('\n'.join(quoted))

                attachments = msg.get('attachments', [])
                if attachments:
                    att_text = self._format_attachments(attachments)
                    if att_text:
                        parts.append(att_text)
            else:
                parts.append(text)

        return '\n\n'.join(parts)

    def _extract_message_text(self, msg: dict) -> str:
        """Extract text content from a message."""
        text = msg.get('text', '')
        if text:
            return text.strip()

        content_items = msg.get('content', [])
        text_parts = []

        for item in content_items:
            item_type = item.get('type', '')

            if item_type == 'text':
                text_parts.append(item.get('text', ''))
            elif item_type == 'thinking':
                thinking = item.get('thinking', '')
                if thinking:
                    text_parts.append(f"\n<details>\n<summary>Thinking</summary>\n\n{thinking}\n\n</details>\n")

        return '\n'.join(text_parts).strip()

    def _format_attachments(self, attachments: list) -> str:
        """Format message attachments (embedded files)."""
        parts = []

        for att in attachments:
            filename = att.get('file_name', 'unknown')
            file_type = att.get('file_type', '')
            content = att.get('extracted_content', '')

            if content:
                if file_type.startswith('text/') or filename.endswith(('.md', '.py', '.swift', '.js', '.css')):
                    lang = self._get_language(filename)
                    parts.append(f"\n**Attached: {filename}**\n```{lang}\n{content[:500]}{'...' if len(content) > 500 else ''}\n```")
                else:
                    parts.append(f"\n**Attached: {filename}** ({att.get('file_size', 0)} bytes)")

        return '\n'.join(parts)

    def _get_language(self, filename: str) -> str:
        """Get markdown code block language from filename."""
        ext_map = {
            '.py': 'python',
            '.swift': 'swift',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.css': 'css',
            '.html': 'html',
            '.json': 'json',
            '.md': 'markdown',
            '.sh': 'bash',
            '.yml': 'yaml',
            '.yaml': 'yaml',
        }
        for ext, lang in ext_map.items():
            if filename.endswith(ext):
                return lang
        return ''

    def _set_file_date(self, filepath: Path, iso_timestamp: str):
        """Set file modification date from ISO timestamp."""
        import os
        import subprocess

        try:
            dt = datetime.fromisoformat(iso_timestamp.replace('Z', '+00:00'))
            timestamp = dt.timestamp()

            os.utime(filepath, (timestamp, timestamp))

            date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
            subprocess.run(
                ['SetFile', '-d', date_str, str(filepath)],
                capture_output=True,
                check=False
            )
        except Exception:
            pass
