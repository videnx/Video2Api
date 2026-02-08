"""进程内 Worker：从 SQLite 队列领取任务并执行。"""
from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional
from uuid import uuid4

from app.db.sqlite import sqlite_db
from app.services.ixbrowser_service import ixbrowser_service
from app.services.sora_nurture_service import sora_nurture_service
from app.services.task_runtime import spawn

logger = logging.getLogger(__name__)


class WorkerRunner:
    def __init__(self) -> None:
        self.owner = f"worker-{uuid4().hex[:8]}"
        self._stop_event = asyncio.Event()
        self._sora_loop_task: Optional[asyncio.Task] = None
        self._nurture_loop_task: Optional[asyncio.Task] = None
        self._sora_running: Dict[int, asyncio.Task] = {}
        self._nurture_running: Optional[asyncio.Task] = None
        self._sora_lease_seconds = 120
        self._nurture_lease_seconds = 180

    async def start(self) -> None:
        self._stop_event.clear()
        try:
            sora_cnt = sqlite_db.requeue_stale_sora_jobs()
            nurture_cnt = sqlite_db.requeue_stale_nurture_batches()
            sqlite_db.create_event_log(
                source="system",
                action="worker.start",
                event="start",
                status="success",
                level="INFO",
                message=f"Worker 启动，恢复任务 sora={sora_cnt} nurture={nurture_cnt}",
                metadata={"owner": self.owner, "sora_requeued": sora_cnt, "nurture_requeued": nurture_cnt},
            )
        except Exception:  # noqa: BLE001
            logger.exception("Worker 启动恢复失败")

        self._sora_loop_task = spawn(
            self._sora_loop(),
            task_name="worker.sora.loop",
            metadata={"owner": self.owner},
        )
        self._nurture_loop_task = spawn(
            self._nurture_loop(),
            task_name="worker.nurture.loop",
            metadata={"owner": self.owner},
        )

    async def stop(self) -> None:
        self._stop_event.set()
        wait_tasks = []
        if self._sora_loop_task and not self._sora_loop_task.done():
            self._sora_loop_task.cancel()
            wait_tasks.append(self._sora_loop_task)
        if self._nurture_loop_task and not self._nurture_loop_task.done():
            self._nurture_loop_task.cancel()
            wait_tasks.append(self._nurture_loop_task)
        for task in list(self._sora_running.values()):
            if not task.done():
                task.cancel()
                wait_tasks.append(task)
        if self._nurture_running and not self._nurture_running.done():
            self._nurture_running.cancel()
            wait_tasks.append(self._nurture_running)
        if wait_tasks:
            await asyncio.gather(*wait_tasks, return_exceptions=True)

    async def _sora_loop(self) -> None:
        while not self._stop_event.is_set():
            # 清理已完成任务
            done_ids = [job_id for job_id, task in self._sora_running.items() if task.done()]
            for job_id in done_ids:
                self._sora_running.pop(job_id, None)

            max_parallel = max(1, int(getattr(ixbrowser_service, "sora_job_max_concurrency", 2) or 2))
            while len(self._sora_running) < max_parallel:
                row = sqlite_db.claim_next_sora_job(owner=self.owner, lease_seconds=self._sora_lease_seconds)
                if not row:
                    break
                job_id = int(row.get("id") or 0)
                if job_id <= 0:
                    break
                task = spawn(
                    self._run_one_sora_job(job_id),
                    task_name="worker.sora.run_one",
                    metadata={"owner": self.owner, "job_id": job_id},
                )
                self._sora_running[job_id] = task

            await asyncio.sleep(1.0)

    async def _run_one_sora_job(self, job_id: int) -> None:
        hb = spawn(
            self._heartbeat_sora_job(job_id),
            task_name="worker.sora.heartbeat",
            metadata={"owner": self.owner, "job_id": job_id},
        )
        try:
            await ixbrowser_service._run_sora_job(job_id)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            sqlite_db.update_sora_job(job_id, {"run_last_error": str(exc)})
            raise
        finally:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)
            sqlite_db.clear_sora_job_lease(job_id=job_id, owner=self.owner)

    async def _heartbeat_sora_job(self, job_id: int) -> None:
        while not self._stop_event.is_set():
            sqlite_db.heartbeat_sora_job_lease(
                job_id=job_id,
                owner=self.owner,
                lease_seconds=self._sora_lease_seconds,
            )
            await asyncio.sleep(max(5, int(self._sora_lease_seconds // 3)))

    async def _nurture_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._nurture_running and not self._nurture_running.done():
                await asyncio.sleep(1.0)
                continue

            row = sqlite_db.claim_next_sora_nurture_batch(owner=self.owner, lease_seconds=self._nurture_lease_seconds)
            if not row:
                await asyncio.sleep(1.0)
                continue

            batch_id = int(row.get("id") or 0)
            if batch_id <= 0:
                await asyncio.sleep(0.5)
                continue
            self._nurture_running = spawn(
                self._run_one_nurture_batch(batch_id),
                task_name="worker.nurture.run_one",
                metadata={"owner": self.owner, "batch_id": batch_id},
            )

    async def _run_one_nurture_batch(self, batch_id: int) -> None:
        hb = spawn(
            self._heartbeat_nurture_batch(batch_id),
            task_name="worker.nurture.heartbeat",
            metadata={"owner": self.owner, "batch_id": batch_id},
        )
        try:
            await sora_nurture_service._run_batch_impl(batch_id)  # noqa: SLF001
        except Exception as exc:  # noqa: BLE001
            sqlite_db.update_sora_nurture_batch(batch_id, {"error": str(exc)})
            raise
        finally:
            hb.cancel()
            await asyncio.gather(hb, return_exceptions=True)
            sqlite_db.clear_sora_nurture_batch_lease(batch_id=batch_id, owner=self.owner)

    async def _heartbeat_nurture_batch(self, batch_id: int) -> None:
        while not self._stop_event.is_set():
            sqlite_db.heartbeat_sora_nurture_batch_lease(
                batch_id=batch_id,
                owner=self.owner,
                lease_seconds=self._nurture_lease_seconds,
            )
            await asyncio.sleep(max(5, int(self._nurture_lease_seconds // 3)))


worker_runner = WorkerRunner()
