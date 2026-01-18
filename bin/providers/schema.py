"""
Schema version detection for provider exports.
Helps identify when export formats change and need converter updates.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json


@dataclass
class SchemaFingerprint:
    """Fingerprint of an export's data structure."""
    provider: str
    version: str
    files: dict[str, list[str]]  # filename -> list of top-level keys
    message_keys: list[str] | None = None  # for conversation exports
    content_types: set[str] | None = None  # types found in content arrays

    def matches(self, expected: 'SchemaFingerprint') -> tuple[bool, list[str]]:
        """
        Check if this fingerprint matches expected schema.
        Returns (matches, list of differences).
        """
        differences = []

        if self.files.keys() != expected.files.keys():
            differences.append(f"Files differ: found {set(self.files.keys())}, expected {set(expected.files.keys())}")

        for filename, keys in expected.files.items():
            if filename in self.files:
                missing = set(keys) - set(self.files[filename])
                extra = set(self.files[filename]) - set(keys)
                if missing:
                    differences.append(f"{filename}: missing keys {missing}")
                if extra:
                    differences.append(f"{filename}: new keys {extra}")

        if expected.message_keys and self.message_keys:
            missing = set(expected.message_keys) - set(self.message_keys)
            extra = set(self.message_keys) - set(expected.message_keys)
            if missing:
                differences.append(f"Messages: missing keys {missing}")
            if extra:
                differences.append(f"Messages: new keys {extra}")

        return (len(differences) == 0, differences)


# Expected schema definitions
CLAUDE_SCHEMA_V1 = SchemaFingerprint(
    provider='claude',
    version='1.0',
    files={
        'users.json': ['uuid', 'full_name', 'email_address'],
        'conversations.json': ['uuid', 'name', 'summary', 'created_at', 'updated_at', 'account', 'chat_messages'],
        'memories.json': ['conversations_memory', 'project_memories', 'account_uuid'],
        'projects.json': ['uuid', 'name', 'description', 'docs', 'created_at'],
    },
    message_keys=['uuid', 'text', 'sender', 'created_at', 'content', 'attachments', 'files'],
    content_types={'text', 'tool_use', 'tool_result', 'thinking', 'token_budget'},
)

CHATGPT_SCHEMA_V1 = SchemaFingerprint(
    provider='chatgpt',
    version='1.0',
    files={
        'conversations.json': ['title', 'create_time', 'update_time', 'mapping'],
    },
    message_keys=None,  # ChatGPT uses tree structure, not flat messages
    content_types=None,
)


def detect_schema(source_dir: Path, provider: str) -> SchemaFingerprint:
    """
    Analyze an export directory and create a schema fingerprint.
    """
    files_schema = {}
    message_keys = None
    content_types = set()

    # Check each JSON file
    for json_file in source_dir.glob('*.json'):
        if json_file.name.startswith('.'):
            continue

        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list) and data and isinstance(data[0], dict):
                files_schema[json_file.name] = list(data[0].keys())

                # For conversations, also extract message structure
                if json_file.name == 'conversations.json' and provider == 'claude':
                    if 'chat_messages' in data[0] and data[0]['chat_messages']:
                        message_keys = list(data[0]['chat_messages'][0].keys())
                        # Extract content types
                        for conv in data:
                            for msg in conv.get('chat_messages', []):
                                for content_item in msg.get('content', []):
                                    if 'type' in content_item:
                                        content_types.add(content_item['type'])

            elif isinstance(data, dict):
                files_schema[json_file.name] = list(data.keys())

        except (json.JSONDecodeError, KeyError):
            continue

    return SchemaFingerprint(
        provider=provider,
        version='detected',
        files=files_schema,
        message_keys=message_keys,
        content_types=content_types if content_types else None,
    )


def validate_schema(source_dir: Path, provider: str) -> tuple[bool, str, list[str]]:
    """
    Validate an export against the expected schema.

    Returns:
        (is_valid, version, list of warnings/differences)
    """
    detected = detect_schema(source_dir, provider)

    expected_schemas = {
        'claude': CLAUDE_SCHEMA_V1,
        'chatgpt': CHATGPT_SCHEMA_V1,
    }

    expected = expected_schemas.get(provider)
    if not expected:
        return (True, 'unknown', [f"No schema defined for provider: {provider}"])

    matches, differences = detected.matches(expected)

    if matches:
        return (True, expected.version, [])
    else:
        return (False, expected.version, differences)
