"""Allow-listed, typed operations that evidence agents may execute.

The registry is the enforcement point between an LLM-proposed ``AgentRequest``
and backend code.  A request is never executed until its agent, operation, and
operation-specific parameters have all been validated here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agents.iot import (
    alarm_summary,
    compare_telemetry_periods,
    count_alarms,
    recent_alarms,
    telemetry,
    telemetry_summary,
)
from agents.manuals import search as search_manual
from agents.orders import orders, quotes
from agents.service import maintenance_tickets, observed_maintenance_plan
from core.alarm_codes import normalise_alarm_code
from core.auth import AuthContext
from core.contracts import AgentName, AgentRequest, AgentResult, EvidenceSource


class UnknownOperationError(ValueError):
    """An agent/operation pair is not available to the planner."""


class MissingOperationMachineContextError(ValueError):
    """A registered operation requires a machine selected by trusted backend input."""


class OperationParameters(BaseModel):
    """Base schema for operation parameters supplied by the planner."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class TimeRangeParameters(OperationParameters):
    start_time: datetime | None = None
    end_time: datetime | None = None

    @model_validator(mode="after")
    def valid_time_range(self) -> "TimeRangeParameters":
        if self.start_time is not None and self.end_time is not None:
            try:
                invalid = self.start_time > self.end_time
            except TypeError as error:
                raise ValueError("Time-range boundaries must use compatible time zones.") from error
            if invalid:
                raise ValueError("A time range cannot end before it starts.")
        return self


class AlarmQueryParameters(TimeRangeParameters):
    alarm_code: str | None = Field(default=None, max_length=100)
    severity: Literal["Critical", "High", "Medium", "Low"] | None = None
    alarm_status: Literal["Open", "Acknowledged", "Resolved"] | None = None

    @field_validator("alarm_code")
    @classmethod
    def normalise_alarm_code(cls, value: str | None) -> str | None:
        return normalise_alarm_code(value) if value else value


class RecentAlarmsParameters(AlarmQueryParameters):
    limit: int = Field(default=20, ge=1, le=100)


class AlarmSummaryParameters(AlarmQueryParameters):
    limit: int = Field(default=20, ge=1, le=100)


class TelemetryQueryParameters(TimeRangeParameters):
    operational_status: Literal["Running", "Alarm", "Idle", "Stopped", "Maintenance", "Size change"] | None = None


class RecentTelemetryParameters(TelemetryQueryParameters):
    limit: int = Field(default=20, ge=1, le=100)


class CompareTelemetryPeriodsParameters(OperationParameters):
    first_start: datetime
    first_end: datetime
    second_start: datetime
    second_end: datetime
    operational_status: Literal["Running", "Alarm", "Idle", "Stopped", "Maintenance", "Size change"] | None = None

    @model_validator(mode="after")
    def valid_periods(self) -> "CompareTelemetryPeriodsParameters":
        try:
            invalid = self.first_start > self.first_end or self.second_start > self.second_end
        except TypeError as error:
            raise ValueError("Comparison boundaries must use compatible time zones.") from error
        if invalid:
            raise ValueError("A comparison period cannot end before it starts.")
        return self


class ManualSearchParameters(OperationParameters):
    query: str = Field(min_length=1, max_length=4_000)
    limit: int = Field(default=5, ge=1, le=20)


class MaintenanceTicketsParameters(OperationParameters):
    limit: int = Field(default=10, ge=1, le=100)


class ListRecordsParameters(OperationParameters):
    limit: int = Field(default=10, ge=1, le=100)


@dataclass(frozen=True)
class OperationContext:
    """Trusted context injected by the backend, never by the planner."""

    user: AuthContext
    machine_id: str | None = None


OperationHandler = Callable[[OperationParameters, OperationContext], Awaitable[AgentResult]]


@dataclass(frozen=True)
class OperationDefinition:
    agent: AgentName
    operation: str
    parameters_model: type[OperationParameters]
    requires_machine_context: bool
    handler: OperationHandler


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

    async def execute(self, request: AgentRequest, context: OperationContext) -> AgentResult:
        definition, parameters = self.validate(request)
        if definition.requires_machine_context and not (context.machine_id and context.machine_id.strip()):
            raise MissingOperationMachineContextError(
                f"{definition.agent}.{definition.operation} requires a selected machine."
            )
        return await definition.handler(parameters, context)


def _machine(context: OperationContext) -> str:
    """Narrow a type after the registry has enforced machine context."""

    assert context.machine_id is not None and context.machine_id.strip()
    return context.machine_id.strip()


async def _recent_alarms(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, RecentAlarmsParameters)
    machine_id = _machine(context)
    alarms = await recent_alarms(machine_id, context.user, parameters.limit, **parameters.model_dump(exclude={"limit"}))
    return AgentResult(agent="iot", operation="recent_alarms", evidence={"machine_id": machine_id, "alarms": alarms}, structured_data={"machine_id": machine_id, "alarms": alarms})


