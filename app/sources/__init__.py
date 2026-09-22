"""Реестр источников. Порядок задаёт очерёдность обхода в прогоне."""
from . import djinni, dou, linkedin, robotaua, workua

MODULES = (workua, robotaua, djinni, dou, linkedin)
REGISTRY = {m.NAME: m for m in MODULES}

__all__ = ["REGISTRY", "MODULES", "workua", "robotaua", "djinni", "dou", "linkedin"]
