"""arq worker startup/shutdown wiring."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from medbuddy.reminders import worker
from tests.helpers import make_mock_settings


@pytest.mark.asyncio
async def test_worker_startup_mock_integration_no_shared_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "get_settings", lambda: make_mock_settings())
    ctx: dict = {}
    await worker.startup(ctx)
    assert ctx["outbound_http"] is None
    assert ctx["services"] is not None
    await worker.shutdown(ctx)


@pytest.mark.asyncio
async def test_worker_startup_creates_outbound_http_and_shutdown_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MagicMock()
    settings.is_mock = False
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "build_app_services", lambda *a, **k: MagicMock())

    ctx: dict = {}
    await worker.startup(ctx)
    ob = ctx["outbound_http"]
    assert isinstance(ob, httpx.AsyncClient)
    assert not ob.is_closed

    await worker.shutdown(ctx)
    assert ob.is_closed
