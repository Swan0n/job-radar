"""Уровень английского, который требует вакансия: «B2», «C1»… или None, если не указан.

Без LLM — по тексту карточки и описания, поэтому работает и для неоценённых вакансий.
"""
from __future__ import annotations

import re

# «none» — работодатель прямо пишет, что английский не нужен (djinni: «Англійська - Немає»).
NONE = "none"
LEVELS = [NONE, "A1", "A2", "B1", "B2", "C1", "C2"]
NONE_RE = re.compile(r"англ\w*\s*[-–—:]\s*(?:немає|нет|не потрібн\w*|не нужн\w*)"
                     r"|english\s*[-–—:]\s*(?:none|not required)|english\s+is\s+not\s+required", re.I)
# Кириллица в «А2/В1/С1» — частая опечатка в украинских вакансиях.
CYR = str.maketrans("АВСавс", "ABCABC")

# Словесные уровни → CEFR. Порядок важен: длинные формы раньше коротких
# («upper-intermediate» содержит «intermediate»).
WORDS: list[tuple[str, str]] = [
    (r"pre[\s-]?intermediate", "A2"),
    (r"upper[\s-]?intermediate", "B2"),
    (r"intermediate", "B1"),
    (r"elementary|beginner", "A2"),
]
WORD_RE = re.compile("|".join(f"(?P<w{i}>{p})" for i, (p, _) in enumerate(WORDS)), re.I)
# B2, но не B2B/C2C и не часть артикула.
CEFR_RE = re.compile(r"(?<![\w/-])([ABCАВС][12])(?![\w])", re.I)
ENGLISH_RE = re.compile(r"english|англ\w*", re.I)

# Описательные уровни ловим только вплотную к слову «английский»: «fluent» само по себе —
# это и «fluent in Python», а «вільного» — «вільного читання документації».
NEAR: list[tuple[str, str]] = [
    (r"(?:fluent|advanced|excellent)\s+(?:in\s+)?english|english\s*(?:[-–—:]\s*|is\s+)?(?:fluent|advanced)", "C1"),
    (r"(?:вільн\w*|свободн\w*)\s+(?:володіння\s+|владение\s+)?англ\w*|англ\w*(?:\s+мова|\s+язык)?\s*[-–—:]?\s*(?:вільн\w*|свободн\w*)(?!\s+чит)", "C1"),
    (r"(?:розмовн\w*|разговорн\w*)\s+англ\w*|англ\w*(?:\s+мова|\s+язык)?\s*[-–—:]?\s*(?:розмовн\w*|разговорн\w*)", "B1"),
]
NEAR_RE = [(re.compile(p, re.I), lv) for p, lv in NEAR]

# Насколько далеко от слова «English/Англійська» может стоять уровень.
WINDOW = 90


# Между соседними уровнями одной вилки — только скобки, слэши и «или»: «Upper-Intermediate (B2/C1)».
JOINER_RE = re.compile(r"[\s()/,+.\-–—]*(?:or|або|или|to|до)?[\s()/,+.\-–—]*", re.I)


def _matches(chunk: str) -> list[tuple[int, int, str]]:
    """Все уровни в куске текста: (начало, конец, CEFR)."""
    out = [(m.start(1), m.end(1), m.group(1).upper().translate(CYR)) for m in CEFR_RE.finditer(chunk)]
    for m in WORD_RE.finditer(chunk):
        idx = int(next(k for k, v in m.groupdict().items() if v)[1:])
        out.append((m.start(), m.end(), WORDS[idx][1]))
    return sorted(out)


def _nearest_group(chunk: str, kw_start: int, kw_end: int) -> list[str]:
    """Уровни, относящиеся именно к этому «English»: ближайший и сцепленные с ним в вилку.
    Так «Англійська B2, німецька A2» даёт B2, а не A2."""
    ms = _matches(chunk)
    if not ms:
        return []
    dist = lambda m: kw_start - m[1] if m[1] <= kw_start else max(0, m[0] - kw_end)
    i = min(range(len(ms)), key=lambda k: dist(ms[k]))
    lo = hi = i
    while lo > 0 and JOINER_RE.fullmatch(chunk[ms[lo - 1][1]:ms[lo][0]]):
        lo -= 1
    while hi < len(ms) - 1 and JOINER_RE.fullmatch(chunk[ms[hi][1]:ms[hi + 1][0]]):
        hi += 1
    return [m[2] for m in ms[lo:hi + 1]]


def detect(text: str | None) -> str | None:
    """Минимальный требуемый уровень: «Upper-Intermediate (B2/C1) or higher» → B2."""
    if not text:
        return None
    found: list[str] = []
    for m in ENGLISH_RE.finditer(text):
        lo = max(0, m.start() - WINDOW)
        chunk = text[lo:m.end() + WINDOW]
        found += _nearest_group(chunk, m.start() - lo, m.end() - lo)
    for rx, lv in NEAR_RE:
        if rx.search(text):
            found.append(lv)
    if not found:
        # «Upper-Intermediate» без слова English почти всегда про английский;
        # «fluent», «advanced» без контекста — нет (fluent in Python, advanced Kubernetes).
        found = [m[2] for m in _matches(text) if m[2] in ("A2", "B1", "B2")
                 and re.search("intermediate", text[m[0]:m[1]], re.I)]
    if not found:
        return NONE if NONE_RE.search(text) else None
    return min(found, key=LEVELS.index)
