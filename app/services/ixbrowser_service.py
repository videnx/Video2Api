"""
ixBrowser 本地 API 服务
"""
from __future__ import annotations

import asyncio
import base64
import json
import inspect
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple
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
    IXBrowserOpenProfileResponse,
    IXBrowserGenerateRequest,
    IXBrowserGenerateJobCreateResponse,
    IXBrowserScanRunSummary,
    IXBrowserSessionScanItem,
    IXBrowserSessionScanResponse,
    IXBrowserSilentRefreshCreateResponse,
    IXBrowserSilentRefreshJob,
    IXBrowserWindow,
    SoraJob,
    SoraJobCreateResponse,
    SoraJobEvent,
    SoraJobRequest,
)
from app.services.account_dispatch_service import AccountDispatchNoAvailableError, account_dispatch_service
from app.services.ixbrowser.groups import GroupsMixin
from app.services.ixbrowser.profiles import ProfilesMixin
from app.services.ixbrowser.proxies import ProxiesMixin
from app.services.ixbrowser.scan import ScanMixin
from app.services.ixbrowser.sora_api import SoraApiMixin
from app.services.ixbrowser.sora_jobs import SoraJobsMixin
from app.services.ixbrowser.silent_refresh import SilentRefreshMixin
from app.services.ixbrowser.errors import (
    IXBrowserAPIError,
    IXBrowserConnectionError,
    IXBrowserNotFoundError,
    IXBrowserServiceError,
)
from app.services.task_runtime import spawn

logger = logging.getLogger(__name__)

CF_NAV_LISTENER_TTL_SEC = 60
CF_NAV_RECORD_COOLDOWN_SEC = 20
CF_NAV_TITLE_CHECK_DELAY_SEC = 0.2
CF_NAV_TITLE_MARKERS = ("just a moment", "challenge-platform", "cloudflare")

IPHONE_OS_VERSIONS = [
    "16_0",
    "16_1",
    "16_2",
    "16_3",
    "16_4",
    "17_0",
    "17_1",
    "17_2",
    "17_3",
    "17_4",
]

IPHONE_BUILD_IDS = [
    "15E148",
    "15E302",
    "15E5178f",
    "16A366",
    "16A404",
    "16B92",
    "16C50",
    "16D57",
    "16E227",
    "17A577",
]

IPHONE_UA_POOL = [
    (
        "Mozilla/5.0 (iPhone; CPU iPhone OS {os_version} like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{safari_version} "
        "Mobile/{build_id} Safari/604.1"
    ).format(
        os_version=os_version,
        safari_version=os_version.replace("_", "."),
        build_id=build_id,
    )
    for os_version in IPHONE_OS_VERSIONS
    for build_id in IPHONE_BUILD_IDS
]


@dataclass
class IXBrowserServiceDeps:
    # 可注入依赖，便于 unit test stub/monkeypatch。
    playwright_factory: Callable[[], Any] = async_playwright


