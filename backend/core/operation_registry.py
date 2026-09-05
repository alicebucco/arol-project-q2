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
    alarm_guidance_context_evidence,
    alarm_summary_evidence,
    compare_telemetry_periods_evidence,
    count_alarms_evidence,
    recent_alarms_evidence,
    telemetry_evidence,
    telemetry_summary_evidence,
)
from agents.manuals import search_evidence
from agents.orders import orders_evidence, quotes_evidence
from agents.service import maintenance_tickets_evidence, observed_maintenance_plan_evidence
from core.alarm_codes import normalise_alarm_code
from core.auth import AuthContext
from core.contracts import AgentName, AgentRequest, AgentResult


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


class AlarmGuidanceParameters(OperationParameters):
    alarm_code: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=5, ge=1, le=20)

    @field_validator("alarm_code")
    @classmethod
    def normalise_alarm_code(cls, value: str) -> str:
        return normalise_alarm_code(value)


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


def _machine(context: OperationContext) -> str:
    """Narrow a type after the registry has enforced machine context."""

    assert context.machine_id is not None and context.machine_id.strip()
    return context.machine_id.strip()


async def _recent_alarms(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, RecentAlarmsParameters)
    return await recent_alarms_evidence(
        _machine(context),
        context.user,
        parameters.limit,
        **parameters.model_dump(exclude={"limit"}),
    )


async def _count_alarms(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmQueryParameters)
    return await count_alarms_evidence(_machine(context), context.user, **parameters.model_dump())


async def _alarm_summary(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmSummaryParameters)
    return await alarm_summary_evidence(
        _machine(context),
        context.user,
        parameters.limit,
        **parameters.model_dump(exclude={"limit"}),
    )


async def _alarm_guidance_context(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmGuidanceParameters)
    return await alarm_guidance_context_evidence(
        _machine(context), context.user, parameters.alarm_code, parameters.limit
    )


async def _telemetry(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, RecentTelemetryParameters)
    return await telemetry_evidence(
        _machine(context),
        context.user,
        parameters.limit,
        **parameters.model_dump(exclude={"limit"}),
    )


async def _telemetry_summary(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, TelemetryQueryParameters)
    return await telemetry_summary_evidence(_machine(context), context.user, **parameters.model_dump())


async def _compare_telemetry_periods(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, CompareTelemetryPeriodsParameters)
    return await compare_telemetry_periods_evidence(
        _machine(context), context.user, **parameters.model_dump()
    )


async def _search_manuals(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ManualSearchParameters)
    return await search_evidence(_machine(context), parameters.query, context.user, parameters.limit)


async def _maintenance_tickets(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, MaintenanceTicketsParameters)
    return await maintenance_tickets_evidence(_machine(context), context.user, parameters.limit)


async def _observed_maintenance_plan(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    del parameters
    return await observed_maintenance_plan_evidence(_machine(context), context.user)


async def _orders(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ListRecordsParameters)
    return await orders_evidence(context.user, parameters.limit)


async def _quotes(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ListRecordsParameters)
    return await quotes_evidence(context.user, parameters.limit)


OPERATION_REGISTRY = OperationRegistry(
    [
        OperationDefinition("iot", "recent_alarms", RecentAlarmsParameters, True, _recent_alarms, "Retrieve recent alarm events, optionally filtered by code, severity, status, or time range."),
        OperationDefinition("iot", "count_alarms", AlarmQueryParameters, True, _count_alarms, "Count alarm events when the user asks how often an alarm or condition occurred."),
        OperationDefinition("iot", "alarm_summary", AlarmSummaryParameters, True, _alarm_summary, "Group alarm events by code to identify frequent or recurring alarm conditions."),
        OperationDefinition("iot", "alarm_guidance_context", AlarmGuidanceParameters, True, _alarm_guidance_context, "Return a deterministic alarm-code meaning and, for roles authorised for operational data, matching recent events. Use when the user asks what one alarm code means."),
        OperationDefinition("iot", "telemetry", RecentTelemetryParameters, True, _telemetry, "Retrieve recent machine telemetry snapshots such as production, uptime, temperature, and operational status."),
        OperationDefinition("iot", "telemetry_summary", TelemetryQueryParameters, True, _telemetry_summary, "Aggregate telemetry metrics over a requested time range for averages, totals, minima, maxima, or trends."),
        OperationDefinition("iot", "compare_telemetry_periods", CompareTelemetryPeriodsParameters, True, _compare_telemetry_periods, "Compare aggregate telemetry metrics across two explicit time periods."),
        OperationDefinition("manuals", "search", ManualSearchParameters, True, _search_manuals, "Find relevant machine-manual excerpts for procedures, safety guidance, configuration, troubleshooting, or technical requirements."),
        OperationDefinition("service", "maintenance_tickets", MaintenanceTicketsParameters, True, _maintenance_tickets, "Retrieve maintenance tickets and their statuses for the selected machine."),
        OperationDefinition("service", "observed_maintenance_plan", OperationParameters, True, _observed_maintenance_plan, "Compare documented maintenance thresholds with productive hours observed in available telemetry."),
        OperationDefinition("orders", "orders", ListRecordsParameters, False, _orders, "Retrieve the authenticated company’s recent orders and shipment statuses."),
        OperationDefinition("orders", "quotes", ListRecordsParameters, False, _quotes, "Retrieve the authenticated company’s recent quotes, revisions, validity, and totals."),
    ]
)
