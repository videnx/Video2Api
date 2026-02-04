"""
ixBrowser 本地 API 服务
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.core.config import settings
from app.db.sqlite import sqlite_db
from app.models.ixbrowser import (
    IXBrowserGenerateJob,
    IXBrowserGroup,
    IXBrowserGroupWindows,
    IXBrowserGenerateRequest,
    IXBrowserGenerateJobCreateResponse,
    IXBrowserScanRunSummary,
    IXBrowserSessionScanItem,
    IXBrowserSessionScanResponse,
    IXBrowserWindow,
)

logger = logging.getLogger(__name__)


class IXBrowserServiceError(Exception):
    """ixBrowser 服务通用异常"""


class IXBrowserConnectionError(IXBrowserServiceError):
    """ixBrowser 连接异常"""


class IXBrowserAPIError(IXBrowserServiceError):
    """ixBrowser 业务异常"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(f"ixBrowser API error {code}: {message}")


class IXBrowserNotFoundError(IXBrowserServiceError):
    """ixBrowser 资源不存在"""


class IXBrowserService:
    """ixBrowser 本地接口封装"""

    scan_history_limit = 10
    generate_timeout_seconds = 30 * 60
    generate_poll_interval_seconds = 6

    async def list_groups(self) -> List[IXBrowserGroup]:
        """
        获取全部分组列表（自动翻页）
        """
        page = 1
        limit = 200
        total = None
        groups: List[IXBrowserGroup] = []
        seen_ids = set()

        while total is None or len(groups) < total:
            payload = {
                "page": page,
                "limit": limit,
                "title": ""
            }
            data = await self._post("/api/v2/group-list", payload)

            data_section = data.get("data", {}) if isinstance(data, dict) else {}
            if total is None:
                total = int(data_section.get("total", 0) or 0)

            page_items = data_section.get("data", [])
            if not isinstance(page_items, list) or not page_items:
                break

            for item in page_items:
                if not isinstance(item, dict):
                    continue

                group_id = item.get("id")
                title = item.get("title")
                if group_id is None or title is None:
                    continue

                try:
                    normalized_id = int(group_id)
                except (TypeError, ValueError):
                    continue

                if normalized_id in seen_ids:
                    continue

                seen_ids.add(normalized_id)
                groups.append(IXBrowserGroup(id=normalized_id, title=str(title)))

            # 保险兜底：接口 total 异常时，防止死循环
            if len(page_items) < limit:
                break
            page += 1

        # 按 id 排序，确保前端展示稳定
        return sorted(groups, key=lambda group: group.id)

    async def list_group_windows(self) -> List[IXBrowserGroupWindows]:
        """
        获取分组及其窗口列表
        """
        groups = await self.list_groups()
        profiles = await self._list_profiles()

        grouped: Dict[int, IXBrowserGroupWindows] = {
            group.id: IXBrowserGroupWindows(id=group.id, title=group.title)
            for group in groups
        }

        for profile in profiles:
            group_id = profile.get("group_id")
            profile_id = profile.get("profile_id")
            name = profile.get("name")

            if group_id is None or profile_id is None or name is None:
                continue

            try:
                group_id_int = int(group_id)
                profile_id_int = int(profile_id)
            except (TypeError, ValueError):
                continue

            if group_id_int not in grouped:
                group_name = str(profile.get("group_name") or "").strip() or "未知分组"
                grouped[group_id_int] = IXBrowserGroupWindows(id=group_id_int, title=group_name)

            grouped[group_id_int].windows.append(
                IXBrowserWindow(profile_id=profile_id_int, name=str(name))
            )

        result = sorted(grouped.values(), key=lambda item: item.id)
        for item in result:
            item.windows.sort(key=lambda window: window.profile_id, reverse=True)
            item.window_count = len(item.windows)

        return result

    async def _list_profiles(self) -> List[dict]:
        """
        获取全部窗口列表（自动翻页）
        """
        page = 1
        limit = 200
        total = None
        profiles: List[dict] = []
        seen_ids = set()

        while total is None or len(profiles) < total:
            payload = {
                "profile_id": 0,
                "name": "",
                "group_id": 0,
                "tag_id": 0,
                "page": page,
                "limit": limit
            }
            data = await self._post("/api/v2/profile-list", payload)

            data_section = data.get("data", {}) if isinstance(data, dict) else {}
            if total is None:
                total = int(data_section.get("total", 0) or 0)

            page_items = data_section.get("data", [])
            if not isinstance(page_items, list) or not page_items:
                break

            for item in page_items:
                if not isinstance(item, dict):
                    continue

                profile_id = item.get("profile_id")
                try:
                    profile_id_int = int(profile_id)
                except (TypeError, ValueError):
                    continue

                if profile_id_int in seen_ids:
                    continue

                seen_ids.add(profile_id_int)
                profiles.append(
                    {
                        "profile_id": profile_id_int,
                        "name": str(item.get("name") or f"窗口-{profile_id_int}"),
                        "group_id": item.get("group_id"),
                        "group_name": item.get("group_name"),
                    }
                )

            # 保险兜底：接口 total 异常时，防止死循环
            if len(page_items) < limit:
                break
            page += 1

        return profiles

    async def scan_group_sora_sessions(
        self,
        group_title: str = "Sora",
        operator_user: Optional[dict] = None,
        with_fallback: bool = True,
    ) -> IXBrowserSessionScanResponse:
        """
        打开指定分组窗口，抓取 sora.chatgpt.com 的 session 接口响应
        """
        groups = await self.list_group_windows()
        target = self._find_group_by_title(groups, group_title)
        if not target:
            raise IXBrowserNotFoundError(f"未找到分组：{group_title}")

        results: List[IXBrowserSessionScanItem] = []

        async with async_playwright() as playwright:
            for window in target.windows:
                started_at = time.perf_counter()
                close_success = False
                success = False
                session_status: Optional[int] = None
                account: Optional[str] = None
                session_obj: Optional[dict] = None
                session_raw: Optional[str] = None
                quota_remaining_count: Optional[int] = None
                quota_total_count: Optional[int] = None
                quota_reset_at: Optional[str] = None
                quota_source: Optional[str] = None
                quota_payload: Optional[dict] = None
                quota_error: Optional[str] = None
                error: Optional[str] = None
                browser = None

                try:
                    open_data = await self._open_profile(window.profile_id, restart_if_opened=True)
                    ws_endpoint = open_data.get("ws")
                    if not ws_endpoint:
                        debugging_address = open_data.get("debugging_address")
                        if debugging_address:
                            ws_endpoint = f"http://{debugging_address}"

                    if not ws_endpoint:
                        raise IXBrowserConnectionError("打开窗口成功，但未返回调试地址（ws/debugging_address）")

                    browser = await playwright.chromium.connect_over_cdp(
                        ws_endpoint,
                        timeout=15_000
                    )
                    session_status, session_obj, session_raw = await self._fetch_sora_session(browser)
                    account = self._extract_account(session_obj)
                    try:
                        quota_info = await self._fetch_sora_quota(browser, session_obj)
                        quota_remaining_count = quota_info.get("remaining_count")
                        quota_total_count = quota_info.get("total_count")
                        quota_reset_at = quota_info.get("reset_at")
                        quota_source = quota_info.get("source")
                        quota_payload = quota_info.get("payload")
                        quota_error = quota_info.get("error")
                    except Exception as quota_exc:  # noqa: BLE001
                        quota_error = str(quota_exc)
                    success = session_status == 200 and session_obj is not None
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)
                finally:
                    if browser:
                        try:
                            await browser.close()
                        except Exception:  # noqa: BLE001
                            pass

                    try:
                        close_success = await self._close_profile(window.profile_id)
                    except Exception as close_exc:  # noqa: BLE001
                        close_success = False
                        if not error:
                            error = f"窗口关闭失败：{close_exc}"

                duration_ms = int((time.perf_counter() - started_at) * 1000)
                results.append(
                    IXBrowserSessionScanItem(
                        profile_id=window.profile_id,
                        window_name=window.name,
                        group_id=target.id,
                        group_title=target.title,
                        session_status=session_status,
                        account=account,
                        session=session_obj,
                        session_raw=session_raw,
                        quota_remaining_count=quota_remaining_count,
                        quota_total_count=quota_total_count,
                        quota_reset_at=quota_reset_at,
                        quota_source=quota_source,
                        quota_payload=quota_payload,
                        quota_error=quota_error,
                        success=success,
                        close_success=close_success,
                        error=error,
                        duration_ms=duration_ms,
                    )
                )

        success_count = sum(1 for item in results if item.success)
        failed_count = len(results) - success_count
        response = IXBrowserSessionScanResponse(
            group_id=target.id,
            group_title=target.title,
            total_windows=len(results),
            success_count=success_count,
            failed_count=failed_count,
            results=results,
        )
        run_id = self._save_scan_response(
            response=response,
            operator_user=operator_user,
            keep_latest_runs=self.scan_history_limit,
        )
        response.run_id = run_id
        run_row = sqlite_db.get_ixbrowser_scan_run(run_id)
        response.scanned_at = str(run_row.get("scanned_at")) if run_row else None
        if with_fallback:
            self._apply_fallback_from_history(response)
            if response.run_id is not None:
                sqlite_db.update_ixbrowser_scan_run_fallback_count(response.run_id, response.fallback_applied_count)
        return response

    async def create_sora_generate_job(
        self,
        request: IXBrowserGenerateRequest,
        operator_user: Optional[dict] = None,
    ) -> IXBrowserGenerateJobCreateResponse:
        """
        创建 Sora 文生视频任务（单窗口）
        """
        prompt = request.prompt.strip()
        if not prompt:
            raise IXBrowserServiceError("提示词不能为空")
        if len(prompt) > 4000:
            raise IXBrowserServiceError("提示词过长（最多 4000 字符）")

        duration_to_frames = {
            "10s": 300,
            "15s": 450,
            "25s": 750,
        }
        if request.duration not in duration_to_frames:
            raise IXBrowserServiceError("时长仅支持：10s、15s、25s")
        if request.aspect_ratio not in {"landscape", "portrait"}:
            raise IXBrowserServiceError("比例仅支持：landscape、portrait")

        target_window = await self._get_window_from_sora_group(request.profile_id)
        if not target_window:
            raise IXBrowserNotFoundError(f"窗口 {request.profile_id} 不在 Sora 分组中")

        job_id = sqlite_db.create_ixbrowser_generate_job(
            {
                "profile_id": request.profile_id,
                "window_name": target_window.name,
                "group_title": "Sora",
                "prompt": prompt,
                "duration": request.duration,
                "aspect_ratio": request.aspect_ratio,
                "status": "queued",
                "operator_user_id": operator_user.get("id") if isinstance(operator_user, dict) else None,
                "operator_username": operator_user.get("username") if isinstance(operator_user, dict) else None,
            }
        )

        async def _runner():
            await self._run_sora_generate_job(job_id)

        asyncio.create_task(_runner())
        job = self.get_sora_generate_job(job_id)
        return IXBrowserGenerateJobCreateResponse(job=job)

    def get_sora_generate_job(self, job_id: int) -> IXBrowserGenerateJob:
        row = sqlite_db.get_ixbrowser_generate_job(job_id)
        if not row:
            raise IXBrowserNotFoundError(f"未找到生成任务：{job_id}")
        return self._build_generate_job(row)

    def list_sora_generate_jobs(
        self,
        group_title: str = "Sora",
        limit: int = 20,
        profile_id: Optional[int] = None,
    ) -> List[IXBrowserGenerateJob]:
        rows = sqlite_db.list_ixbrowser_generate_jobs(
            group_title=group_title,
            limit=min(max(limit, 1), 100),
            profile_id=profile_id,
        )
        return [self._build_generate_job(row) for row in rows]

    async def _run_sora_generate_job(self, job_id: int) -> None:
        row = sqlite_db.get_ixbrowser_generate_job(job_id)
        if not row:
            return

        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sqlite_db.update_ixbrowser_generate_job(
            job_id,
            {
                "status": "running",
                "started_at": started_at,
                "error": None,
            }
        )
        t0 = time.perf_counter()

        try:
            final = await self._submit_and_monitor_sora_video(
                profile_id=int(row["profile_id"]),
                prompt=str(row["prompt"]),
                duration=str(row["duration"]),
                aspect_ratio=str(row["aspect_ratio"]),
                max_submit_attempts=2,  # 提交失败重试一次
                timeout_seconds=self.generate_timeout_seconds,
                poll_interval_seconds=self.generate_poll_interval_seconds,
                job_id=job_id,
            )

            status = "completed" if final.get("status") == "completed" else "failed"
            sqlite_db.update_ixbrowser_generate_job(
                job_id,
                {
                    "status": status,
                    "task_id": final.get("task_id"),
                    "task_url": final.get("task_url"),
                    "error": final.get("error"),
                    "poll_attempts": final.get("poll_attempts"),
                    "submit_attempts": final.get("submit_attempts"),
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
        except Exception as exc:  # noqa: BLE001
            sqlite_db.update_ixbrowser_generate_job(
                job_id,
                {
                    "status": "failed",
                    "error": str(exc),
                    "elapsed_ms": int((time.perf_counter() - t0) * 1000),
                    "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

    async def _submit_and_monitor_sora_video(
        self,
        profile_id: int,
        prompt: str,
        duration: str,
        aspect_ratio: str,
        max_submit_attempts: int,
        timeout_seconds: int,
        poll_interval_seconds: int,
        job_id: int,
    ) -> Dict[str, Any]:
        duration_to_frames = {
            "10s": 300,
            "15s": 450,
            "25s": 750,
        }
        n_frames = duration_to_frames[duration]

        open_data = await self._open_profile_with_retry(profile_id, max_attempts=3)
        ws_endpoint = open_data.get("ws")
        if not ws_endpoint:
            debugging_address = open_data.get("debugging_address")
            if debugging_address:
                ws_endpoint = f"http://{debugging_address}"
        if not ws_endpoint:
            raise IXBrowserConnectionError("打开窗口成功，但未返回调试地址（ws/debugging_address）")

        submit_attempts = 0
        poll_attempts = 0
        reconnect_attempts = 0
        max_reconnect_attempts = 3
        browser = None
        page = None
        task_id: Optional[str] = None
        task_url: Optional[str] = None
        access_token: Optional[str] = None

        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.connect_over_cdp(ws_endpoint, timeout=20_000)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()

                await page.goto("https://sora.chatgpt.com/drafts", wait_until="domcontentloaded", timeout=40_000)
                await page.wait_for_timeout(1500)

                cookies = await context.cookies("https://sora.chatgpt.com")
                device_id = next(
                    (cookie.get("value") for cookie in cookies if cookie.get("name") == "oai-did" and cookie.get("value")),
                    None
                ) or str(uuid4())

                last_submit_error: Optional[str] = None
                for attempt in range(1, max_submit_attempts + 1):
                    submit_attempts = attempt
                    sqlite_db.update_ixbrowser_generate_job(job_id, {"submit_attempts": submit_attempts})
                    submit_data = await self._submit_video_request_from_page(
                        page=page,
                        prompt=prompt,
                        aspect_ratio=aspect_ratio,
                        n_frames=n_frames,
                        device_id=device_id,
                    )
                    task_id = submit_data.get("task_id")
                    task_url = submit_data.get("task_url")
                    access_token = submit_data.get("access_token")
                    submit_error = submit_data.get("error")

                    if task_id:
                        break

                    last_submit_error = submit_error or "提交生成失败"
                    if attempt < max_submit_attempts:
                        await page.wait_for_timeout(1500)
                        continue

                if not task_id:
                    raise IXBrowserServiceError(last_submit_error or "提交生成失败")

                sqlite_db.update_ixbrowser_generate_job(
                    job_id,
                    {
                        "task_id": task_id,
                        "task_url": task_url,
                        "status": "running",
                        "error": None,
                    }
                )

                if not access_token:
                    access_token = await self._get_access_token_from_page(page)
                if not access_token:
                    raise IXBrowserServiceError("提交成功但未获取到 accessToken，无法监听任务状态")

                started = time.perf_counter()
                while True:
                    if (time.perf_counter() - started) >= timeout_seconds:
                        return {
                            "status": "failed",
                            "task_id": task_id,
                            "task_url": task_url,
                            "error": f"任务监听超时（>{timeout_seconds}s）",
                            "submit_attempts": submit_attempts,
                            "poll_attempts": poll_attempts,
                        }

                    poll_attempts += 1
                    try:
                        state = await self._poll_sora_task_from_page(
                            page=page,
                            task_id=task_id,
                            access_token=access_token,
                        )
                    except Exception as poll_exc:  # noqa: BLE001
                        if self._is_page_closed_error(poll_exc) and reconnect_attempts < max_reconnect_attempts:
                            reconnect_attempts += 1
                            try:
                                if browser:
                                    await browser.close()
                            except Exception:  # noqa: BLE001
                                pass
                            browser, page, access_token = await self._reconnect_sora_page(playwright, profile_id)
                            continue
                        return {
                            "status": "failed",
                            "task_id": task_id,
                            "task_url": task_url,
                            "error": f"任务轮询失败：{poll_exc}",
                            "submit_attempts": submit_attempts,
                            "poll_attempts": poll_attempts,
                        }
                    sqlite_db.update_ixbrowser_generate_job(job_id, {"poll_attempts": poll_attempts})

                    maybe_url = state.get("task_url")
                    if maybe_url:
                        task_url = maybe_url

                    if state.get("state") == "completed":
                        return {
                            "status": "completed",
                            "task_id": task_id,
                            "task_url": task_url,
                            "error": None,
                            "submit_attempts": submit_attempts,
                            "poll_attempts": poll_attempts,
                        }
                    if state.get("state") == "failed":
                        return {
                            "status": "failed",
                            "task_id": task_id,
                            "task_url": task_url,
                            "error": state.get("error") or "任务失败",
                            "submit_attempts": submit_attempts,
                            "poll_attempts": poll_attempts,
                        }

                    try:
                        await page.wait_for_timeout(poll_interval_seconds * 1000)
                    except Exception as wait_exc:  # noqa: BLE001
                        if self._is_page_closed_error(wait_exc) and reconnect_attempts < max_reconnect_attempts:
                            reconnect_attempts += 1
                            try:
                                if browser:
                                    await browser.close()
                            except Exception:  # noqa: BLE001
                                pass
                            browser, page, access_token = await self._reconnect_sora_page(playwright, profile_id)
                            continue
                        return {
                            "status": "failed",
                            "task_id": task_id,
                            "task_url": task_url,
                            "error": f"任务监听中断：{wait_exc}",
                            "submit_attempts": submit_attempts,
                            "poll_attempts": poll_attempts,
                        }
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:  # noqa: BLE001
                    pass

    async def _submit_video_request_from_page(
        self,
        page,
        prompt: str,
        aspect_ratio: str,
        n_frames: int,
        device_id: str,
    ) -> Dict[str, Optional[str]]:
        try:
            await page.wait_for_function(
                "typeof window.SentinelSDK !== 'undefined' && typeof window.SentinelSDK.token === 'function'",
                timeout=30_000
            )
        except PlaywrightTimeoutError as exc:
            raise IXBrowserServiceError("页面未加载 SentinelSDK，无法提交生成请求") from exc

        data = await page.evaluate(
            """
            async ({prompt, aspectRatio, nFrames, deviceId}) => {
              const err = (message) => ({ task_id: null, task_url: null, access_token: null, error: message });
              try {
                const sessionResp = await fetch("https://sora.chatgpt.com/api/auth/session", {
                  method: "GET",
                  credentials: "include"
                });
                const sessionText = await sessionResp.text();
                let sessionJson = null;
                try { sessionJson = JSON.parse(sessionText); } catch (e) {}
                const accessToken = sessionJson?.accessToken || null;
                if (!accessToken) return err("session 中未找到 accessToken");

                const sentinelRaw = await window.SentinelSDK.token("sora_2_create_task__auto", deviceId);
                if (!sentinelRaw) return err("获取 Sentinel token 失败");

                let sentinelObj = sentinelRaw;
                if (typeof sentinelRaw === "string") {
                  try { sentinelObj = JSON.parse(sentinelRaw); } catch (e) { sentinelObj = null; }
                }
                const sentinelToken = typeof sentinelRaw === "string"
                  ? sentinelRaw
                  : JSON.stringify(sentinelRaw);

                const finalDeviceId = sentinelObj?.id || deviceId;
                const payload = {
                  kind: "video",
                  prompt,
                  orientation: aspectRatio,
                  size: "small",
                  n_frames: nFrames,
                  model: "sy_8",
                  inpaint_items: []
                };

                const createResp = await fetch("https://sora.chatgpt.com/backend/nf/create", {
                  method: "POST",
                  credentials: "include",
                  headers: {
                    "Authorization": `Bearer ${accessToken}`,
                    "OpenAI-Sentinel-Token": sentinelToken,
                    "OAI-Device-Id": finalDeviceId,
                    "OAI-Language": "en-US",
                    "Content-Type": "application/json"
                  },
                  body: JSON.stringify(payload)
                });
                const text = await createResp.text();
                let json = null;
                try { json = JSON.parse(text); } catch (e) {}
                const taskId = json?.id || json?.task_id || json?.task?.id || null;
                const taskUrl = taskId ? `https://sora.chatgpt.com/g/${taskId}` : null;
                if (!taskId) {
                  const message = json?.error?.message || json?.message || text || `nf/create 状态码 ${createResp.status}`;
                  return err(String(message).slice(0, 300));
                }
                return {
                  task_id: taskId,
                  task_url: taskUrl,
                  access_token: accessToken,
                  error: null
                };
              } catch (e) {
                return err(String(e));
              }
            }
            """,
            {
                "prompt": prompt,
                "aspectRatio": aspect_ratio,
                "nFrames": n_frames,
                "deviceId": device_id,
            }
        )
        if not isinstance(data, dict):
            return {"task_id": None, "task_url": None, "access_token": None, "error": "提交返回格式异常"}
        return {
            "task_id": data.get("task_id"),
            "task_url": data.get("task_url"),
            "access_token": data.get("access_token"),
            "error": data.get("error"),
        }

    async def _get_access_token_from_page(self, page) -> Optional[str]:
        data = await page.evaluate(
            """
            async () => {
              try {
                const resp = await fetch("https://sora.chatgpt.com/api/auth/session", {
                  method: "GET",
                  credentials: "include"
                });
                const text = await resp.text();
                let json = null;
                try { json = JSON.parse(text); } catch (e) {}
                return json?.accessToken || null;
              } catch (e) {
                return null;
              }
            }
            """
        )
        if isinstance(data, str) and data.strip():
            return data.strip()
        return None

    async def _poll_sora_task_from_page(
        self,
        page,
        task_id: str,
        access_token: str,
    ) -> Dict[str, Optional[str]]:
        data = await page.evaluate(
            """
            async ({taskId, accessToken}) => {
              const headers = {
                "Authorization": `Bearer ${accessToken}`,
                "Accept": "application/json"
              };
              const fail = (msg) => ({ state: "failed", error: msg, task_url: null });

              try {
                const pendingResp = await fetch("https://sora.chatgpt.com/backend/nf/pending/v2", {
                  method: "GET",
                  credentials: "include",
                  headers
                });
                const pendingText = await pendingResp.text();
                let pendingJson = null;
                try { pendingJson = JSON.parse(pendingText); } catch (e) {}
                if (pendingResp.status === 200 && Array.isArray(pendingJson)) {
                  const foundPending = pendingJson.find((item) => item?.id === taskId);
                  if (foundPending) {
                    return { state: "processing", error: null, task_url: null };
                  }
                }
              } catch (e) {}

              try {
                const draftsResp = await fetch("https://sora.chatgpt.com/backend/project_y/profile/drafts?limit=30", {
                  method: "GET",
                  credentials: "include",
                  headers
                });
                const draftsText = await draftsResp.text();
                let draftsJson = null;
                try { draftsJson = JSON.parse(draftsText); } catch (e) {}
                const items = draftsJson?.items;
                if (!Array.isArray(items)) {
                  return { state: "processing", error: null, task_url: null };
                }
                const target = items.find((item) => item?.task_id === taskId);
                if (!target) {
                  return { state: "processing", error: null, task_url: null };
                }

                const reason = target.reason_str || target.markdown_reason_str || null;
                const kind = target.kind || "";
                const taskUrl = target.url || target.downloadable_url || null;
                if (reason && String(reason).trim()) {
                  return fail(String(reason));
                }
                if (kind === "sora_content_violation") {
                  return fail("内容审核未通过");
                }
                if (taskUrl) {
                  return { state: "completed", error: null, task_url: taskUrl };
                }
                return { state: "processing", error: null, task_url: null };
              } catch (e) {
                return fail(String(e));
              }
            }
            """,
            {
                "taskId": task_id,
                "accessToken": access_token,
            }
        )
        if not isinstance(data, dict):
            return {"state": "processing", "error": None, "task_url": None}
        state = data.get("state")
        if state not in {"processing", "completed", "failed"}:
            state = "processing"
        return {
            "state": state,
            "error": data.get("error"),
            "task_url": data.get("task_url"),
        }

    def _build_generate_job(self, row: dict) -> IXBrowserGenerateJob:
        return IXBrowserGenerateJob(
            job_id=int(row["id"]),
            profile_id=int(row["profile_id"]),
            window_name=row.get("window_name"),
            group_title=str(row.get("group_title") or "Sora"),
            prompt=str(row.get("prompt") or ""),
            duration=str(row.get("duration") or "10s"),
            aspect_ratio=str(row.get("aspect_ratio") or "landscape"),
            status=str(row.get("status") or "queued"),
            task_id=row.get("task_id"),
            task_url=row.get("task_url"),
            error=row.get("error"),
            elapsed_ms=row.get("elapsed_ms"),
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            operator_username=row.get("operator_username"),
        )

    async def _open_profile_with_retry(self, profile_id: int, max_attempts: int = 3) -> dict:
        last_error: Optional[Exception] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self._open_profile(profile_id, restart_if_opened=True)
            except (IXBrowserConnectionError, IXBrowserAPIError) as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                await asyncio.sleep(1.2)
        if last_error:
            raise last_error
        raise IXBrowserConnectionError("打开窗口失败")

    async def _reconnect_sora_page(self, playwright, profile_id: int):
        open_data = await self._open_profile_with_retry(profile_id, max_attempts=2)
        ws_endpoint = open_data.get("ws")
        if not ws_endpoint:
            debugging_address = open_data.get("debugging_address")
            if debugging_address:
                ws_endpoint = f"http://{debugging_address}"
        if not ws_endpoint:
            raise IXBrowserConnectionError("重连窗口失败：未返回调试地址")

        browser = await playwright.chromium.connect_over_cdp(ws_endpoint, timeout=20_000)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto("https://sora.chatgpt.com/drafts", wait_until="domcontentloaded", timeout=40_000)
        await page.wait_for_timeout(1000)
        access_token = await self._get_access_token_from_page(page)
        if not access_token:
            raise IXBrowserServiceError("重连后未获取到 accessToken")
        return browser, page, access_token

    def _is_page_closed_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        keywords = [
            "target page, context or browser has been closed",
            "target closed",
            "context has been closed",
            "browser has been closed",
            "has been closed",
            "connection closed",
        ]
        return any(token in message for token in keywords)

    def get_latest_sora_scan(
        self,
        group_title: str = "Sora",
        with_fallback: bool = True,
    ) -> IXBrowserSessionScanResponse:
        run_row = sqlite_db.get_ixbrowser_latest_scan_run(group_title)
        if not run_row:
            raise IXBrowserNotFoundError(f"未找到分组 {group_title} 的扫描历史")
        response = self._build_response_from_run_row(run_row)
        if with_fallback:
            self._apply_fallback_from_history(response)
        return response

    def get_sora_scan_history(
        self,
        group_title: str = "Sora",
        limit: int = 10,
    ) -> List[IXBrowserScanRunSummary]:
        rows = sqlite_db.get_ixbrowser_scan_runs(group_title, limit=min(max(limit, 1), self.scan_history_limit))
        return [
            IXBrowserScanRunSummary(
                run_id=int(row["id"]),
                group_id=int(row["group_id"]),
                group_title=str(row["group_title"]),
                total_windows=int(row["total_windows"]),
                success_count=int(row["success_count"]),
                failed_count=int(row["failed_count"]),
                scanned_at=str(row["scanned_at"]),
                operator_username=row.get("operator_username"),
            )
            for row in rows
        ]

    def get_sora_scan_by_run(
        self,
        run_id: int,
        with_fallback: bool = False,
    ) -> IXBrowserSessionScanResponse:
        run_row = sqlite_db.get_ixbrowser_scan_run(run_id)
        if not run_row:
            raise IXBrowserNotFoundError(f"未找到扫描记录：{run_id}")
        response = self._build_response_from_run_row(run_row)
        if with_fallback:
            self._apply_fallback_from_history(response)
        return response

    def _build_response_from_run_row(self, run_row: dict) -> IXBrowserSessionScanResponse:
        run_id = int(run_row["id"])
        rows = sqlite_db.get_ixbrowser_scan_results_by_run(run_id)
        results: List[IXBrowserSessionScanItem] = []
        for row in rows:
            results.append(
                IXBrowserSessionScanItem(
                    profile_id=int(row["profile_id"]),
                    window_name=str(row.get("window_name") or ""),
                    group_id=int(row["group_id"]),
                    group_title=str(row["group_title"]),
                    session_status=row.get("session_status"),
                    account=row.get("account"),
                    session=row.get("session_json") if isinstance(row.get("session_json"), dict) else None,
                    session_raw=row.get("session_raw"),
                    quota_remaining_count=row.get("quota_remaining_count"),
                    quota_total_count=row.get("quota_total_count"),
                    quota_reset_at=row.get("quota_reset_at"),
                    quota_source=row.get("quota_source"),
                    quota_payload=row.get("quota_payload_json") if isinstance(row.get("quota_payload_json"), dict) else None,
                    quota_error=row.get("quota_error"),
                    success=bool(row.get("success")),
                    close_success=bool(row.get("close_success")),
                    error=row.get("error"),
                    duration_ms=int(row.get("duration_ms") or 0),
                )
            )
        return IXBrowserSessionScanResponse(
            run_id=run_id,
            scanned_at=str(run_row.get("scanned_at")),
            group_id=int(run_row["group_id"]),
            group_title=str(run_row["group_title"]),
            total_windows=int(run_row["total_windows"]),
            success_count=int(run_row["success_count"]),
            failed_count=int(run_row["failed_count"]),
            fallback_applied_count=int(run_row.get("fallback_applied_count") or 0),
            results=results,
        )

    def _save_scan_response(
        self,
        response: IXBrowserSessionScanResponse,
        operator_user: Optional[dict],
        keep_latest_runs: int,
    ) -> int:
        run_data = {
            "group_id": response.group_id,
            "group_title": response.group_title,
            "total_windows": response.total_windows,
            "success_count": response.success_count,
            "failed_count": response.failed_count,
            "fallback_applied_count": 0,
            "operator_user_id": operator_user.get("id") if isinstance(operator_user, dict) else None,
            "operator_username": operator_user.get("username") if isinstance(operator_user, dict) else None,
        }
        result_rows = [item.model_dump() for item in response.results]
        return sqlite_db.create_ixbrowser_scan_run(
            run_data=run_data,
            results=result_rows,
            keep_latest_runs=keep_latest_runs,
        )

    def _apply_fallback_from_history(self, response: IXBrowserSessionScanResponse) -> None:
        if response.run_id is None:
            response.fallback_applied_count = 0
            return
        fallback_rows = sqlite_db.get_ixbrowser_latest_success_results_before_run(
            group_title=response.group_title,
            before_run_id=response.run_id,
        )
        fallback_map = {int(row["profile_id"]): row for row in fallback_rows}
        applied_count = 0
        for item in response.results:
            fallback_row = fallback_map.get(item.profile_id)
            if not fallback_row:
                continue
            changed = False
            if not item.account:
                fallback_account = fallback_row.get("account")
                if isinstance(fallback_account, str) and fallback_account.strip():
                    item.account = fallback_account.strip()
                    changed = True
            if item.quota_remaining_count is None and fallback_row.get("quota_remaining_count") is not None:
                item.quota_remaining_count = int(fallback_row.get("quota_remaining_count"))
                changed = True
            if not item.quota_reset_at:
                fallback_reset = fallback_row.get("quota_reset_at")
                if isinstance(fallback_reset, str) and fallback_reset.strip():
                    item.quota_reset_at = fallback_reset.strip()
                    changed = True
            if changed:
                item.fallback_applied = True
                item.fallback_run_id = int(fallback_row.get("run_id"))
                item.fallback_scanned_at = str(fallback_row.get("run_scanned_at"))
                applied_count += 1
        response.fallback_applied_count = applied_count

    def _find_group_by_title(
        self,
        groups: List[IXBrowserGroupWindows],
        group_title: str
    ) -> Optional[IXBrowserGroupWindows]:
        normalized = group_title.strip().lower()
        for group in groups:
            if group.title.strip().lower() == normalized:
                return group
        return None

    async def _get_window_from_sora_group(self, profile_id: int) -> Optional[IXBrowserWindow]:
        groups = await self.list_group_windows()
        sora_group = self._find_group_by_title(groups, "Sora")
        if not sora_group:
            return None
        for window in sora_group.windows:
            if int(window.profile_id) == int(profile_id):
                return window
        return None

    async def _open_profile(self, profile_id: int, restart_if_opened: bool = False) -> dict:
        payload = {
            "profile_id": profile_id,
            "args": ["--disable-extension-welcome-page"],
            "load_extensions": True,
            "load_profile_info_page": False,
            "cookies_backup": True,
            "cookie": ""
        }
        try:
            data = await self._post("/api/v2/profile-open", payload)
        except IXBrowserAPIError as exc:
            already_open = exc.code == 111003 or "已经打开" in exc.message.lower() or "already open" in exc.message.lower()
            process_not_found = exc.code == 1009 or "process not found" in exc.message.lower()
            if restart_if_opened and (already_open or process_not_found):
                # 1009 常见于窗口状态与本地进程状态短暂不一致，先尝试关闭再重开。
                await self._close_profile(profile_id)
                await asyncio.sleep(1.0)
                data = await self._post("/api/v2/profile-open", payload)
            else:
                raise
        result = data.get("data", {})
        if not isinstance(result, dict):
            raise IXBrowserConnectionError("打开窗口返回格式异常")
        return result

    async def _close_profile(self, profile_id: int) -> bool:
        try:
            await self._post("/api/v2/profile-close", {"profile_id": profile_id})
        except IXBrowserAPIError as exc:
            # 1009: Process not found，说明进程已不存在，按“已关闭”处理即可。
            if exc.code == 1009 or "process not found" in exc.message.lower():
                return True
            raise
        return True

    async def _fetch_sora_session(self, browser) -> Tuple[Optional[int], Optional[dict], Optional[str]]:
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        try:
            await page.goto(
                "https://sora.chatgpt.com/drafts",
                wait_until="domcontentloaded",
                timeout=30_000
            )
            await page.wait_for_timeout(1200)
        except PlaywrightTimeoutError as exc:
            raise IXBrowserConnectionError("访问 Sora drafts 超时") from exc

        data = await page.evaluate(
            """
            async () => {
              const resp = await fetch("https://sora.chatgpt.com/api/auth/session", {
                method: "GET",
                credentials: "include"
              });
              const text = await resp.text();
              let parsed = null;
              try {
                parsed = JSON.parse(text);
              } catch (e) {}
              return {
                status: resp.status,
                raw: text,
                json: parsed
              };
            }
            """
        )

        if not isinstance(data, dict):
            return None, None, None

        status = data.get("status")
        raw = data.get("raw")
        parsed = data.get("json")
        status_int = int(status) if isinstance(status, int) else None
        parsed_obj = parsed if isinstance(parsed, dict) else None
        raw_text = raw if isinstance(raw, str) else None
        return status_int, parsed_obj, raw_text

    async def _fetch_sora_quota(
        self,
        browser,
        session_obj: Optional[dict] = None
    ) -> Dict[str, Optional[Any]]:
        """
        在指纹浏览器页面内获取 Sora 次数信息：
        1) 从 /api/auth/session 读取 accessToken（已由上游获取）
        2) 使用该 token 在页面内请求 /backend/nf/check
        注意：请求由指纹浏览器页面发起，而非服务端直连 Sora。
        """
        access_token = self._extract_access_token(session_obj)
        if not access_token:
            return {
                "remaining_count": None,
                "total_count": None,
                "reset_at": None,
                "source": "https://sora.chatgpt.com/backend/nf/check",
                "payload": None,
                "error": "session 中未找到 accessToken",
            }

        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = context.pages[0] if context.pages else await context.new_page()

        response_data = await page.evaluate(
            """
            async (token) => {
              const endpoint = "https://sora.chatgpt.com/backend/nf/check";
              try {
                const resp = await fetch(endpoint, {
                  method: "GET",
                  credentials: "include",
                  headers: {
                    "Authorization": `Bearer ${token}`,
                    "Accept": "application/json"
                  }
                });
                const text = await resp.text();
                let parsed = null;
                try {
                  parsed = JSON.parse(text);
                } catch (e) {}
                return {
                  status: resp.status,
                  raw: text,
                  json: parsed,
                  source: endpoint
                };
              } catch (e) {
                return {
                  status: null,
                  raw: null,
                  json: null,
                  source: endpoint,
                  error: String(e)
                };
              }
            }
            """,
            access_token
        )

        if not isinstance(response_data, dict):
            return {
                "remaining_count": None,
                "total_count": None,
                "reset_at": None,
                "source": "https://sora.chatgpt.com/backend/nf/check",
                "payload": None,
                "error": "nf/check 返回格式异常",
            }

        status = response_data.get("status")
        raw = response_data.get("raw")
        payload = response_data.get("json")
        source = str(response_data.get("source") or "https://sora.chatgpt.com/backend/nf/check")
        request_error = response_data.get("error")

        if request_error:
            return {
                "remaining_count": None,
                "total_count": None,
                "reset_at": None,
                "source": source,
                "payload": None,
                "error": str(request_error),
            }

        if status != 200:
            detail = raw if isinstance(raw, str) and raw.strip() else "unknown error"
            return {
                "remaining_count": None,
                "total_count": None,
                "reset_at": None,
                "source": source,
                "payload": payload if isinstance(payload, dict) else None,
                "error": f"nf/check 状态码 {status}: {detail[:200]}",
            }

        parsed = self._parse_sora_nf_check(payload if isinstance(payload, dict) else {})
        return {
            "remaining_count": parsed.get("remaining_count"),
            "total_count": parsed.get("total_count"),
            "reset_at": parsed.get("reset_at"),
            "source": source,
            "payload": payload if isinstance(payload, dict) else None,
            "error": None,
        }

    def _parse_sora_nf_check(self, payload: Dict[str, Any]) -> Dict[str, Optional[Any]]:
        rate_info = payload.get("rate_limit_and_credit_balance")
        if not isinstance(rate_info, dict):
            return {
                "remaining_count": None,
                "total_count": None,
                "reset_at": None,
            }

        remaining_count = self._to_int(rate_info.get("estimated_num_videos_remaining"))
        purchased_remaining = self._to_int(rate_info.get("estimated_num_purchased_videos_remaining"))
        reset_seconds = self._to_int(rate_info.get("access_resets_in_seconds"))

        total_count = None
        if remaining_count is not None and purchased_remaining is not None:
            total_count = remaining_count + purchased_remaining

        reset_at = None
        if reset_seconds is not None and reset_seconds >= 0:
            reset_at = (
                datetime.now(timezone.utc) + timedelta(seconds=reset_seconds)
            ).isoformat()

        return {
            "remaining_count": remaining_count,
            "total_count": total_count,
            "reset_at": reset_at,
        }

    def _to_int(self, value: Any) -> Optional[int]:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            try:
                return int(float(value.strip()))
            except ValueError:
                return None
        return None

    def _extract_access_token(self, session_obj: Optional[dict]) -> Optional[str]:
        if not isinstance(session_obj, dict):
            return None
        token = session_obj.get("accessToken")
        if isinstance(token, str) and token.strip():
            return token.strip()
        return None

    def _extract_account(self, session_obj: Optional[dict]) -> Optional[str]:
        if not session_obj:
            return None
        user = session_obj.get("user")
        if isinstance(user, dict):
            email = user.get("email")
            name = user.get("name")
            if isinstance(email, str) and email.strip():
                return email.strip()
            if isinstance(name, str) and name.strip():
                return name.strip()
        return None

    async def _post(self, path: str, payload: dict) -> dict:
        base = settings.ixbrowser_api_base.rstrip("/")
        url = f"{base}{path}"
        timeout = httpx.Timeout(10.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
        except httpx.ConnectError as exc:
            raise IXBrowserConnectionError(
                f"无法连接 ixBrowser 本地 API，请确认 ixBrowser 已启动且地址可访问：{base}"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            body = exc.response.text
            logger.error("ixBrowser HTTP error: %s %s", status, body)
            raise IXBrowserConnectionError(f"ixBrowser 接口 HTTP 异常：{status}") from exc
        except Exception as exc:  # noqa: BLE001
            raise IXBrowserConnectionError(f"调用 ixBrowser 失败：{exc}") from exc

        if not isinstance(result, dict):
            raise IXBrowserConnectionError("ixBrowser 返回格式异常：响应不是 JSON 对象")

        error = result.get("error", {})
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message", "unknown error")
            if code is not None:
                try:
                    code_int = int(code)
                except (TypeError, ValueError):
                    code_int = -1
                if code_int != 0:
                    raise IXBrowserAPIError(code_int, str(message))

        return result


ixbrowser_service = IXBrowserService()
