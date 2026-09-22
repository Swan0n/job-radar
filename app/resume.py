"""Чтение резюме из файла: PDF, DOCX, TXT, MD."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

RESUME_DIR = Path(__file__).resolve().parent.parent / "resume"
SUPPORTED = {".pdf", ".docx", ".txt", ".md", ".rtf"}


def find_resume_file() -> Path | None:
    """Берёт самый свежий подходящий файл из папки resume/."""
    if not RESUME_DIR.exists():
        return None
    files = [p for p in RESUME_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in SUPPORTED and not p.name.startswith(".")]
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _from_pdf(path)
    if suffix == ".docx":
        return _from_docx(path)
    return path.read_text(encoding="utf-8", errors="ignore")


def _from_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as e:                      # битая страница не должна ронять разбор
            log.warning("страница PDF не читается: %s", e)
    text = "\n".join(pages).strip()
    if len(text) < 80:
        raise ValueError(
            "Из PDF почти не извлёкся текст — похоже, это скан или картинка. "
            "Сохрани резюме как DOCX либо как PDF с текстовым слоем."
        )
    return text


def _from_docx(path: Path) -> str:
    import docx

    doc = docx.Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:                        # навыки часто верстают таблицей
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(p for p in parts if p.strip()).strip()
