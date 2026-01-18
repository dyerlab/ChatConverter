"""
Base class for chat history provider converters.
Each provider (ChatGPT, Claude, etc.) implements this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime


class BaseConverter(ABC):
    """Abstract base class for provider-specific converters."""

    def __init__(self, source_dir: Path, output_dir: Path):
        """
        Initialize converter with source and output directories.

        Args:
            source_dir: Path to the provider's dated export folder
                        (e.g., providers/chatgpt/2026.01.15/)
            output_dir: Path to the obsidian_export directory
        """
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.markdown_dir = output_dir / 'markdown'
        self.attachments_dir = output_dir / 'attachments'

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider name (e.g., 'chatgpt', 'claude')."""
        pass

    @abstractmethod
    def convert(self) -> dict:
        """
        Run the conversion process.

        Returns:
            dict with conversion statistics:
            {
                'conversations_total': int,
                'conversations_converted': int,
                'attachments_copied': int,
                'errors': list[str]
            }
        """
        pass

    def ensure_output_dirs(self):
        """Create output directories if they don't exist."""
        self.markdown_dir.mkdir(parents=True, exist_ok=True)
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def sanitize_filename(title: str, max_length: int = 100) -> str:
        """Create a safe filename from a title string."""
        import re
        if not title:
            title = "Untitled"
        sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length].rsplit(' ', 1)[0]
        return sanitized or "Untitled"

    @staticmethod
    def create_frontmatter(tags: list[str] = None) -> str:
        """Create YAML frontmatter for Obsidian notes."""
        if tags is None:
            tags = []
        tag_lines = '\n'.join(f'  - {tag}' for tag in tags)
        return f"""---
tags:
{tag_lines}
relatedTo:
---

"""
