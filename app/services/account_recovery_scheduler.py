"""账号恢复扫描调度器（基于 account_dispatch 配置）。"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional
from uuid import uuid4

from app.db.sqlite import sqlite_db
from app.models.settings import AccountDispatchSettings
from app.services.ixbrowser_service import ixbrowser_service
from app.services.task_runtime import spawn

logger = logging.getLogger(__name__)


class AccountRecoveryScheduler:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._settings = AccountDispatchSettings()
        self._owner = f"account-recovery-{uuid4().hex[:8]}"
        self._next_run_at = 0.0

    def apply_settings(self, settings: AccountDispatchSettings) -> None:
        self._settings = settings.model_copy(deep=True)
        interval = max(1, int(self._settings.auto_scan_interval_minutes or 10))
        self._next_run_at = max(self._next_run_at, time.time() + interval * 60)

    async def start(self) -> None:
        self._stop_event.clear()
        if self._task and not self._task.done():
            return
        if self._next_run_at <= 0:
            interval = max(1, int(self._settings.auto_scan_interval_minutes or 10))
            self._next_run_at = time.time() + interval * 60
        self._task = spawn(
            self._loop(),
            task_name="scheduler.account_recovery.loop",
            metadata={"owner": self._owner},
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("AccountRecoveryScheduler tick failed")
            await asyncio.sleep(10)

    async def _tick(self) -> None:
        cfg = self._settings
        if not cfg.enabled or not cfg.auto_scan_enabled:
            return
        now = time.time()
        if now < self._next_run_at:
            return

        interval_minutes = max(1, int(cfg.auto_scan_interval_minutes or 10))
        slot = int(now // (interval_minutes * 60))
        lock_key = f"scheduler.account_recovery.{slot}"
        if not sqlite_db.try_acquire_scheduler_lock(lock_key=lock_key, owner=self._owner, ttl_seconds=120):
            self._next_run_at = now + 5
            return

        group_title = str(cfg.auto_scan_group_title or "Sora").strip() or "Sora"
        self._next_run_at = now + interval_minutes * 60

        try:
            await ixbrowser_service.scan_group_sora_sessions(
                group_title=group_title,
                operator_user={"id": None, "username": "account_recovery_scheduler"},
                with_fallback=True,
                profile_ids=None,
            )
            sqlite_db.create_event_log(
                source="system",
                action="scheduler.account_recovery.trigger",
                event="trigger",
                status="success",
                level="INFO",
                message=f"账号恢复扫描成功: group={group_title}",
                metadata={"group_title": group_title, "interval_minutes": interval_minutes},
            )
        except Exception as exc:  # noqa: BLE001
            sqlite_db.create_event_log(
                source="system",
                action="scheduler.account_recovery.trigger",
                event="trigger",
                status="failed",
                level="WARN",
                message=f"账号恢复扫描失败: {exc}",
                metadata={"group_title": group_title, "interval_minutes": interval_minutes, "error": str(exc)},
            )


account_recovery_scheduler = AccountRecoveryScheduler()

