"""Locate the Tesseract tessdata directory used by tesserocr."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def resolve_tessdata_path(check_for_lang: Optional[str] = None) -> Optional[Path]:
    """Find a usable tessdata directory.

    Search order:
      1. ``TESSDATA_PREFIX`` environment variable
      2. project-root ``tessdata_backup/tessdata``
      3. project-root ``resource/tessdata``
      4. packaged ``_internal/Tesseract-OCR/tessdata``

    If ``check_for_lang`` is given, the directory must contain
    ``<check_for_lang>.traineddata``.
    """
    candidates: list[Path] = []

    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        candidates.append(Path(env))

    project_root = Path(__file__).resolve().parent.parent.parent
    candidates.extend(
        [
            project_root / "tessdata_backup" / "tessdata",
            project_root / "resource" / "tessdata",
            project_root / "_internal" / "Tesseract-OCR" / "tessdata",
        ]
    )

    required_file = (
        f"{check_for_lang}.traineddata" if check_for_lang else None
    )
    for path in candidates:
        if not path.is_dir():
            continue
        if required_file and not (path / required_file).is_file():
            continue
        return path
    return None
