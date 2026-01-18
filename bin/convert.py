#!/usr/bin/env python3
"""
Main entry point for converting chat history exports to Obsidian markdown.
Scans providers directory, tracks processed exports, and dispatches to converters.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Setup paths
BIN_DIR = Path(__file__).parent
PROJECT_DIR = BIN_DIR.parent
PROVIDERS_DIR = PROJECT_DIR / 'providers'
OUTPUT_DIR = PROJECT_DIR / 'obsidian_export'
REGISTRY_FILE = BIN_DIR / 'registry.json'

# Add bin to path for imports
sys.path.insert(0, str(BIN_DIR))

from providers.chatgpt import ChatGPTConverter
from providers.claude import ClaudeConverter
from providers.gemini import GeminiConverter


# Map provider names to converter classes
CONVERTERS = {
    'chatgpt': ChatGPTConverter,
    'claude': ClaudeConverter,
    'gemini': GeminiConverter,
}


def load_registry() -> dict:
    """Load the processing registry."""
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_registry(registry: dict):
    """Save the processing registry."""
    with open(REGISTRY_FILE, 'w') as f:
        json.dump(registry, f, indent=2)


def scan_exports() -> list[dict]:
    """
    Scan the providers directory for available exports.

    Returns:
        List of dicts with export info:
        {
            'provider': str,
            'date': str,
            'path': Path,
            'key': str,  # e.g., 'chatgpt/2026.01.15'
        }
    """
    exports = []

    if not PROVIDERS_DIR.exists():
        return exports

    for provider_dir in sorted(PROVIDERS_DIR.iterdir()):
        if not provider_dir.is_dir() or provider_dir.name.startswith('.'):
            continue

        provider_name = provider_dir.name

        for date_dir in sorted(provider_dir.iterdir()):
            if not date_dir.is_dir() or date_dir.name.startswith('.'):
                continue

            exports.append({
                'provider': provider_name,
                'date': date_dir.name,
                'path': date_dir,
                'key': f"{provider_name}/{date_dir.name}",
            })

    return exports


def display_menu(exports: list[dict], registry: dict) -> list[dict]:
    """
    Display menu of available exports and their status.

    Returns:
        List of unprocessed exports
    """
    print("\n" + "=" * 60)
    print("Chat History to Obsidian Converter")
    print("=" * 60)

    if not exports:
        print("\nNo exports found in providers/ directory.")
        return []

    print("\nAvailable exports:\n")

    unprocessed = []

    for i, export in enumerate(exports, 1):
        key = export['key']
        reg_entry = registry.get(key, {})
        is_processed = reg_entry.get('processed', False)

        if is_processed:
            processed_date = reg_entry.get('date', 'unknown')
            status = f"[DONE {processed_date}]"
        else:
            status = "[pending]"
            unprocessed.append(export)

        # Check if converter exists
        has_converter = export['provider'] in CONVERTERS
        converter_status = "" if has_converter else " (no converter yet)"

        print(f"  {i}. {export['provider']}/{export['date']} {status}{converter_status}")

    print()
    return unprocessed


def select_export(unprocessed: list[dict]) -> dict | None:
    """Prompt user to select an export to process."""
    if not unprocessed:
        print("All exports have been processed.")
        return None

    # Filter to only those with converters
    convertible = [e for e in unprocessed if e['provider'] in CONVERTERS]

    if not convertible:
        print("No pending exports have converters available yet.")
        return None

    if len(convertible) == 1:
        export = convertible[0]
        response = input(f"Process {export['key']}? [Y/n]: ").strip().lower()
        if response in ('', 'y', 'yes'):
            return export
        return None

    print("Pending exports with available converters:")
    for i, export in enumerate(convertible, 1):
        print(f"  {i}. {export['key']}")

    print()
    choice = input("Enter number to process (or 'q' to quit): ").strip()

    if choice.lower() == 'q':
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(convertible):
            return convertible[idx]
    except ValueError:
        pass

    print("Invalid selection.")
    return None


def run_conversion(export: dict) -> bool:
    """Run the converter for an export."""
    provider = export['provider']
    date = export['date']
    converter_class = CONVERTERS.get(provider)

    if not converter_class:
        print(f"No converter available for provider: {provider}")
        return False

    # Output mirrors input structure: obsidian_export/provider/date/
    export_output_dir = OUTPUT_DIR / provider / date

    print(f"\nConverting {export['key']}...")
    print("-" * 40)

    converter = converter_class(export['path'], export_output_dir)
    stats = converter.convert()

    print("-" * 40)
    print(f"Conversations: {stats['conversations_converted']}/{stats['conversations_total']}")
    if stats.get('memories_converted'):
        print(f"Memories: {stats['memories_converted']}")
    if stats.get('projects_converted'):
        print(f"Projects: {stats['projects_converted']}")
    print(f"Attachments copied: {stats['attachments_copied']}")

    if stats['errors']:
        print(f"Errors: {len(stats['errors'])}")
        for err in stats['errors'][:5]:  # Show first 5 errors
            print(f"  - {err}")
        if len(stats['errors']) > 5:
            print(f"  ... and {len(stats['errors']) - 5} more")

    return stats['conversations_converted'] > 0


def main():
    # Scan for exports
    exports = scan_exports()
    registry = load_registry()

    # Display menu
    unprocessed = display_menu(exports, registry)

    # Select and process
    export = select_export(unprocessed)

    if export:
        success = run_conversion(export)

        if success:
            # Update registry
            registry[export['key']] = {
                'processed': True,
                'date': datetime.now().strftime('%Y-%m-%d'),
            }
            save_registry(registry)
            print(f"\n✓ Marked {export['key']} as processed")

        export_output_dir = OUTPUT_DIR / export['provider'] / export['date']
        print(f"\nOutput: {export_output_dir}")


if __name__ == '__main__':
    main()
