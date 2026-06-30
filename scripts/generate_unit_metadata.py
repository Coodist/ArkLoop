#!/usr/bin/env python3
r"""
Standalone unit metadata generator.

This is mainly useful when the full `sync_new_resource.py` cannot reach GitHub
(e.g. network issues) but local copies of character_table.json / range_table.json
are already available.

Usage:
    .venv\Scripts\python scripts/generate_unit_metadata.py \
        --character-table C:\Users\assert\Downloads\ArknightsGameData-master\zh_CN\gamedata\excel\character_table.json \
        --range-table C:\Users\assert\Downloads\ArknightsGameData-master\zh_CN\gamedata\excel\range_table.json \
        --operator-mapping resource/operator_mapping.json \
        --output new_resource/unit_metadata.json
"""

import argparse
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from pathlib import Path
from sync_new_resource import generate_unit_metadata


def main():
    parser = argparse.ArgumentParser(description="Generate unit_metadata.json from game data tables.")
    parser.add_argument(
        "--character-table",
        type=Path,
        required=True,
        help="Path to character_table.json",
    )
    parser.add_argument(
        "--range-table",
        type=Path,
        required=True,
        help="Path to range_table.json",
    )
    parser.add_argument(
        "--operator-mapping",
        type=Path,
        default=Path(project_root) / "resource" / "operator_mapping.json",
        help="Path to operator_mapping.json (default: resource/operator_mapping.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(project_root) / "new_resource" / "unit_metadata.json",
        help="Output path (default: new_resource/unit_metadata.json)",
    )
    args = parser.parse_args()

    missing = [p for p in (args.character_table, args.range_table, args.operator_mapping) if not p.exists()]
    if missing:
        for p in missing:
            print(f"Error: file not found: {p}")
        sys.exit(1)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    generate_unit_metadata(
        character_path=args.character_table,
        range_path=args.range_table,
        operator_mapping_path=args.operator_mapping,
        output_path=args.output,
    )
    print(f"Done: {args.output}")


if __name__ == "__main__":
    main()
