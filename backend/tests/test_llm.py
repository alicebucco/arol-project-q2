import asyncio
from types import SimpleNamespace

from pydantic import SecretStr

import core.llm as llm


def test_structured_reply_uses_deterministic_decoding(monkeypatch) -> None:
    request_arguments: dict[str, object] = {}

    class FakeCompletions:
        async def create(self, **kwargs):
            request_arguments.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"requests": []}'))])

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=FakeCompletions())

        async def close(self) -> None:
            return None

    monkeypatch.setattr(llm, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        llm,
        "get_settings",
        lambda: SimpleNamespace(llm_api_key=SecretStr("test-key"), llm_base_url="https://example.test", llm_model="test-model"),
    )

    reply = asyncio.run(llm.generate_structured_reply("plan this", "return JSON"))

    assert reply == '{"requests": []}'
    assert request_arguments["temperature"] == 0.0
    assert request_arguments["max_tokens"] == 800
