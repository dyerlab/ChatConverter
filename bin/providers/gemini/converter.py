"""
Gemini export converter.

Converts Safari .webarchive files containing shared Gemini conversations
into Obsidian-compatible markdown files.

Input Format:
    Safari Web Archive (.webarchive) - Apple binary plist containing:
    - WebMainResource: The rendered HTML of the conversation page
    - WebSubresources: CSS, JS, and some cached assets
    - WebSubframeArchives: Nested frames (not used)

HTML Structure (as of Jan 2025):
    User messages:
        <div class="user-query-container">
            <div class="query-content" id="user-query-content-N">
                <p class="query-text">
                    <p class="query-text-line">Message text</p>
                </p>
            </div>
        </div>

    Assistant responses:
        <message-content class="message-content">
            <div class="markdown markdown-main-panel">
                [HTML content with p, ul, li, table, img, etc.]
            </div>
        </message-content>

    Images:
        - Generated images: <img src="https://lh3.googleusercontent.com/gg/...">
        - Data URIs: <img src="data:image/png;base64,...">

Output Format:
    - Markdown files with YAML frontmatter (tags: [gemini])
    - User messages as blockquotes (> prefix)
    - Assistant responses as regular markdown
    - Images saved as PNG to attachments/ folder
    - Obsidian wiki-link syntax for images: ![[filename.png]]
"""

from __future__ import annotations

import base64
import hashlib
import plistlib
import re
import urllib.request
from html import unescape
from pathlib import Path
from typing import TYPE_CHECKING

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from providers.base import BaseConverter
from common.text_transforms import clean_text, normalize_whitespace