async def _count_alarms(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmQueryParameters)
    machine_id = _machine(context)
    result = await count_alarms(machine_id, context.user, **parameters.model_dump())
    return AgentResult(agent="iot", operation="count_alarms", evidence=result, structured_data={"machine_id": machine_id})


async def _alarm_summary(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmSummaryParameters)
    machine_id = _machine(context)
    result = await alarm_summary(machine_id, context.user, **parameters.model_dump())
    return AgentResult(agent="iot", operation="alarm_summary", evidence=result, structured_data={"machine_id": machine_id, "alarm_patterns": result["patterns"]})


async def _telemetry(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, RecentTelemetryParameters)
    machine_id = _machine(context)
    snapshots = await telemetry(machine_id, context.user, parameters.limit, **parameters.model_dump(exclude={"limit"}))
    return AgentResult(agent="iot", operation="telemetry", evidence={"machine_id": machine_id, "telemetry": snapshots}, structured_data={"machine_id": machine_id, "telemetry": snapshots})


async def _telemetry_summary(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, TelemetryQueryParameters)
    machine_id = _machine(context)
    result = await telemetry_summary(machine_id, context.user, **parameters.model_dump())
    return AgentResult(agent="iot", operation="telemetry_summary", evidence=result, structured_data={"machine_id": machine_id})


async def _compare_telemetry_periods(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, CompareTelemetryPeriodsParameters)
    result = await compare_telemetry_periods(_machine(context), context.user, **parameters.model_dump())
    return AgentResult(agent="iot", operation="compare_telemetry_periods", evidence=result, structured_data={"machine_id": _machine(context)})


def _manual_sources(matches: list[dict[str, Any]]) -> list[EvidenceSource]:
    """Expose only bounded excerpts and citations, never an internal raw chunk."""

    return [
        EvidenceSource(
            source_id=f"manual:{match['file']}:{match['page']}",
            source_type="manual",
            citation={
                "file": match["file"], "page": match["page"], "section": match["section"],
                "title": match.get("title"), "relevance": match.get("relevance"),
            },
            excerpt=match.get("excerpt"),
        )
        for match in matches
    ]


async def _search_manuals(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ManualSearchParameters)
    machine_id = _machine(context)
    matches = await search_manual(machine_id, parameters.query, context.user, parameters.limit)
    sources = _manual_sources(matches)
    return AgentResult(agent="manuals", operation="search", evidence={"machine_id": machine_id, "match_count": len(sources)}, sources=sources)


async def _maintenance_tickets(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, MaintenanceTicketsParameters)
    machine_id = _machine(context)
    tickets = await maintenance_tickets(machine_id, context.user, parameters.limit)
    return AgentResult(agent="service", operation="maintenance_tickets", evidence={"machine_id": machine_id, "maintenance_tickets": tickets}, structured_data={"machine_id": machine_id, "maintenance_tickets": tickets})


async def _observed_maintenance_plan(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    del parameters
    observation = await observed_maintenance_plan(_machine(context), context.user)
    return AgentResult(agent="service", operation="observed_maintenance_plan", evidence={"maintenance_observation": observation}, structured_data={"maintenance_observation": observation})


async def _orders(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ListRecordsParameters)
    result = await orders(context.user, parameters.limit)
    return AgentResult(agent="orders", operation="orders", evidence={"orders": result}, structured_data={"orders": result})


async def _quotes(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ListRecordsParameters)
    result = await quotes(context.user, parameters.limit)
    return AgentResult(agent="orders", operation="quotes", evidence={"quotes": result}, structured_data={"quotes": result})


OPERATION_REGISTRY = OperationRegistry(
    [
        OperationDefinition("iot", "recent_alarms", RecentAlarmsParameters, True, _recent_alarms),
        OperationDefinition("iot", "count_alarms", AlarmQueryParameters, True, _count_alarms),
        OperationDefinition("iot", "alarm_summary", AlarmSummaryParameters, True, _alarm_summary),
        OperationDefinition("iot", "telemetry", RecentTelemetryParameters, True, _telemetry),
        OperationDefinition("iot", "telemetry_summary", TelemetryQueryParameters, True, _telemetry_summary),
        OperationDefinition("iot", "compare_telemetry_periods", CompareTelemetryPeriodsParameters, True, _compare_telemetry_periods),
        OperationDefinition("manuals", "search", ManualSearchParameters, True, _search_manuals),
        OperationDefinition("service", "maintenance_tickets", MaintenanceTicketsParameters, True, _maintenance_tickets),
        OperationDefinition("service", "observed_maintenance_plan", OperationParameters, True, _observed_maintenance_plan),
        OperationDefinition("orders", "orders", ListRecordsParameters, False, _orders),
        OperationDefinition("orders", "quotes", ListRecordsParameters, False, _quotes),
    ]
)