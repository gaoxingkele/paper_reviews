"""Strip MDPI publication metadata / page-UI noise from extracted article text.

The browser extraction includes the journal page chrome (publication dates, DOI,
"Open Access Article", reprint/citation-export UI, author-affiliation block).
That leaks "this is already published" into the reviewer (causing false desk
rejects) and adds noise. This keeps the manuscript body from the first real
section (Abstract / 1. Introduction) onward and drops obvious UI lines.

Writes corpus/energies_clean/<name>.txt.
"""
from __future__ import annotations
import re, pathlib

SRC = pathlib.Path("corpus/energies")
DST = pathlib.Path("corpus/energies_clean")
DST.mkdir(parents=True, exist_ok=True)

# lines that are clearly page UI / metadata
DROP_RE = re.compile(
    r"^(first_page|settings|Order Article Reprints|Open Access(Article)?|Article Menu|"
    r"Cite This|Subscribe|Submit to this Journal|Review for this Journal|Edit a Special Issue|"
    r"Download|Browse Figures|Versions Notes|Article Views|Citations|Table of Contents|"
    r"Share|Help|Format|BibTeX|EndNote|RIS|MDPI and ACS Style|AMA Style|Chicago/Turabian Style)\b",
    re.I)
META_RE = re.compile(
    r"^\s*(Published|Received|Revised|Accepted|Available online|Academic Editor|"
    r"Digital Object Identifier|DOI|https?://doi\.org|Volume\s+\d+|Issue\s+\d+|"
    r"This article belongs to|Special Issue|Keywords:?|Index Terms)\b", re.I)


def clean(text: str) -> str:
    # cut everything before the first Abstract / Introduction heading if present
    m = re.search(r"(?im)^\s*(abstract|1\.?\s+introduction)\b", text)
    head = ""
    if m:
        # keep the title (first non-empty line) as a header
        first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
        head = first_line.strip() + "\n\n"
        text = text[m.start():]
    lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            lines.append("")
            continue
        if DROP_RE.match(s) or META_RE.match(s):
            continue
        # drop author-affiliation numeric markers like "by X 1,*,Y 2"
        lines.append(ln)
    out = head + "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def main():
    n = 0
    for fp in sorted(SRC.glob("*.txt")):
        t = clean(fp.read_text(encoding="utf-8"))
        (DST / fp.name).write_text(t, encoding="utf-8")
        n += 1
        print(f"  {fp.name}: {fp.stat().st_size} -> {len(t)} chars")
    print(f"cleaned {n} files -> {DST}")


if __name__ == "__main__":
    main()