class GeminiConverter(BaseConverter):
    """
    Converter for Gemini conversations saved as Safari webarchives.

    Since Google doesn't provide bulk export for Gemini conversations,
    users must manually share and save each conversation as a Safari
    Web Archive (.webarchive) file.

    Attributes:
        _image_counter: Tracks image numbering within current conversation
        _current_conversation: Name of conversation being processed (for filenames)
        _attachments_saved: Running count of images saved across all conversations
    """

    def __init__(self, source_dir: Path, output_dir: Path) -> None:
        """
        Initialize the Gemini converter.

        Args:
            source_dir: Path to dated export folder containing .webarchive files
                        (e.g., providers/gemini/2026.01.18/)
            output_dir: Path to output directory for this export
                        (e.g., obsidian_export/gemini/2026.01.18/)
        """
        super().__init__(source_dir, output_dir)
        self._image_counter: int = 0
        self._current_conversation: str = ""
        self._attachments_saved: int = 0

    @property
    def provider_name(self) -> str:
        """Return the provider identifier."""
        return 'gemini'

    def convert(self) -> dict:
        """
        Run the full conversion process for all webarchive files.

        Scans the source directory for .webarchive files, converts each
        to markdown, and saves images to the attachments folder.

        Returns:
            Statistics dictionary with keys:
                - conversations_total: Number of webarchive files found
                - conversations_converted: Number successfully converted
                - attachments_copied: Number of images saved
                - errors: List of error messages for failed conversions
        """
        stats = {
            'conversations_total': 0,
            'conversations_converted': 0,
            'attachments_copied': 0,
            'errors': []
        }

        self.ensure_output_dirs()

        # Find all webarchive files in source directory
        webarchives = list(self.source_dir.glob('*.webarchive'))
        stats['conversations_total'] = len(webarchives)

        if not webarchives:
            print("  No .webarchive files found")
            return stats

        print(f"  Found {len(webarchives)} webarchive files")

        # Track used filenames to handle duplicates
        used_filenames: dict[str, int] = {}

        for archive_path in webarchives:
            # Use the webarchive filename (without extension) as conversation title
            title = archive_path.stem
            base_name = self.sanitize_filename(title)

            # Handle duplicate filenames by appending counter
            if base_name in used_filenames:
                used_filenames[base_name] += 1
                filename = f"{base_name} ({used_filenames[base_name]})"
            else:
                used_filenames[base_name] = 0
                filename = base_name

            output_path = self.markdown_dir / f"{filename}.md"

            try:
                # Reset per-conversation state
                self._current_conversation = filename
                self._image_counter = 0

                if self._convert_webarchive(archive_path, output_path):
                    stats['conversations_converted'] += 1
                    print(f"    Converted: {filename}")
            except Exception as e:
                stats['errors'].append(f"{title}: {str(e)}")
                print(f"    Error: {title} - {e}")

        stats['attachments_copied'] = self._attachments_saved
        return stats

    def _convert_webarchive(self, archive_path: Path, output_path: Path) -> bool:
        """
        Convert a single webarchive file to markdown.

        Args:
            archive_path: Path to the .webarchive file
            output_path: Path where the markdown file should be written

        Returns:
            True if conversion succeeded, False if no content was extracted
        """
        # Read the webarchive (Apple binary plist format)
        with open(archive_path, 'rb') as f:
            data = plistlib.load(f)

        # Extract the main HTML content from WebMainResource
        main_resource = data.get('WebMainResource', {})
        html_bytes = main_resource.get('WebResourceData', b'')

        if not html_bytes:
            return False

        html = html_bytes.decode('utf-8', errors='ignore')

        # Parse HTML to extract conversation turns
        turns = self._extract_turns(html)

        if not turns:
            return False

        # Build markdown document
        content = self.create_frontmatter(tags=['gemini'])
        content += self._format_conversation(turns)
        content = normalize_whitespace(content)

        output_path.write_text(content, encoding='utf-8')
        return True

    def _extract_turns(self, html: str) -> list[dict]:
        """
        Extract conversation turns from the rendered HTML.

        Parses the Gemini page HTML to find user queries and model responses,
        matching them by their position in the document.

        Args:
            html: The full HTML content of the conversation page

        Returns:
            List of turn dictionaries, each containing:
                - role: 'user' or 'assistant'
                - content: The message text (HTML for assistant, plain for user)
        """
        turns = []

        # === Extract User Queries ===
        # User queries are identified by id="user-query-content-N" where N is 0-indexed
        # The actual text is in nested <p class="query-text-line"> elements

        user_matches = []
        for match in re.finditer(r'id="user-query-content-(\d+)"', html):
            idx = int(match.group(1))
            start_pos = match.start()

            # Search for query text within 5000 chars after the ID marker
            text_match = re.search(
                r'class="query-text[^"]*"[^>]*>(.*?)</p>',
                html[start_pos:start_pos + 5000],
                re.DOTALL
            )

            if text_match:
                raw_text = text_match.group(1)

                # Try to extract individual lines (multi-line queries)
                lines = re.findall(
                    r'class="query-text-line[^"]*"[^>]*>\s*(.*?)\s*</p>',
                    raw_text,
                    re.DOTALL
                )

                if lines:
                    text = '\n'.join(self._clean_html(line) for line in lines)
                else:
                    text = self._clean_html(raw_text)

                user_matches.append((idx, start_pos, text))

        # === Extract Model Responses ===
        # Responses are in <div class="markdown markdown-main-panel"> elements
        # within <message-content> containers

        response_pattern = re.compile(
            r'class="markdown markdown-main-panel[^"]*"[^>]*>(.*?)</div>\s*</message-content>',
            re.DOTALL
        )

        response_matches = []
        for match in response_pattern.finditer(html):
            response_matches.append((match.start(), match.group(1)))

        # === Match Queries with Responses ===
        # Sort queries by index and pair with responses by document position

        user_matches.sort(key=lambda x: x[0])

        for i, (idx, user_pos, user_text) in enumerate(user_matches):
            # Add user turn
            if user_text.strip():
                turns.append({'role': 'user', 'content': user_text.strip()})

            # Find the response between this query and the next
            next_user_pos = user_matches[i + 1][1] if i + 1 < len(user_matches) else len(html)

            for resp_pos, resp_content in response_matches:
                if user_pos < resp_pos < next_user_pos:
                    cleaned = self._html_to_markdown(resp_content)
                    if cleaned.strip():
                        turns.append({'role': 'assistant', 'content': cleaned.strip()})
                    break

        return turns

    def _clean_html(self, html: str) -> str:
        """
        Remove HTML tags and normalize text.

        Args:
            html: Raw HTML string potentially containing tags and entities

        Returns:
            Plain text with HTML tags stripped, entities decoded, and
            whitespace normalized to single spaces
        """
        text = re.sub(r'<[^>]+>', '', html)  # Strip all HTML tags
        text = unescape(text)                 # Decode &amp; &lt; etc.
        text = re.sub(r'\s+', ' ', text)      # Collapse whitespace
        return text.strip()

    def _extract_and_save_image(self, data_uri: str) -> str | None:
        """
        Extract image from a base64 data URI and save to attachments.

        Args:
            data_uri: Full data URI string (e.g., "data:image/png;base64,...")

        Returns:
            Obsidian wiki-link to saved image (e.g., "![[conversation_img01.png]]")
            or None if extraction fails
        """
        try:
            if not data_uri.startswith('data:image/'):
                return None

            # Parse data URI format: data:mime/type;base64,<encoded_data>
            header, b64_data = data_uri.split(';base64,', 1)
            mime_type = header.replace('data:', '')

            # Map MIME types to file extensions
            ext_map = {
                'image/png': '.png',
                'image/jpeg': '.jpg',
                'image/jpg': '.jpg',
                'image/gif': '.gif',
                'image/webp': '.webp',
            }
            ext = ext_map.get(mime_type, '.png')

            # Decode and save
            image_data = base64.b64decode(b64_data)

            self._image_counter += 1
            filename = f"{self._current_conversation}_img{self._image_counter:02d}{ext}"

            output_path = self.attachments_dir / filename
            output_path.write_bytes(image_data)
            self._attachments_saved += 1

            return f"![[{filename}]]"

        except Exception:
            return None

    def _download_and_save_image(self, url: str) -> str | None:
        """
        Download image from Google's CDN and save as PNG to attachments.

        Google's image CDN (lh3.googleusercontent.com) supports format
        conversion via URL parameters. We use =s0-rp to request:
        - s0: Original size (no resizing)
        - rp: PNG format (lossless)

        Args:
            url: Google CDN image URL

        Returns:
            Obsidian wiki-link to saved image (e.g., "![[conversation_img01.png]]")
            or None if download fails
        """
        try:
            # Only process Google-hosted images
            if 'lh3.googleusercontent.com' not in url:
                return None

            # Modify URL to request PNG format
            # Replace any existing params with =s0-rp
            if '=' in url:
                png_url = url.rsplit('=', 1)[0] + '=s0-rp'
            else:
                png_url = url + '=s0-rp'

            # Download with browser-like User-Agent
            req = urllib.request.Request(png_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as response:
                image_data = response.read()

            # Save as PNG
            self._image_counter += 1
            filename = f"{self._current_conversation}_img{self._image_counter:02d}.png"

            output_path = self.attachments_dir / filename
            output_path.write_bytes(image_data)
            self._attachments_saved += 1

            return f"![[{filename}]]"

        except Exception:
            return None

    def _html_to_markdown(self, html: str) -> str:
        """
        Convert Gemini's HTML response content to markdown.

        Processes HTML elements in a specific order to handle nested structures
        correctly. Images are extracted and saved, then HTML is converted to
        markdown syntax.

        Args:
            html: HTML content from a model response div

        Returns:
            Markdown-formatted text with images saved to attachments
        """
        text = html

        # ============================================================
        # IMAGES - Process first to extract before HTML cleanup
        # ============================================================

        # Handle embedded base64 images (data URIs)
        def replace_data_uri_image(match):
            data_uri = match.group(1)
            if data_uri.startswith('data:image/'):
                md_link = self._extract_and_save_image(data_uri)
                if md_link:
                    return f"\n{md_link}\n"
            return ''

        text = re.sub(
            r'<img[^>]*src="(data:image/[^"]+)"[^>]*>',
            replace_data_uri_image,
            text
        )

        # Handle external Google CDN images (generated images)
        def replace_external_image(match):
            url = match.group(1)
            # Only download Gemini-generated images (gg/ path)
            if 'lh3.googleusercontent.com/gg/' in url:
                md_link = self._download_and_save_image(url)
                if md_link:
                    return f"\n{md_link}\n"
            # Keep other external images as standard markdown links
            return f'\n![]({url})\n'

        text = re.sub(
            r'<img[^>]*src="(https?://[^"]+)"[^>]*>',
            replace_external_image,
            text
        )

        # ============================================================
        # CODE BLOCKS - Process before inline formatting
        # ============================================================

        # Gemini's custom <code-block> element with language attribute
        text = re.sub(
            r'<code-block[^>]*?language="([^"]*)"[^>]*>(.*?)</code-block>',
            lambda m: f'\n```{m.group(1)}\n{unescape(m.group(2))}\n```\n',
            text,
            flags=re.DOTALL
        )

        # Standard <pre><code class="language-X"> blocks
        text = re.sub(
            r'<pre[^>]*><code[^>]*class="[^"]*language-([^"]*)"[^>]*>(.*?)</code></pre>',
            lambda m: f'\n```{m.group(1)}\n{unescape(m.group(2))}\n```\n',
            text,
            flags=re.DOTALL
        )

        # Generic <pre><code> blocks without language
        text = re.sub(
            r'<pre[^>]*><code[^>]*>(.*?)</code></pre>',
            lambda m: f'\n```\n{unescape(m.group(1))}\n```\n',
            text,
            flags=re.DOTALL
        )

        # Inline <code> elements
        text = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', text)

        # ============================================================
        # INLINE FORMATTING
        # ============================================================

        # Bold: <b> and <strong>
        text = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', text)
        text = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', text)

        # Italic: <i> and <em>
        text = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', text)
        text = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', text)

        # ============================================================
        # HEADERS
        # ============================================================

        text = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', text)
        text = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', text)
        text = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', text)
        text = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n', text)

        # ============================================================
        # TABLES - Convert HTML tables to markdown pipe tables
        # ============================================================

        def process_table(match):
            """Convert an HTML table to markdown table format."""
            table_html = match.group(1)
            rows = []

            # Extract all <tr> rows from thead and tbody
            row_matches = re.findall(r'<tr[^>]*>(.*?)</tr>', table_html, re.DOTALL)

            for row_idx, row_html in enumerate(row_matches):
                # Extract <td> and <th> cells
                cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', row_html, re.DOTALL)

                # Clean cell contents: strip HTML, decode entities, normalize whitespace
                clean_cells = []
                for cell in cells:
                    cell_text = re.sub(r'<[^>]+>', '', cell)
                    cell_text = unescape(cell_text)
                    cell_text = re.sub(r'\s+', ' ', cell_text).strip()
                    clean_cells.append(cell_text)

                if clean_cells:
                    rows.append(clean_cells)
                    # Add markdown separator row after header (first row)
                    if row_idx == 0:
                        rows.append(['---'] * len(clean_cells))

            if not rows:
                return ''

            # Build markdown table with pipe separators
            md_rows = []
            for row in rows:
                md_rows.append('| ' + ' | '.join(row) + ' |')

            return '\n\n' + '\n'.join(md_rows) + '\n\n'

        text = re.sub(
            r'<table[^>]*>(.*?)</table>',
            process_table,
            text,
            flags=re.DOTALL
        )

        # ============================================================
        # LISTS - Handle <ul>/<ol> with nested <li> elements
        # ============================================================

        def process_list_item(match):
            """Convert a list item, stripping inner <p> tags."""
            content = match.group(1)
            # Gemini wraps list item content in <p> tags - remove them
            content = re.sub(r'<p[^>]*>', '', content)
            content = re.sub(r'</p>', '', content)
            content = re.sub(r'\s+', ' ', content).strip()
            return f'\n- {content}'

        text = re.sub(
            r'<li[^>]*>(.*?)</li>',
            process_list_item,
            text,
            flags=re.DOTALL
        )

        # Remove list container tags
        text = re.sub(r'<ul[^>]*>', '', text)
        text = re.sub(r'</ul>', '\n', text)
        text = re.sub(r'<ol[^>]*>', '', text)
        text = re.sub(r'</ol>', '\n', text)

        # ============================================================
        # BLOCK ELEMENTS
        # ============================================================

        # Paragraphs become double newlines
        text = re.sub(r'<p[^>]*>', '\n', text)
        text = re.sub(r'</p>', '\n', text)

        # Line breaks
        text = re.sub(r'<br\s*/?>', '\n', text)

        # Divs are structural only - remove without adding whitespace
        text = re.sub(r'<div[^>]*>', '', text)
        text = re.sub(r'</div>', '', text)

        # ============================================================
        # LINKS
        # ============================================================

        text = re.sub(
            r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>',
            r'[\2](\1)',
            text
        )

        # ============================================================
        # CLEANUP
        # ============================================================

        # Remove any remaining HTML tags
        text = re.sub(r'<[^>]+>', '', text)

        # Decode any remaining HTML entities
        text = unescape(text)

        # Normalize whitespace: collapse multiple blank lines, trim spaces
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        # Apply common text transformations (emoji removal, LaTeX, etc.)
        text = clean_text(text)

        return text.strip()

    def _format_conversation(self, turns: list[dict]) -> str:
        """
        Format extracted conversation turns as markdown.

        User messages are formatted as blockquotes (> prefix on each line).
        Assistant messages are included as regular markdown text.

        Args:
            turns: List of turn dictionaries with 'role' and 'content' keys

        Returns:
            Formatted markdown string with turns separated by blank lines
        """
        parts = []

        for turn in turns:
            role = turn['role']
            content = turn['content']

            if role == 'user':
                # Format user messages as blockquotes
                lines = content.split('\n')
                quoted = []
                for line in lines:
                    if line.strip():
                        quoted.append('> ' + line)
                    else:
                        quoted.append('>')  # Empty blockquote line
                parts.append('\n'.join(quoted))
            else:
                # Assistant responses as-is
                parts.append(content)

        return '\n\n'.join(parts)
