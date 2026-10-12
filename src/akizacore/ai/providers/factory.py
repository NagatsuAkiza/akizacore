from akizacore.ai.providers.base import LLMProvider
from akizacore.ai.providers.chain import ResilientProvider
from akizacore.ai.providers.openai_compat import OpenAICompatibleProvider
from akizacore.config import Settings


def build_llm(settings: Settings) -> LLMProvider | None:
    """Kembalikan None bila AI belum dikonfigurasi (bot tetap jalan tanpa fitur AI)."""
    if not (settings.ai_base_url and settings.ai_api_key and settings.ai_model_fast):
        return None
    primary = OpenAICompatibleProvider(
        name="primary",
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key.get_secret_value(),
        model=settings.ai_model_fast,
    )
    fallback: OpenAICompatibleProvider | None = None
    if (
        settings.ai_fallback_base_url
        and settings.ai_fallback_api_key
        and settings.ai_fallback_model
    ):
        fallback = OpenAICompatibleProvider(
            name="fallback",
            base_url=settings.ai_fallback_base_url,
            api_key=settings.ai_fallback_api_key.get_secret_value(),
            model=settings.ai_fallback_model,
        )
    return ResilientProvider(primary, fallback)
