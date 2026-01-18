"""
ChatGPT export converter.
Handles the tree-structured conversation format from OpenAI data exports.
"""

import json
import os
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from providers.base import BaseConverter
from common.text_transforms import clean_text, normalize_whitespace


class ChatGPTConverter(BaseConverter):
    """Converter for ChatGPT/OpenAI data exports."""

    def __init__(self, source_dir: Path, output_dir: Path):
        super().__init__(source_dir, output_dir)
        self.asset_map = {}  # Maps asset pointers to filenames

    @property
    def provider_name(self) -> str:
        return 'chatgpt'

    def convert(self) -> dict:
        """Run the full conversion process."""
        stats = {
            'conversations_total': 0,
            'conversations_converted': 0,
            'attachments_copied': 0,
            'errors': []
        }

        self.ensure_output_dirs()

        # Build asset pointer mapping
        print("  Building image asset map...")
        self._build_asset_map()
        print(f"  Found {len(self.asset_map)} image assets")

        # Load conversations
        conversations_file = self.source_dir / 'conversations.json'
        if not conversations_file.exists():
            stats['errors'].append(f"conversations.json not found in {self.source_dir}")
            return stats

        print(f"  Loading conversations...")
        with open(conversations_file, 'r', encoding='utf-8') as f:
            conversations = json.load(f)

        stats['conversations_total'] = len(conversations)
        print(f"  Found {len(conversations)} conversations")

        # Convert each conversation
        used_filenames = {}

        for conv in conversations:
            title = conv.get('title', 'Untitled')
            base_name = self.sanitize_filename(title)

            # Handle duplicates
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
                stats['errors'].append(f"{title}: {str(e)}")

        # Copy attachments
        print("  Copying attachments...")
        stats['attachments_copied'] = self._copy_attachments()
        print(f"  Copied {stats['attachments_copied']} image files")

        return stats

    def _build_asset_map(self):
        """Build mapping from asset pointers to actual filenames."""
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}

        def scan_directory(directory: Path):
            if not directory.exists():
                return
            for f in directory.iterdir():
                if f.is_file() and f.suffix.lower() in image_extensions:
                    self._register_asset(f.name)

        # Scan root directory
        scan_directory(self.source_dir)

        # Scan subdirectories
        for subdir in self.source_dir.iterdir():
            if subdir.is_dir():
                scan_directory(subdir)
                # Also scan nested directories (e.g., audio folders)
                for nested in subdir.iterdir():
                    if nested.is_dir():
                        scan_directory(nested)

    def _register_asset(self, filename: str):
        """Register an asset file with its possible pointer formats."""
        # sediment:// style (file_XXXX)
        if filename.startswith('file_'):
            match = re.match(r'(file_[0-9a-f]+)', filename)
            if match:
                file_id = match.group(1)
                self.asset_map[f'sediment://{file_id}'] = filename

        # file-service:// style (file-XXXX)
        elif filename.startswith('file-'):
            match = re.match(r'(file-[A-Za-z0-9]+)', filename)
            if match:
                file_id = match.group(1)
                self.asset_map[f'file-service://{file_id}'] = filename

    def _get_messages_from_mapping(self, mapping: dict) -> list:
        """Extract messages in order from the conversation tree."""
        messages = []

        # Find root node
        root = None
        for node_id, node in mapping.items():
            if node.get('parent') is None:
                root = node_id
                break

        if not root:
            return messages

        def traverse(node_id):
            node = mapping.get(node_id)
            if not node:
                return

            msg = node.get('message')
            if msg:
                author = msg.get('author', {}).get('role', 'unknown')
                content = msg.get('content', {})
                parts = content.get('parts', [])

                if author in ['user', 'assistant'] and parts:
                    text_parts = []
                    image_embeds = []

                    for part in parts:
                        if isinstance(part, str):
                            text_parts.append(part)
                        elif isinstance(part, dict):
                            if 'text' in part:
                                text_parts.append(part['text'])
                            elif part.get('content_type') == 'image_asset_pointer':
                                asset_pointer = part.get('asset_pointer', '')
                                if asset_pointer in self.asset_map:
                                    filename = self.asset_map[asset_pointer]
                                    image_embeds.append(f'![[{filename}]]')

                    text = '\n'.join(text_parts)

                    if image_embeds:
                        if text:
                            text += '\n\n' + '\n'.join(image_embeds)
                        else:
                            text = '\n'.join(image_embeds)

                    if text:
                        messages.append({
                            'role': author,
                            'content': text,
                        })

            for child_id in node.get('children', []):
                traverse(child_id)

        traverse(root)
        return messages

    def _format_conversation(self, messages: list) -> str:
        """Format messages with user as quotes, assistant as normal text."""
        parts = []

        for msg in messages:
            content = clean_text(msg['content'])

            if msg['role'] == 'user':
                # Format as blockquote
                lines = content.split('\n')
                quoted = []
                for line in lines:
                    if line.strip():
                        quoted.append('> ' + line)
                    else:
                        quoted.append('>')
                parts.append('\n'.join(quoted))
            else:
                parts.append(content)

        return '\n\n'.join(parts)

    def _convert_conversation(self, conv: dict, output_path: Path) -> bool:
        """Convert a single conversation to markdown."""
        messages = self._get_messages_from_mapping(conv.get('mapping', {}))
        if not messages:
            return False

        content = self.create_frontmatter(tags=['chatgpt'])
        content += self._format_conversation(messages)
        content = normalize_whitespace(content)

        output_path.write_text(content, encoding='utf-8')

        # Set file creation/modification date
        create_time = conv.get('create_time')
        if create_time:
            self._set_file_date(output_path, create_time)

        return True

    def _set_file_date(self, filepath: Path, timestamp: float):
        """Set file creation and modification date (macOS)."""
        try:
            dt = datetime.fromtimestamp(timestamp)
            os.utime(filepath, (timestamp, timestamp))

            # macOS SetFile for creation date
            date_str = dt.strftime("%m/%d/%Y %H:%M:%S")
            subprocess.run(
                ['SetFile', '-d', date_str, str(filepath)],
                capture_output=True,
                check=False
            )
        except Exception:
            pass

    def _copy_attachments(self) -> int:
        """Copy all image files to attachments folder."""
        image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
        copied = 0

        def copy_images_from(directory: Path):
            nonlocal copied
            if not directory.exists():
                return
            for file in directory.iterdir():
                if file.is_file() and file.suffix.lower() in image_extensions:
                    dest = self.attachments_dir / file.name
                    if not dest.exists():
                        shutil.copy2(file, dest)
                        copied += 1

        # Copy from root
        copy_images_from(self.source_dir)

        # Copy from dalle-generations
        copy_images_from(self.source_dir / 'dalle-generations')

        # Copy from user-* and UUID directories
        for subdir in self.source_dir.iterdir():
            if subdir.is_dir():
                if subdir.name.startswith('user-') or (len(subdir.name) == 36 and '-' in subdir.name):
                    copy_images_from(subdir)

        return copied
