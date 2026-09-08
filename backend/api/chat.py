"""Chat API endpoints."""

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, status

from agents.manuals import ManualsUnavailableError
from api.presenters import manual_search_result
from api.schemas import ChatRequest, ChatResponse
from core.auth import AuthContext, get_current_user
from db.repositories.errors import MachineNotFoundError, MachineUnavailableError
from core.llm import LlmNotConfiguredError, LlmRequestError
from core.orchestrator import MissingMachineContextError, handle_chat

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user: AuthContext = Depends(get_current_user),
) -> ChatResponse:
    """Send a question to the configured LLM (agent routing comes next)."""

    message = request.message.strip()
    if not message:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The message cannot be blank.",
        )

    try:
        result = await handle_chat(
            message,
            replace(user, hide_machine_existence=True),
            request.machine_id,
            request.history,
        )
    except MissingMachineContextError as error:
        return ChatResponse(answer=str(error))
    except (MachineNotFoundError, MachineUnavailableError):
        return ChatResponse(
            answer=(
                "The requested machine is not available in your authorized scope, "
                "so I cannot provide machine-specific information."
            )
        )
    except ManualsUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Manual search is temporarily unavailable.",
        ) from None
    except LlmNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM_API_KEY is not configured.",
        ) from None
    except LlmRequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The LLM provider could not complete the request.",
        ) from None

    return ChatResponse(
        answer=result.answer,
        agent=result.agent,
        sources=[manual_search_result(row) for row in result.manual_evidence or []],
        data=result.structured_data,
    )
