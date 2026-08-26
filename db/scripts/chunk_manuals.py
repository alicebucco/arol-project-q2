"""Extract locally stored AROL manuals into page-aware text chunks.

The resulting JSONL file is deliberately written under ``data/``: manuals and
their derived text are restricted course material and must never be committed.
Embeddings are intentionally out of scope for this script.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader


MANUAL_FILENAME = re.compile(r"^(?P<serial>[A-Za-z0-9-]+)_manual_EN\.pdf$", re.IGNORECASE)
SECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("safety", re.compile(r"\b(safety|warnings?|precautions?|hazards?)\b", re.IGNORECASE)),
    ("technical_data", re.compile(r"\b(technical data|specifications?|dimensions?)\b", re.IGNORECASE)),
    ("mechanical", re.compile(r"\b(mechanical|installation|assembly|lubrication)\b", re.IGNORECASE)),
    ("troubleshooting", re.compile(r"\b(troubleshooting|faults?|alarms?|diagnostics?)\b", re.IGNORECASE)),
)


@dataclass(frozen=True)
class ManualChunk:
    chunk_id: str
    machine_serial_number: str
    source_file: str
    page: int
    section: str
    chunk_index: int
    content: str


def normalise_text(text: str) -> str:
    """Turn PDF layout whitespace into ordinary searchable text."""
    return re.sub(r"\s+", " ", text).strip()


def classify_section(text: str, previous_section: str) -> str:
    """Keep the previous section until a recognised heading appears."""
    for section, pattern in SECTION_PATTERNS:
        if pattern.search(text):
            return section
    return previous_section


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text by words, retaining a short overlap for search continuity."""
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start
        length = 0
        while end < len(words):
            next_length = length + len(words[end]) + (1 if length else 0)
            if end > start and next_length > size:
                break
            length = next_length
            end += 1
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        overlap_words = 0
        new_start = end
        while new_start > start and overlap_words < overlap:
            new_start -= 1
            overlap_words += len(words[new_start]) + 1
        start = new_start
    return chunks


def serial_from_filename(path: Path) -> str:
    match = MANUAL_FILENAME.match(path.name)
    if not match:
        raise ValueError(
            f"Unexpected manual filename: {path.name}. "
            "Expected <serial>_manual_EN.pdf (for example 15610_manual_EN.pdf)."
        )
    return match.group("serial")


def chunk_manual(path: Path, size: int, overlap: int) -> list[ManualChunk]:
    serial = serial_from_filename(path)
    reader = PdfReader(path)
    if reader.is_encrypted:
        raise ValueError(f"Encrypted PDF is not supported: {path.name}")

    chunks: list[ManualChunk] = []
    section = "general"
    for page_number, pdf_page in enumerate(reader.pages, start=1):
        text = normalise_text(pdf_page.extract_text() or "")
        if not text:
            continue
        section = classify_section(text, section)
        for page_index, content in enumerate(split_text(text, size, overlap), start=1):
            chunks.append(
                ManualChunk(
                    chunk_id=f"{serial}-p{page_number}-{page_index}",
                    machine_serial_number=serial,
                    source_file=path.name,
                    page=page_number,
                    section=section,
                    chunk_index=page_index,
                    content=content,
                )
            )
    return chunks


def main() -> None:
    parser = argparse.ArgumentParser(description="Create local, page-aware chunks from AROL PDF manuals.")
    parser.add_argument("manuals_dir", type=Path, help="Directory containing <serial>_manual_EN.pdf files")
    parser.add_argument("--output", type=Path, required=True, help="Local JSONL output path, normally under data/")
    parser.add_argument("--chunk-size", type=int, default=1200, help="Maximum characters per chunk (default: 1200)")
    parser.add_argument("--overlap", type=int, default=150, help="Approximate overlap characters (default: 150)")
    args = parser.parse_args()

    if args.chunk_size <= 0 or args.overlap < 0 or args.overlap >= args.chunk_size:
        raise SystemExit("chunk-size must be positive and overlap must be between 0 and chunk-size - 1")
    if not args.manuals_dir.is_dir():
        raise SystemExit(f"Manuals directory not found: {args.manuals_dir}")

    manuals = sorted(args.manuals_dir.glob("*_manual_EN.pdf"))
    if not manuals:
        raise SystemExit(f"No *_manual_EN.pdf files found in {args.manuals_dir}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    total_chunks = 0
    with args.output.open("w", encoding="utf-8") as destination:
        for manual in manuals:
            chunks = chunk_manual(manual, args.chunk_size, args.overlap)
            for chunk in chunks:
                destination.write(json.dumps(asdict(chunk), ensure_ascii=False) + "\n")
            total_chunks += len(chunks)
            print(f"{manual.name}: {len(chunks)} chunks")
    print(f"Created {total_chunks} chunks in {args.output}")


if __name__ == "__main__":
    main()
