"""Reading a dropped research-paper PDF: text, title, abstract and year, as far as they can be found."""

from __future__ import annotations

import io
import re

from backtester.errors import CodedError

MAX_BYTES = 60 * 1024 * 1024
MAX_PAGES = 60
MAX_CHARS = 600_000


class PaperError(CodedError):
    """A paper could not be read. The message says why."""
    code = "BT-PDF-000"


def _guess_title(meta_title: str | None, first_page: str, filename: str) -> str:
    bad = re.compile(r"^(untitled|microsoft word|document|\S+\.(pdf|docx?|tex))", re.I)
    if meta_title and len(meta_title.strip()) >= 8 and not bad.match(meta_title.strip()):
        return re.sub(r"\s+", " ", meta_title.strip())[:200]
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in first_page.splitlines()]
    skip = re.compile(r"^(https?://|www\.|doi|\d+$|abstract\b|page \d+|vol(ume)?\b|journal\b|working paper\b|ssrn\b|electronic copy)", re.I)
    lines = [ln for ln in lines if 12 <= len(ln) <= 200 and not skip.match(ln)]
    if lines:
        title = lines[0]
        connectors = {"of", "and", "in", "the", "a", "an", "for", "to", "with", "on", "by", "from", "at", "&", "or", "across", "under"}
        # a title often wraps onto a second line: when the first ends mid-phrase or the second continues in lower case
        if len(lines) > 1 and (lines[1][:1].islower() or title.split()[-1].lower() in connectors or title.endswith((":", "-", "\u2014"))):
            title = f"{title} {lines[1]}"
        return title[:200]
    return re.sub(r"[_-]+", " ", filename.rsplit(".", 1)[0]).strip().title() or "Untitled paper"


def _guess_abstract(text: str) -> str:
    """The paragraph after an 'Abstract' heading, up to the keywords line or the introduction."""
    m = re.search(r"(?is)\babstract\b[\s:.\u2014\u2013-]*(.{120,3000}?)(?:\n\s*(?:key\s*words?|index terms|jel\b|1\.?\s*introduction|introduction)\b|\Z)",
                  text[:20000])
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(1)).strip()[:2000]


def read_pdf(data: bytes, filename: str = "paper.pdf") -> dict:
    """Returns {title, authors, year, doi, abstract, pages, text, warning}."""
    if len(data) > MAX_BYTES:
        raise PaperError(f"{filename} is larger than {MAX_BYTES // 1024 // 1024} MB.", "BT-PDF-001")
    if not data.startswith(b"%PDF-"):
        raise PaperError(f"{filename} is not a PDF file.", "BT-PDF-002")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise PaperError("The PDF reader (pypdf) is not installed, so papers cannot be read yet. Close the dashboard and start it "
                         "again with start.sh (Mac: Start Backtester.command, Windows: start.bat), which installs it.", "BT-PDF-003")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise PaperError(f"{filename} is password-protected.", "BT-PDF-004")
        pages = len(reader.pages)
        chunks = []
        for i in range(min(pages, MAX_PAGES)):
            chunks.append(reader.pages[i].extract_text() or "")
        meta = reader.metadata
    except PaperError:
        raise
    except Exception as e:
        raise PaperError(f"{filename} could not be read as a PDF ({type(e).__name__}).", "BT-PDF-005")
    text = "\n\n".join(chunks)[:MAX_CHARS]
    first = chunks[0] if chunks else ""
    year = None
    created = getattr(meta, "creation_date", None) if meta else None
    ym = re.search(r"\b(19[5-9]\d|20[0-3]\d)\b", first[:3000])
    if ym:
        year = int(ym.group(1))
    elif created:
        year = created.year
    doi = re.search(r"10\.\d{4,9}/[^\s\"<>]+", text[:6000])
    return {
        "title": _guess_title(getattr(meta, "title", None) if meta else None, first, filename),
        "authors": (getattr(meta, "author", None) or "").strip() if meta else "",
        "year": year, "doi": doi.group(0).rstrip(".,;)") if doi else "", "abstract": _guess_abstract(text),
        "pages": pages, "text": text,
        "warning": None if len(text.strip()) > 200 else
        "Very little text could be extracted (a scanned PDF?). The file is saved, but Claude cannot read its contents.",
    }
