"""Conservative composition of answers from authorised evidence."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.business_time import BUSINESS_TODAY
from core.orchestration.models import EvidenceBundle

StructuredReply = Callable[[str, str], Awaitable[str]]
ChatReply = Callable[..., Awaitable[str]]

class ManualSentenceSelection(BaseModel):
    """One selection of source sentences from an authorised manual chunk."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    chunk_id: str = Field(min_length=1, max_length=200)
    sentence_indexes: list[int] = Field(min_length=1, max_length=10)


class ManualSelectionReply(BaseModel):
    """Structured LLM output used only before backend source validation."""

    model_config = ConfigDict(extra="forbid")

    selections: list[ManualSentenceSelection] = Field(default_factory=list, max_length=10)


def private_manual_evidence(bundle: EvidenceBundle) -> list[dict[str, Any]]:
    """Return raw manual chunks held only in in-process agent results."""

    chunks: list[dict[str, Any]] = []
    for result in bundle.results:
        if result.agent == "manuals" and result.operation == "search":
            chunks.extend(result.private_evidence.get("manual_evidence", []))
    return chunks


async def select_validated_manual_sentences(
    message: str,
    manual_evidence: list[dict[str, Any]],
    generate_structured_reply: StructuredReply,
) -> list[str]:
    """Select authorised manual sentences without allowing the LLM to copy text."""

    chunks: list[dict[str, Any]] = []
    for evidence in manual_evidence:
        content = evidence.get("content")
        chunk_id = evidence.get("chunk_id")
        if not isinstance(content, str) or not isinstance(chunk_id, str):
            continue
        sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", content) if sentence.strip()]
        if sentences:
            chunks.append({"chunk_id": chunk_id, "sentences": sentences})

    prompt = (
        f"User question: {message}\n\n"
        "Return a JSON object with exactly one key, `selections`. Each selection must contain `chunk_id` and "
        "`sentence_indexes`, a list of zero-based indexes from that chunk's numbered sentences. Select only sentences "
        "that directly answer the question. Do not write claims, quotes, file names, pages, Markdown, or extra fields. "
        "If no direct sentence is supported, return {\"selections\": []}.\n\n"
        f"Authorised numbered sentences:\n{json.dumps(chunks, ensure_ascii=False)}"
    )
    system_prompt = (
        "You select conservative, source-grounded manual sentences for the AROL Customer Platform. "
        "Return valid JSON only. Do not infer causes, remedies, procedures, completion, or maintenance status."
    )
    try:
        raw_reply = await generate_structured_reply(prompt, system_prompt)
        proposed = ManualSelectionReply.model_validate_json(raw_reply)
    except ValidationError:
        return []

    sentences_by_chunk = {chunk["chunk_id"]: chunk["sentences"] for chunk in chunks}
    selected: list[str] = []
    for selection in proposed.selections:
        sentences = sentences_by_chunk.get(selection.chunk_id)
        if sentences is None:
            continue
        for index in selection.sentence_indexes:
            if 0 <= index < len(sentences):
                selected.append(sentences[index])
    return list(dict.fromkeys(selected))


def composer_evidence_with_manual_sentences(
    bundle: EvidenceBundle,
    selected_manual_sentences: list[str],
) -> list[dict[str, Any]]:
    """Replace raw manual-search output with backend-validated manual sentences."""

    evidence = [
        item for item in bundle.composer_evidence
        if not (item.get("agent") == "manuals" and item.get("operation") == "search")
    ]
    if selected_manual_sentences:
        evidence.append({
            "agent": "manuals",
            "operation": "validated_manual_sentences",
            "evidence": {"sentences": selected_manual_sentences},
            "sources": [],
            "warnings": [],
        })
    return evidence


async def compose_grounded_evidence_answer(
    message: str,
    composer_evidence: list[dict[str, Any]],
    generate_chat_reply: ChatReply,
) -> str:
    """Compose a grounded answer from already-authorised evidence."""

    prompt = (
        f"User question: {message}\n\n"
        "Use only the following evidence retrieved by authorised backend tools. "
        "If it is empty, say that no matching records were found. Do not invent values. "
        "Use every relevant evidence category present. Do not omit IoT, Service, or Orders facts merely because "
        "documented manual guidance is also present. Treat validated manual sentences as documented guidance, not "
        "as proof of a cause, repair, machine condition, or safety status. State when the available evidence cannot "
        "establish a causal conclusion. "
        "Answer only in English and mention relevant IDs or statuses when useful. "
        "Do not include manual citations inline; the frontend presents authorised sources separately. "
        f"Use {BUSINESS_TODAY.isoformat()} as today's date when interpreting "
        "quote expiry, open items, or overdue work.\n\n"
        f"Evidence retrieved by the authorised agents:\n"
        f"{json.dumps(composer_evidence, default=str, ensure_ascii=False)}"
    )
    system_prompt = (
        "You are the AROL Customer Platform assistant. "
        "The backend has already enforced authentication, company scope, and role permissions. "
        "Summarise only the supplied evidence; never reveal or infer data outside it. "
        "Manual evidence is limited to authorised indexed chunks and citations, never full PDF documents. "
        "Return plain text only: do not use Markdown, HTML, asterisks, square brackets, "
        "backslashes, code fences, or inline citations. Use short paragraphs; if a list is "
        "necessary, use ordinary numbered lines. "
        "For maintenance observations, treat observed productive hours as a bounded telemetry window, "
        "not as a lifetime counter; do not claim a threshold proves maintenance is currently due or completed."
    )
    return await generate_chat_reply(prompt, system_prompt=system_prompt)


async def compose_evidence_answer(
    message: str,
    bundle: EvidenceBundle,
    *,
    generate_chat_reply: ChatReply,
    generate_structured_reply: StructuredReply,
) -> str:
    """Compose a grounded answer while preserving every relevant agent result."""

    manual_evidence = private_manual_evidence(bundle)
    if not manual_evidence:
        return await compose_grounded_evidence_answer(message, bundle.composer_evidence, generate_chat_reply)

    selected_manual_sentences = await select_validated_manual_sentences(message, manual_evidence, generate_structured_reply)
    has_non_manual_evidence = any(result.agent != "manuals" for result in bundle.results)
    if not has_non_manual_evidence:
        if selected_manual_sentences:
            return "\n".join(selected_manual_sentences)
        return "I found authorised manual evidence, but could not generate a validated summary. Please review the sources below."

    return await compose_grounded_evidence_answer(
        message,
        composer_evidence_with_manual_sentences(bundle, selected_manual_sentences),
        generate_chat_reply,
    )
