"""Submission ingestion: load a manuscript into a Paper.

Priority: LaTeX source > Markdown > plain text > PDF (PDF last because it loses
math notation; arXiv:2505.23824 shows LaTeX input yields more stable reviews).
PDF extraction is best-effort and optional (pypdf).
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import Paper


def load_paper(path: str | Path, paper_id: str | None = None) -> Paper:
    p = Path(path)
    pid = paper_id or p.stem
    suffix = p.suffix.lower()
    if suffix in {".tex"}:
        return _from_text(p.read_text(encoding="utf-8", errors="ignore"), pid, "latex")
    if suffix in {".md", ".markdown"}:
        return _from_text(p.read_text(encoding="utf-8", errors="ignore"), pid, "md")
    if suffix in {".txt"}:
        return _from_text(p.read_text(encoding="utf-8", errors="ignore"), pid, "text")
    if suffix == ".pdf":
        return _from_pdf(p, pid)
    # fallback
    return _from_text(p.read_text(encoding="utf-8", errors="ignore"), pid, "text")


def _from_text(text: str, pid: str, fmt: str) -> Paper:
    title = ""
    m = re.search(r"^\s*#\s+(.+)$", text, flags=re.MULTILINE)        # md
    if not m:
        m = re.search(r"\\title\{([^}]+)\}", text)                   # latex
    if m:
        title = m.group(1).strip()

    abstract = ""
    am = re.search(r"(?:abstract|摘要)[:：\s]*\n+(.+?)(?:\n#|\n\\section|\Z)",
                   text, flags=re.IGNORECASE | re.DOTALL)
    if am:
        abstract = am.group(1).strip()[:4000]

    sections = _split_sections(text, fmt)
    refs = _extract_refs(text)
    return Paper(paper_id=pid, title=title, abstract=abstract, sections=sections,
                 references=refs, raw_text=text, source_format=fmt)


def _split_sections(text: str, fmt: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    if fmt == "latex":
        parts = re.split(r"\\section\*?\{([^}]+)\}", text)
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i].strip()] = parts[i + 1].strip()[:40_000]
    else:
        parts = re.split(r"^\s*#{1,3}\s+(.+)$", text, flags=re.MULTILINE)
        for i in range(1, len(parts) - 1, 2):
            sections[parts[i].strip()] = parts[i + 1].strip()[:40_000]
    return sections


def _extract_refs(text: str) -> list[str]:
    m = re.search(r"(?:references|参考文献|bibliography)\s*\n(.+)\Z",
                  text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return []
    block = m.group(1)
    refs = re.findall(r"(?:^\s*\[\d+\].+|^\s*\d+\.\s+.+)", block, flags=re.MULTILINE)
    return [r.strip() for r in refs][:300]


def _from_pdf(p: Path, pid: str) -> Paper:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("PDF ingest needs pypdf: pip install pypdf") from e
    reader = PdfReader(str(p))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    paper = _from_text(text, pid, "pdf")
    return paper
