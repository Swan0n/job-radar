"""Настройки поиска. Живут в БД одной JSON-строкой и правятся из интерфейса."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

# Веса складываются в 100. Домен по умолчанию 0 — пользователь его не выбирал,
# но поле оставлено, чтобы можно было добавить вес из интерфейса.
DEFAULT_WEIGHTS = {"skills": 40, "experience": 35, "conditions": 25, "domain": 0}

ALL_SOURCES = ["work.ua", "robota.ua", "djinni.co", "dou.ua", "linkedin"]


@dataclass
class Settings:
    # --- что ищем ---
    queries: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)

    # --- где ---
    cities: list[str] = field(default_factory=lambda: ["Київ"])
    work_formats: list[str] = field(default_factory=lambda: ["remote", "hybrid", "office"])

    # --- деньги ---
    min_salary: int = 0
    salary_currency: str = "USD"          # USD | UAH — в чём задан min_salary
    uah_per_usd: float = 42.0             # курс для приведения вилок к одной валюте

    # --- отбор ---
    threshold: int = 70                   # основная вкладка
    secondary_threshold: int = 50         # вкладка «почти подходит»
    weights: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    # --- источники ---
    sources_enabled: dict[str, bool] = field(
        default_factory=lambda: {s: True for s in ALL_SOURCES}
    )

    # --- объёмы ---
    max_pages_per_query: int = 3
    first_scan_days: int = 30
    max_details_per_run: int = 120        # потолок на загрузку полных описаний

    # --- модели Claude ---
    scoring_model: str = "claude-sonnet-5"
    letter_model: str = "claude-sonnet-5"

    # --- расписание ---
    # Выключено: прогон только по кнопке, токены не тратятся без спроса.
    auto_schedule: bool = False
    schedule_time: str = "09:00"
    timezone: str = "Europe/Kyiv"
    notify_macos: bool = True

    def normalized_weights(self) -> dict[str, float]:
        """Приводит веса к сумме 1.0, даже если из интерфейса пришла ерунда."""
        w = {k: max(0, int(self.weights.get(k, 0))) for k in DEFAULT_WEIGHTS}
        total = sum(w.values())
        if total <= 0:
            w = dict(DEFAULT_WEIGHTS)
            total = sum(w.values())
        return {k: v / total for k, v in w.items()}

    def enabled_sources(self) -> list[str]:
        return [s for s in ALL_SOURCES if self.sources_enabled.get(s, True)]

    def min_salary_usd(self) -> float:
        if not self.min_salary:
            return 0.0
        if self.salary_currency.upper() == "UAH":
            return self.min_salary / max(self.uah_per_usd, 1.0)
        return float(self.min_salary)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "Settings":
        s = cls()
        if not raw:
            return s
        for key, value in raw.items():
            if hasattr(s, key) and value is not None:
                setattr(s, key, value)
        # добиваем словари на случай, если в БД лежит версия со старым набором ключей
        s.weights = {**DEFAULT_WEIGHTS, **(s.weights or {})}
        s.sources_enabled = {**{k: True for k in ALL_SOURCES}, **(s.sources_enabled or {})}
        return s
