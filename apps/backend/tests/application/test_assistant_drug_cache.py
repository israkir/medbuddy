"""Assistant turn behavior when ``drug_caches`` (Supabase) is wired."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from medbuddy.application.assistant_turn import run_assistant_text_turn
from medbuddy.container import build_app_services
from medbuddy.services import AppServices
from medbuddy.integrations.mocks.llm import MockLLM
from medbuddy.models.domain import Intent


@pytest.mark.asyncio
async def test_personalization_cache_hit_short_circuits(mock_settings) -> None:
    base = build_app_services(mock_settings)
    caches = AsyncMock()
    caches.get_personalized_reply = AsyncMock(return_value="（快取）個人化用藥說明")
    caches.get_reference_cache_id = AsyncMock(return_value=None)
    caches.save_personalized_reply = AsyncMock()
    svc = AppServices(
        line=base.line,
        stt=base.stt,
        llm=MockLLM(intent=Intent.EXPLAIN_MEDICATION),
        drugs=base.drugs,
        users=base.users,
        conversations=base.conversations,
        settings=base.settings,
        line_audio_blobs=base.line_audio_blobs,
        tts=base.tts,
        drug_caches=caches,
    )
    out = await run_assistant_text_turn(svc, user_key="cache-hit-user", user_text="解釋阿斯匹靈")
    assert out == "（快取）個人化用藥說明"
    caches.get_personalized_reply.assert_awaited_once()
    caches.save_personalized_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_personalization_cache_miss_saves_after_compose(mock_settings) -> None:
    base = build_app_services(mock_settings)
    caches = AsyncMock()
    caches.get_personalized_reply = AsyncMock(return_value=None)
    caches.get_reference_cache_id = AsyncMock(return_value=None)
    caches.save_personalized_reply = AsyncMock()
    svc = AppServices(
        line=base.line,
        stt=base.stt,
        llm=MockLLM(intent=Intent.EXPLAIN_MEDICATION),
        drugs=base.drugs,
        users=base.users,
        conversations=base.conversations,
        settings=base.settings,
        line_audio_blobs=base.line_audio_blobs,
        tts=base.tts,
        drug_caches=caches,
    )
    out = await run_assistant_text_turn(svc, user_key="cache-miss-user", user_text="解釋阿斯匹靈")
    assert "阿斯匹靈" in out
    caches.get_personalized_reply.assert_awaited_once()
    caches.save_personalized_reply.assert_awaited_once()
    call_kw = caches.save_personalized_reply.await_args.kwargs
    assert call_kw["llm_meta"]["source"] == "openfda"


@pytest.mark.asyncio
async def test_personalization_llm_meta_source_is_model_when_no_reference_data(
    mock_settings,
) -> None:
    base = build_app_services(mock_settings)
    caches = AsyncMock()
    caches.get_personalized_reply = AsyncMock(return_value=None)
    caches.get_reference_cache_id = AsyncMock(return_value=None)
    caches.save_personalized_reply = AsyncMock()
    drugs = base.drugs
    drugs.fetch_tfda_snippet = AsyncMock(return_value=None)
    drugs.fetch_openfda_label_snippet = AsyncMock(return_value=None)
    svc = AppServices(
        line=base.line,
        stt=base.stt,
        llm=MockLLM(intent=Intent.EXPLAIN_MEDICATION),
        drugs=drugs,
        users=base.users,
        conversations=base.conversations,
        settings=base.settings,
        line_audio_blobs=base.line_audio_blobs,
        tts=base.tts,
        drug_caches=caches,
    )
    out = await run_assistant_text_turn(svc, user_key="no-ref-user", user_text="解釋阿斯匹靈")
    assert "阿斯匹靈" in out
    caches.save_personalized_reply.assert_awaited_once()
    assert caches.save_personalized_reply.await_args.kwargs["llm_meta"]["source"] == "mock_llm"
