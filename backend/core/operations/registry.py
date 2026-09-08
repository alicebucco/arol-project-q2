"""Registry primitives and execution safeguards."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from core.auth import AuthContext
from core.contracts import AgentName, AgentRequest, AgentResult
from core.operations.parameters import OperationParameters


class UnknownOperationError(ValueError):
    """An agent/operation pair is not available to the planner."""

class MissingOperationMachineContextError(ValueError):
    """A registered operation requires a machine selected by trusted backend input."""

@dataclass(frozen=True)
class OperationContext:
    """Trusted context injected by the backend, never by the planner."""

    user: AuthContext
    machine_id: str | None = None

@dataclass(frozen=True)
class OperationDefinition:
    agent: AgentName
    operation: str
    parameters_model: type[OperationParameters]
    requires_machine_context: bool
    handler: OperationHandler
    planner_description: str = ""

class OperationRegistry:
    """Resolve, validate, and execute only registered evidence operations."""

    def __init__(self, definitions: list[OperationDefinition]) -> None:
        self._definitions = {(definition.agent, definition.operation): definition for definition in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("An operation may be registered only once per agent.")

    def resolve(self, request: AgentRequest) -> OperationDefinition:
        try:
            return self._definitions[(request.agent, request.operation)]
        except KeyError as error:
            raise UnknownOperationError(f"Unsupported operation: {request.agent}.{request.operation}") from error

    def validate(self, request: AgentRequest) -> tuple[OperationDefinition, OperationParameters]:
        definition = self.resolve(request)
        return definition, definition.parameters_model.model_validate(request.parameters)

    def plan_requires_machine_context(self, requests: list[AgentRequest]) -> bool:
        """Derive machine-context requirements from trusted operation definitions."""

        return any(self.resolve(request).requires_machine_context for request in requests)

    def planner_catalog(self) -> list[dict[str, Any]]:
        """Expose only the allowed operation vocabulary to the future planner.

        The catalogue describes capabilities; it contains neither user data nor
        executable handlers.  The registry still performs the authoritative
        validation immediately before an operation is run.
        """

        return [
            {
                "agent": definition.agent,
                "operation": definition.operation,
                "description": definition.planner_description,
                "requires_machine_context": definition.requires_machine_context,
                "parameters_schema": definition.parameters_model.model_json_schema(),
            }
            for definition in sorted(self._definitions.values(), key=lambda item: (item.agent, item.operation))
        ]

    async def execute(self, request: AgentRequest, context: OperationContext) -> AgentResult:
        definition, parameters = self.validate(request)
        if definition.requires_machine_context and not (context.machine_id and context.machine_id.strip()):
            raise MissingOperationMachineContextError(
                f"{definition.agent}.{definition.operation} requires a selected machine."
            )
        return await definition.handler(parameters, context)