class IXBrowserService(
    SilentRefreshMixin,
    SoraJobsMixin,
    SoraApiMixin,
    GroupsMixin,
    ProxiesMixin,
    ProfilesMixin,
    ScanMixin,
):
    """ixBrowser 本地接口封装"""

    scan_history_limit = 10
    generate_timeout_seconds = 30 * 60
    generate_poll_interval_seconds = 6
    draft_wait_timeout_seconds = 20 * 60
    draft_manual_poll_interval_seconds = 5 * 60
    request_timeout_ms = 10_000
    ixbrowser_busy_retry_max = 6
    ixbrowser_busy_retry_delay_seconds = 1.2
    sora_blocked_resource_types = {"image", "media", "font"}
    sora_job_max_concurrency = 2
    heavy_load_retry_max_attempts = 4

    def __init__(self, deps: Optional[IXBrowserServiceDeps] = None) -> None:
        self._deps = deps or IXBrowserServiceDeps()
        self._ixbrowser_read_semaphore: Optional[asyncio.Semaphore] = None
        self._ixbrowser_write_semaphore: Optional[asyncio.Semaphore] = None
        self._group_windows_cache: List[IXBrowserGroupWindows] = []
        self._group_windows_cache_at: float = 0.0
        self._group_windows_cache_ttl: float = 120.0
        # profile_id -> proxy binding snapshot（来源：profile-list）
        self._profile_proxy_map: Dict[int, Dict[str, Any]] = {}
        # profile_id -> oai-did（用于 curl-cffi 静默更新请求，减少 CF 风控）
        self._oai_did_by_profile: Dict[int, str] = {}
        # profile_id -> last nav CF record time/url（用于短时间窗口内去重，避免并发写库风暴）
        self._cf_nav_last_record_at: Dict[int, float] = {}
        self._cf_nav_last_record_url: Dict[int, str] = {}
        self._proxy_binding_last_failed_at: float = 0.0
        self._realtime_quota_cache_ttl: float = 30.0
        self._realtime_operator_username: str = "实时使用"
        self._service_error_cls = IXBrowserServiceError
        self._api_error_cls = IXBrowserAPIError
        self._connection_error_cls = IXBrowserConnectionError
        from app.services.ixbrowser.sora_publish_workflow import SoraPublishWorkflow  # noqa: WPS433
        from app.services.ixbrowser.sora_generation_workflow import SoraGenerationWorkflow  # noqa: WPS433
        from app.services.ixbrowser.realtime_quota_service import RealtimeQuotaService  # noqa: WPS433
        from app.services.ixbrowser.sora_job_runner import SoraJobRunner  # noqa: WPS433

        self._sora_publish_workflow = SoraPublishWorkflow(service=self)
        self._sora_generation_workflow = SoraGenerationWorkflow(service=self, db=sqlite_db)
        self._realtime_quota_service = RealtimeQuotaService(service=self, db=sqlite_db)
        self._realtime_quota_service.set_cache_ttl(self._realtime_quota_cache_ttl)
        self._sora_job_runner = SoraJobRunner(service=self, db=sqlite_db)
        self.request_timeout_ms = int(self.request_timeout_ms)

    def playwright_factory(self):
        """对外暴露 Playwright factory（供 workflow/测试复用）。"""
        return self._deps.playwright_factory()

    def register_realtime_subscriber(self) -> asyncio.Queue:
        """对外公开的实时订阅入口（避免外部依赖私有方法）。"""
        return self._register_realtime_subscriber()

    def unregister_realtime_subscriber(self, queue: asyncio.Queue) -> None:
        """对外公开的实时订阅注销入口（避免外部依赖私有方法）。"""
        return self._unregister_realtime_subscriber(queue)

    def select_iphone_user_agent(self, profile_id: int) -> str:
        """对外公开 UA 选择（供 e2e/业务复用）。"""
        return self._select_iphone_user_agent(profile_id)

    async def apply_ua_override(self, page, user_agent: str) -> None:
        """对外公开 UA 覆盖（供 e2e/业务复用）。"""
        return await self._apply_ua_override(page, user_agent)

    async def apply_request_blocking(self, page) -> None:
        """对外公开请求拦截（供 e2e/业务复用）。"""
        return await self._apply_request_blocking(page)

    async def close_profile(self, profile_id: int) -> bool:
        """对外公开关闭窗口（供 e2e/业务复用）。"""
        return await self._close_profile(profile_id)

    def set_realtime_quota_cache_ttl(self, ttl_sec: float) -> None:
        self._realtime_quota_cache_ttl = float(ttl_sec)
        self._realtime_quota_service.set_cache_ttl(self._realtime_quota_cache_ttl)

    def set_sora_job_max_concurrency(self, n: int) -> None:
        n_int = int(n)
        if n_int < 1:
            n_int = 1
        if self.sora_job_max_concurrency == n_int:
            return
        self.sora_job_max_concurrency = n_int
        self._sora_job_runner.set_max_concurrency(n_int)

    async def open_profile_window(
        self,
        profile_id: int,
        group_title: str = "Sora",
    ) -> IXBrowserOpenProfileResponse:
        window = await self._get_window_from_group(profile_id, group_title)
        if not window:
            raise IXBrowserNotFoundError(f"未找到分组 {group_title} 下窗口：{profile_id}")
        open_data_raw = await self._open_profile_with_retry(profile_id, max_attempts=2)
        open_data = self._normalize_opened_profile_data(open_data_raw)
        return IXBrowserOpenProfileResponse(
            profile_id=int(profile_id),
            group_title=str(group_title),
            window_name=window.name,
            ws=open_data.get("ws"),
            debugging_address=open_data.get("debugging_address"),
        )

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
                        "proxy_mode": self._safe_int(item.get("proxy_mode")),
                        "proxy_id": self._safe_int(item.get("proxy_id")),
                        "proxy_type": self._safe_str(item.get("proxy_type")),
                        "proxy_ip": self._safe_str(item.get("proxy_ip")),
                        "proxy_port": self._safe_str(item.get("proxy_port")),
                        "real_ip": self._safe_str(item.get("real_ip")),
                    }
                )

            # 保险兜底：接口 total 异常时，防止死循环
            if len(page_items) < limit:
                break
            page += 1

        return profiles

    @staticmethod
    def _safe_int(value: Any) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(float(text))
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _safe_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _select_iphone_user_agent(self, profile_id: int) -> str:
        if not IPHONE_UA_POOL:
            return (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            )
        try:
            index = abs(int(profile_id)) % len(IPHONE_UA_POOL)
        except (TypeError, ValueError):
            index = 0
        return IPHONE_UA_POOL[index]

    async def _apply_ua_override(self, page, user_agent: str) -> None:
        try:
            session = await page.context.new_cdp_session(page)
            await session.send("Network.setUserAgentOverride", {"userAgent": user_agent})
        except Exception:  # noqa: BLE001
            try:
                await page.set_extra_http_headers({"User-Agent": user_agent})
            except Exception:  # noqa: BLE001
                pass

    async def _apply_request_blocking(self, page) -> None:
        blocked = self.sora_blocked_resource_types

        async def handle_route(route, request):
            if request.resource_type in blocked:
                await route.abort()
            else:
                await route.continue_()

        # 避免同一页面重复注册 route 导致阻断规则不生效/行为不稳定
        try:
            await page.unroute("**/*")
        except Exception:  # noqa: BLE001
            pass

        try:
            await page.route("**/*", handle_route)
        except Exception:  # noqa: BLE001
            pass

    def _should_record_cf_nav_event(self, profile_id: int, url: str) -> bool:
        """
        去重策略：
        - 同 profile 在 cooldown 秒内只记 1 次（防止多次 redirect/并发造成事件风暴）
        - 同 URL 重复不记（即使超过 cooldown）
        """
        try:
            pid = int(profile_id or 0)
        except Exception:
            pid = 0
        if pid <= 0:
            return False
        endpoint = str(url or "").strip()
        now = time.monotonic()
        last_at = float(self._cf_nav_last_record_at.get(pid) or 0.0)
        if last_at and (now - last_at) < float(CF_NAV_RECORD_COOLDOWN_SEC):
            return False
        last_url = self._cf_nav_last_record_url.get(pid)
        if last_url and last_url == endpoint:
            return False
        self._cf_nav_last_record_at[pid] = now
        self._cf_nav_last_record_url[pid] = endpoint
        return True

    async def _handle_cf_nav_framenavigated(self, *, page, profile_id: int, url: str) -> None:
        try:
            deadline = float(getattr(page, "_cf_nav_listener_deadline", 0.0) or 0.0)
        except Exception:
            deadline = 0.0
        if deadline and time.monotonic() > deadline:
            return

        endpoint = str(url or "").strip()
        lowered = endpoint.lower()
        if "/cdn-cgi/" in lowered or "challenge-platform" in lowered or "__cf_chl_" in lowered:
            is_challenge = True
        else:
            # 部分 CF 挑战 URL 不明显（或短暂保持原 URL），补一次 title 判定。
            try:
                await asyncio.sleep(float(CF_NAV_TITLE_CHECK_DELAY_SEC))
            except Exception:  # noqa: BLE001
                return
            title = ""
            try:
                title = str(await page.title() or "")
            except Exception:  # noqa: BLE001
                title = ""
            title_lower = title.lower()
            is_challenge = any(marker in title_lower for marker in CF_NAV_TITLE_MARKERS)

        if not is_challenge:
            return

        if not self._should_record_cf_nav_event(profile_id, endpoint):
            return

        spawn(
            asyncio.to_thread(
                self._record_proxy_cf_event,
                profile_id=profile_id,
                source="page_nav",
                endpoint=endpoint,
                status=None,
                error="cf_challenge",
                is_cf=True,
                assume_proxy_chain=True,
            ),
            task_name="ixbrowser.cf_nav.record",
            metadata={
                "profile_id": int(profile_id),
                "endpoint": endpoint[:200],
            },
        )

    async def _attach_cf_nav_listener(self, page, profile_id: int) -> None:
        """
        在页面准备阶段挂一个短时导航监听器，用于捕获“刚打开就跳 CF 挑战页”的场景。

        只在命中挑战时写入 `proxy_cf_events`（source=page_nav, is_cf=1）。
        """
        try:
            if bool(getattr(page, "_cf_nav_listener_attached", False)):
                return
        except Exception:  # noqa: BLE001
            # page 对象异常时，直接跳过（不影响主流程）
            return

        try:
            setattr(page, "_cf_nav_listener_attached", True)
            setattr(page, "_cf_nav_listener_deadline", time.monotonic() + float(CF_NAV_LISTENER_TTL_SEC))
        except Exception:  # noqa: BLE001
            # 监听器状态写不进去时，为避免重复注册，直接放弃挂载。
            return

        def _on_framenavigated(frame) -> None:
            # 监听器回调必须尽快返回：仅做轻量过滤 + spawn 后台任务
            try:
                deadline = float(getattr(page, "_cf_nav_listener_deadline", 0.0) or 0.0)
            except Exception:
                deadline = 0.0
            if deadline and time.monotonic() > deadline:
                return

            # 只关心主 frame 的导航（避免 iframe 噪声）
            try:
                if frame != getattr(page, "main_frame", None):
                    return
            except Exception:  # noqa: BLE001
                try:
                    if getattr(frame, "parent_frame", None) is not None:
                        return
                except Exception:  # noqa: BLE001
                    return

            try:
                url = str(getattr(frame, "url", "") or "")
            except Exception:  # noqa: BLE001
                url = ""

            lowered = url.lower()
            if "sora.chatgpt.com" not in lowered and "cdn-cgi/challenge-platform" not in lowered:
                return

            spawn(
                self._handle_cf_nav_framenavigated(page=page, profile_id=int(profile_id), url=url),
                task_name="ixbrowser.cf_nav.detect",
                metadata={"profile_id": int(profile_id), "url": url[:200]},
            )

        try:
            page.on("framenavigated", _on_framenavigated)
        except Exception:  # noqa: BLE001
            return

    async def _prepare_sora_page(self, page, profile_id: int) -> None:
        user_agent = self._select_iphone_user_agent(profile_id)
        await self._apply_ua_override(page, user_agent)
        await self._apply_request_blocking(page)
        await self._attach_realtime_quota_listener(page, profile_id, "Sora")
        await self._attach_cf_nav_listener(page, profile_id)

    def _register_realtime_subscriber(self) -> asyncio.Queue:
        return self._realtime_quota_service.register_subscriber()

    def _unregister_realtime_subscriber(self, queue: asyncio.Queue) -> None:
        self._realtime_quota_service.unregister_subscriber(queue)

    async def _notify_realtime_update(self, group_title: str) -> None:
        await self._realtime_quota_service.notify_update(group_title)

    async def _attach_realtime_quota_listener(self, page, profile_id: int, group_title: str) -> None:
        await self._realtime_quota_service.attach_realtime_quota_listener(page, profile_id, group_title)

    async def _record_realtime_quota(
        self,
        profile_id: int,
        group_title: str,
        status: Optional[int],
        payload: Dict[str, Any],
        parsed: Dict[str, Any],
        source_url: str,
    ) -> None:
        await self._realtime_quota_service.record_realtime_quota(
            profile_id=profile_id,
            group_title=group_title,
            status=status,
            payload=payload,
            parsed=parsed,
            source_url=source_url,
        )

    def _build_sora_job(self, row: dict) -> SoraJob:
        status = str(row.get("status") or "queued")
        phase = str(row.get("phase") or "queue")
        progress_pct = row.get("progress_pct")
        if progress_pct is None:
            progress_pct = 100 if status == "completed" else 0
        publish_url = row.get("publish_url")
        if publish_url and not self._sora_publish_workflow.is_valid_publish_url(publish_url):
            publish_url = None
        profile_id = int(row.get("profile_id") or 0)
        proxy_bind = self.get_cached_proxy_binding(profile_id)
        return SoraJob(
            job_id=int(row["id"]),
            profile_id=profile_id,
            window_name=row.get("window_name"),
            group_title=row.get("group_title"),
            prompt=str(row.get("prompt") or ""),
            image_url=row.get("image_url"),
            duration=str(row.get("duration") or "10s"),
            aspect_ratio=str(row.get("aspect_ratio") or "landscape"),
            status=status,
            phase=phase,
            progress_pct=float(progress_pct) if progress_pct is not None else None,
            task_id=row.get("task_id"),
            generation_id=row.get("generation_id"),
            publish_url=publish_url,
            publish_post_id=row.get("publish_post_id"),
            publish_permalink=row.get("publish_permalink"),
            watermark_status=row.get("watermark_status"),
            watermark_url=row.get("watermark_url"),
            watermark_error=row.get("watermark_error"),
            watermark_attempts=row.get("watermark_attempts"),
            watermark_started_at=row.get("watermark_started_at"),
            watermark_finished_at=row.get("watermark_finished_at"),
            dispatch_mode=row.get("dispatch_mode"),
            dispatch_score=row.get("dispatch_score"),
            dispatch_quantity_score=row.get("dispatch_quantity_score"),
            dispatch_quality_score=row.get("dispatch_quality_score"),
            dispatch_reason=row.get("dispatch_reason"),
            retry_of_job_id=row.get("retry_of_job_id"),
            retry_root_job_id=row.get("retry_root_job_id"),
            retry_index=row.get("retry_index"),
            resolved_from_job_id=row.get("resolved_from_job_id"),
            error=row.get("error"),
            proxy_mode=proxy_bind.get("proxy_mode"),
            proxy_id=proxy_bind.get("proxy_id"),
            proxy_type=proxy_bind.get("proxy_type"),
            proxy_ip=proxy_bind.get("proxy_ip"),
            proxy_port=proxy_bind.get("proxy_port"),
            real_ip=proxy_bind.get("real_ip"),
            proxy_local_id=proxy_bind.get("proxy_local_id"),
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            created_at=str(row.get("created_at")),
            updated_at=str(row.get("updated_at")),
            operator_username=row.get("operator_username"),
        )

    def _build_generate_job(self, row: dict) -> IXBrowserGenerateJob:
        status = str(row.get("status") or "queued")
        progress = row.get("progress")
        if progress is None:
            progress = 100 if status == "completed" else 0
        elif status == "completed" and int(progress) < 100:
            progress = 100
        publish_url = row.get("publish_url")
        if publish_url and not self._sora_publish_workflow.is_valid_publish_url(publish_url):
            publish_url = None
        return IXBrowserGenerateJob(
            job_id=int(row["id"]),
            profile_id=int(row["profile_id"]),
            window_name=row.get("window_name"),
            group_title=str(row.get("group_title") or "Sora"),
            prompt=str(row.get("prompt") or ""),
            duration=str(row.get("duration") or "10s"),
            aspect_ratio=str(row.get("aspect_ratio") or "landscape"),
            status=status,
            progress=progress,
            publish_status=row.get("publish_status"),
            publish_url=publish_url,
            publish_post_id=row.get("publish_post_id"),
            publish_permalink=row.get("publish_permalink"),
            publish_error=row.get("publish_error"),
            publish_attempts=row.get("publish_attempts"),
            published_at=row.get("published_at"),
            task_id=row.get("task_id"),
            task_url=row.get("task_url"),
            generation_id=row.get("generation_id"),
            error=row.get("error"),
            elapsed_ms=row.get("elapsed_ms"),
            started_at=row.get("started_at"),
            finished_at=row.get("finished_at"),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            operator_username=row.get("operator_username"),
        )

    @staticmethod
    def _is_ixbrowser_read_path(path: str) -> bool:
        normalized = str(path or "").strip().lower()
        if not normalized:
            return False
        read_suffixes = (
            "/group-list",
            "/profile-list",
            "/proxy-list",
            "/native-client-profile-opened-list",
            "/profile-opened-list",
        )
        return normalized.endswith(read_suffixes)

    async def _post(self, path: str, payload: dict) -> dict:
        base = settings.ixbrowser_api_base.rstrip("/")
        url = f"{base}{path}"
        timeout = httpx.Timeout(max(1.0, float(self.request_timeout_ms) / 1000.0))

        if self._is_ixbrowser_read_path(path):
            if self._ixbrowser_read_semaphore is None:
                self._ixbrowser_read_semaphore = asyncio.Semaphore(3)
            semaphore = self._ixbrowser_read_semaphore
        else:
            if self._ixbrowser_write_semaphore is None:
                self._ixbrowser_write_semaphore = asyncio.Semaphore(1)
            semaphore = self._ixbrowser_write_semaphore

        async with semaphore:
            for attempt in range(self.ixbrowser_busy_retry_max + 1):
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
                            if code_int == 1008 and attempt < self.ixbrowser_busy_retry_max:
                                delay = self.ixbrowser_busy_retry_delay_seconds * (2 ** attempt)
                                logger.warning(
                                    "ixBrowser busy (code=1008), retry in %.1fs (attempt %s/%s)",
                                    delay,
                                    attempt + 1,
                                    self.ixbrowser_busy_retry_max,
                                )
                                await asyncio.sleep(delay)
                                continue
                            raise IXBrowserAPIError(code_int, str(message))

                return result

            raise IXBrowserAPIError(1008, "Server busy, please try again later")


ixbrowser_service = IXBrowserService()
