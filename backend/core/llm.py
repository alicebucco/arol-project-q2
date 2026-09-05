"""Minimal Mercury client using its OpenAI-compatible API."""

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from core.config import get_settings


class LlmNotConfiguredError(RuntimeError):
    """Raised when the local LLM API key has not been configured."""


class LlmRequestError(RuntimeError):
    """Raised when the LLM provider cannot complete a request."""


SYSTEM_PROMPT = (
    "You are the AROL Customer Platform assistant. "
    "Always reply in English, even when the user writes in another language. "
    "This is a connectivity test only: do not claim access to fleet data, "
    "manuals, alarms, orders, or maintenance records."
)


async def _generate_reply(
    message: str,
    system_prompt: str,
    *,
    temperature: float,
    max_tokens: int,
) -> str:
    """Send one request to Mercury with caller-selected decoding settings."""

    settings = get_settings()
    if settings.llm_api_key is None:
        raise LlmNotConfiguredError

    client = AsyncOpenAI(
        api_key=settings.llm_api_key.get_secret_value(),
        base_url=settings.llm_base_url,
    )
    try:
        completion = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except (APIConnectionError, APIStatusError) as error:
        raise LlmRequestError from error
    finally:
        await client.close()

    return completion.choices[0].message.content or ""


async def generate_chat_reply(message: str, system_prompt: str = SYSTEM_PROMPT) -> str:
    """Generate a conversational reply using the existing chat settings."""

    return await _generate_reply(message, system_prompt, temperature=0.75, max_tokens=500)


async def generate_structured_reply(message: str, system_prompt: str) -> str:
    """Generate deterministic, short text intended for schema validation."""

    return await _generate_reply(message, system_prompt, temperature=0.0, max_tokens=800)
