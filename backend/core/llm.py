"""Minimal Mercury client using its OpenAI-compatible API."""

from openai import APIConnectionError, APIStatusError, AsyncOpenAI

from core.config import get_settings


class LlmNotConfiguredError(RuntimeError):
    """Raised when the local LLM API key has not been configured."""


class LlmRequestError(RuntimeError):
    """Raised when the LLM provider cannot complete a request."""


SYSTEM_PROMPT = (
    "You are the AROL Customer Platform assistant. "
    "This is a connectivity test only: do not claim access to fleet data, "
    "manuals, alarms, orders, or maintenance records."
)


async def generate_chat_reply(message: str) -> str:
    """Send a single user message to Mercury and return its text response."""

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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.75,
            max_tokens=500,
        )
    except (APIConnectionError, APIStatusError) as error:
        raise LlmRequestError from error
    finally:
        await client.close()

    return completion.choices[0].message.content or ""
