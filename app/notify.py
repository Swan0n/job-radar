"""Системное уведомление macOS через osascript."""
from __future__ import annotations

import asyncio
import logging
import shutil

log = logging.getLogger(__name__)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


async def macos_notification(title: str, message: str, subtitle: str = "") -> None:
    if not shutil.which("osascript"):
        return
    script = (f'display notification "{_escape(message)}" '
              f'with title "{_escape(title)}"')
    if subtitle:
        script += f' subtitle "{_escape(subtitle)}"'
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        _, err = await proc.communicate()
        if proc.returncode != 0:
            log.warning("уведомление не показалось: %s", err.decode()[:150])
    except Exception as e:
        log.warning("уведомление не показалось: %s", e)
