import json

from akizacore.ai.providers.base import LLMProvider
from akizacore.ai.providers.chain import ResilientProvider
from akizacore.ai.providers.openai_compat import OpenAICompatibleProvider
from akizacore.config import Settings


def parse_extra_body(raw: str | None, setting_name: str) -> dict[str, object]:
    """Baca JSON dari .env (mis. {"reasoning_effort":"low"}). Kosong = tanpa parameter tambahan."""
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{setting_name} bukan JSON yang valid: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(
            f'{setting_name} harus berupa objek JSON, contoh: {{"reasoning_effort":"low"}}'
        )
    return {str(key): value for key, value in data.items()}


def build_primary(settings: Settings) -> OpenAICompatibleProvider | None:
    if not (settings.ai_base_url and settings.ai_api_key and settings.ai_model_fast):
        return None
    return OpenAICompatibleProvider(
        name="primary",
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key.get_secret_value(),
        model=settings.ai_model_fast,
        extra_body=parse_extra_body(settings.ai_extra_body, "AI_EXTRA_BODY"),
    )


def build_fallback(settings: Settings) -> OpenAICompatibleProvider | None:
    if not (
        settings.ai_fallback_base_url
        and settings.ai_fallback_api_key
        and settings.ai_fallback_model
    ):
        return None
    return OpenAICompatibleProvider(
        name="fallback",
        base_url=settings.ai_fallback_base_url,
        api_key=settings.ai_fallback_api_key.get_secret_value(),
        model=settings.ai_fallback_model,
        extra_body=parse_extra_body(settings.ai_fallback_extra_body, "AI_FALLBACK_EXTRA_BODY"),
    )


def build_llm(settings: Settings) -> LLMProvider | None:
    """Kembalikan None bila AI belum dikonfigurasi (bot tetap jalan tanpa fitur AI)."""
    primary = build_primary(settings)
    if primary is None:
        return None
    return ResilientProvider(primary, build_fallback(settings))
