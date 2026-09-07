"""Allow-listed, typed operations that evidence agents may execute.

The registry is the enforcement point between an LLM-proposed ``AgentRequest``
and backend code.  A request is never executed until its agent, operation, and
operation-specific parameters have all been validated here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agents.iot import (
    alarms_by_id,
    alarm_summary,
    company_machines,
    compare_telemetry_periods,
    count_alarms,
    machine_configuration,
    observed_productive_hours,
    recent_alarms,
    repeated_alarm_patterns,
    telemetry,
    telemetry_summary,
)
from agents.manuals import maintenance_requirements, search_with_match_status
from agents.orders import (
    order_detail,
    quote_history,
    search_orders,
    search_quotes,
)
from agents.service import search_tickets, ticket_detail
from core.alarm_codes import alarm_meaning, normalise_alarm_code
from core.auth import AuthContext
from core.contracts import AgentName, AgentRequest, AgentResult
from core.evidence_formatters import agent_result, manual_search_result


class UnknownOperationError(ValueError):
    """An agent/operation pair is not available to the planner."""


class MissingOperationMachineContextError(ValueError):
    """A registered operation requires a machine selected by trusted backend input."""


class OperationParameters(BaseModel):
    """Base schema for operation parameters supplied by the planner."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _normalise_identifier(
    value: str | None,
    *,
    prefix: str,
    field_name: str,
) -> str | None:
    """Accept only a non-empty identifier of the expected resource family."""
    if value is None:
        return None
    if not isinstance(value, str) or not (identifier := value.strip()):
        raise ValueError(f"{field_name} must be a non-empty string.")
    identifier = identifier.upper()
    if not identifier.startswith(prefix):
        raise ValueError(f"{field_name} must start with {prefix}.")
    return identifier


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


class RepeatedAlarmPatternsParameters(OperationParameters):
    limit: int = Field(default=20, ge=1, le=100)


class AlarmMeaningParameters(OperationParameters):
    alarm_code: str = Field(min_length=1, max_length=100)

    @field_validator("alarm_code")
    @classmethod
    def normalise_alarm_code(cls, value: str) -> str:
        return normalise_alarm_code(value)


class AlarmsByIdParameters(OperationParameters):
    """Exact event identifiers emitted by another authorised operation."""

    alarm_ids: list[str] = Field(min_length=1, max_length=100)

    @field_validator("alarm_ids")
    @classmethod
    def normalise_alarm_ids(cls, values: list[str]) -> list[str]:
        normalised: list[str] = []
        for value in values:
            alarm_id = _normalise_identifier(value, prefix="ALM-", field_name="Each alarm ID")
            assert alarm_id is not None
            if alarm_id not in normalised:
                normalised.append(alarm_id)
        return normalised


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
    query: str = Field(min_length=1, max_length=1_000)
    limit: int = Field(default=5, ge=1, le=10)


class MaintenanceTicketsParameters(OperationParameters):
    limit: int = Field(default=10, ge=1, le=100)
    ticket_id: str | None = Field(default=None, max_length=100)
    alarm_id: str | None = Field(default=None, max_length=100)
    ticket_status: Literal["Open", "In progress", "Waiting for parts", "Resolved", "Closed"] | None = None
    ticket_type: Literal[
        "Remote troubleshooting", "On-site service", "Spare parts request",
        "Scheduled maintenance", "Overhaul", "Size change assistance",
    ] | None = None
    priority: Literal["Critical", "High", "Medium", "Low"] | None = None
    owner_role: Literal[
        "Line Operator", "Maintenance Man", "Plant Maintenance Manager", "AROL Technical Service",
    ] | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("ticket_id")
    @classmethod
    def normalise_ticket_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="TCK-", field_name="ticket_id")

    @field_validator("alarm_id")
    @classmethod
    def normalise_alarm_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="ALM-", field_name="alarm_id")

    @model_validator(mode="after")
    def valid_date_range(self) -> "MaintenanceTicketsParameters":
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("A date range cannot end before it starts.")
        return self


class OrdersParameters(OperationParameters):
    limit: int = Field(default=10, ge=1, le=100)
    machine_id: str | None = Field(default=None, max_length=100)
    order_id: str | None = Field(default=None, max_length=100)
    quote_id: str | None = Field(default=None, max_length=100)
    order_status: Literal["Confirmed", "In production", "Delivered", "Closed"] | None = None
    shipment_status: Literal["In production", "Ready for shipment", "Delivered", "Installed"] | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("machine_id")
    @classmethod
    def normalise_machine_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="MCH-", field_name="machine_id")

    @field_validator("order_id")
    @classmethod
    def normalise_order_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="ORD-", field_name="order_id")

    @field_validator("quote_id")
    @classmethod
    def normalise_quote_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="QTE-", field_name="quote_id")

    @model_validator(mode="after")
    def valid_date_range(self) -> "OrdersParameters":
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("A date range cannot end before it starts.")
        return self


class QuotesParameters(OperationParameters):
    limit: int = Field(default=10, ge=1, le=100)
    machine_id: str | None = Field(default=None, max_length=100)
    quote_id: str | None = Field(default=None, max_length=100)
    revision_status: Literal["Draft", "Submitted", "Superseded", "Approved", "Rejected", "Expired"] | None = None
    start_date: date | None = None
    end_date: date | None = None

    @field_validator("machine_id")
    @classmethod
    def normalise_machine_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="MCH-", field_name="machine_id")

    @field_validator("quote_id")
    @classmethod
    def normalise_quote_id(cls, value: str | None) -> str | None:
        return _normalise_identifier(value, prefix="QTE-", field_name="quote_id")

    @model_validator(mode="after")
    def valid_date_range(self) -> "QuotesParameters":
        if self.start_date is not None and self.end_date is not None and self.start_date > self.end_date:
            raise ValueError("A date range cannot end before it starts.")
        return self


class OrderDetailParameters(OperationParameters):
    order_id: str = Field(min_length=1, max_length=100)

    @field_validator("order_id")
    @classmethod
    def normalise_order_id(cls, value: str) -> str:
        normalised = _normalise_identifier(value, prefix="ORD-", field_name="order_id")
        assert normalised is not None
        return normalised


class QuoteHistoryParameters(OperationParameters):
    quote_id: str = Field(min_length=1, max_length=100)

    @field_validator("quote_id")
    @classmethod
    def normalise_quote_id(cls, value: str) -> str:
        normalised = _normalise_identifier(value, prefix="QTE-", field_name="quote_id")
        assert normalised is not None
        return normalised


class TicketDetailParameters(OperationParameters):
    ticket_id: str = Field(min_length=1, max_length=100)

    @field_validator("ticket_id")
    @classmethod
    def normalise_ticket_id(cls, value: str) -> str:
        normalised = _normalise_identifier(value, prefix="TCK-", field_name="ticket_id")
        assert normalised is not None
        return normalised


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
    machine_id = _machine(context)
    alarms = await recent_alarms(
        machine_id,
        context.user,
        parameters.limit,
        **parameters.model_dump(exclude={"limit"}),
    )
    evidence = {"machine_id": machine_id, "alarms": alarms}
    return agent_result("iot", "recent_alarms", evidence, structured_data=evidence)


async def _alarms_by_id(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmsByIdParameters)
    machine_id = _machine(context)
    alarms = await alarms_by_id(machine_id, context.user, parameters.alarm_ids)
    found_ids = {alarm["alarm_id"] for alarm in alarms}
    evidence = {
        "machine_id": machine_id,
        "requested_alarm_ids": parameters.alarm_ids,
        "alarms": alarms,
        "unmatched_alarm_ids": [alarm_id for alarm_id in parameters.alarm_ids if alarm_id not in found_ids],
    }
    return agent_result("iot", "alarms_by_id", evidence, structured_data=evidence)


async def _count_alarms(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmQueryParameters)
    result = await count_alarms(_machine(context), context.user, **parameters.model_dump())
    return agent_result("iot", "count_alarms", result, structured_data={"machine_id": _machine(context)})


async def _alarm_summary(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmSummaryParameters)
    result = await alarm_summary(
        _machine(context),
        context.user,
        parameters.limit,
        **parameters.model_dump(exclude={"limit"}),
    )
    return agent_result(
        "iot", "alarm_summary", result,
        structured_data={"machine_id": _machine(context), "alarm_patterns": result["patterns"]},
    )


async def _repeated_alarm_patterns(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, RepeatedAlarmPatternsParameters)
    machine_id = _machine(context)
    patterns = await repeated_alarm_patterns(machine_id, context.user, parameters.limit)
    evidence = {"machine_id": machine_id, "alarm_patterns": patterns}
    return agent_result("iot", "repeated_alarm_patterns", evidence, structured_data=evidence)


async def _alarm_meaning(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, AlarmMeaningParameters)
    del context
    return agent_result(
        "iot",
        "alarm_meaning",
        {"alarm_code": parameters.alarm_code, "meaning": alarm_meaning(parameters.alarm_code)},
    )


async def _telemetry(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, RecentTelemetryParameters)
    machine_id = _machine(context)
    snapshots = await telemetry(
        machine_id,
        context.user,
        parameters.limit,
        **parameters.model_dump(exclude={"limit"}),
    )
    evidence = {"machine_id": machine_id, "telemetry": snapshots}
    return agent_result("iot", "telemetry", evidence, structured_data=evidence)


async def _telemetry_summary(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, TelemetryQueryParameters)
    result = await telemetry_summary(_machine(context), context.user, **parameters.model_dump())
    return agent_result("iot", "telemetry_summary", result, structured_data={"machine_id": _machine(context)})


async def _compare_telemetry_periods(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, CompareTelemetryPeriodsParameters)
    result = await compare_telemetry_periods(
        _machine(context), context.user, **parameters.model_dump()
    )
    return agent_result("iot", "compare_telemetry_periods", result, structured_data={"machine_id": _machine(context)})


async def _machine_configuration(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    del parameters
    result = await machine_configuration(_machine(context), context.user)
    return agent_result("iot", "machine_configuration", result, structured_data={"machine_configuration": result})


async def _observed_productive_hours(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    del parameters
    result = await observed_productive_hours(_machine(context), context.user)
    return agent_result("iot", "observed_productive_hours", result, structured_data={"productive_hours_observation": result})


async def _company_machines(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    del parameters
    machines = await company_machines(context.user)
    evidence = {"machines": machines}
    return agent_result("iot", "company_machines", evidence, structured_data=evidence)


async def _search_manuals(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, ManualSearchParameters)
    result = await search_with_match_status(
        _machine(context), parameters.query, context.user, parameters.limit,
    )
    metadata = {
        key: result[key]
        for key in (
            "requested_alarm_codes", "exact_alarm_code_matches",
            "unmatched_alarm_codes", "alarm_code_match_status",
        )
    }
    return manual_search_result(_machine(context), result["manual_evidence"], search_metadata=metadata)


async def _maintenance_requirements(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    del parameters
    machine_id = _machine(context)
    result = await maintenance_requirements(machine_id, context.user)
    warnings = [] if result["requirements"] else ["No documented working-hour maintenance intervals were found."]
    return agent_result(
        "manuals", "maintenance_requirements", result,
        structured_data={"maintenance_requirements": result}, warnings=warnings,
    )


async def _maintenance_tickets(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, MaintenanceTicketsParameters)
    machine_id = _machine(context)
    result = await search_tickets(machine_id, context.user, **parameters.model_dump())
    metadata = {
        key: result[key]
        for key in ("total_count", "returned_count", "is_truncated", "limit")
    }
    evidence = {
        "machine_id": machine_id,
        "maintenance_tickets": result["items"],
        "maintenance_tickets_metadata": metadata,
    }
    return agent_result("service", "maintenance_tickets", evidence, structured_data=evidence)


async def _orders(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, OrdersParameters)
    result = await search_orders(context.user, **parameters.model_dump())
    metadata = {
        key: result[key]
        for key in ("total_count", "returned_count", "is_truncated", "limit")
    }
    evidence = {"orders": result["items"], "orders_metadata": metadata}
    return agent_result("orders", "orders", evidence, structured_data=evidence)


async def _quotes(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, QuotesParameters)
    result = await search_quotes(context.user, **parameters.model_dump())
    metadata = {
        key: result[key]
        for key in ("total_count", "returned_count", "is_truncated", "limit")
    }
    evidence = {"quotes": result["items"], "quotes_metadata": metadata}
    return agent_result("orders", "quotes", evidence, structured_data=evidence)


async def _order_detail(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, OrderDetailParameters)
    detail = await order_detail(context.user, parameters.order_id)
    evidence = {"order_detail": detail}
    return agent_result("orders", "order_detail", evidence, structured_data=evidence)


async def _quote_history(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, QuoteHistoryParameters)
    history = await quote_history(context.user, parameters.quote_id)
    evidence = {"quote_history": history}
    return agent_result("orders", "quote_history", evidence, structured_data=evidence)


async def _ticket_detail(parameters: OperationParameters, context: OperationContext) -> AgentResult:
    assert isinstance(parameters, TicketDetailParameters)
    machine_id = _machine(context)
    detail = await ticket_detail(machine_id, context.user, parameters.ticket_id)
    evidence = {"machine_id": machine_id, "ticket_detail": detail}
    return agent_result("service", "ticket_detail", evidence, structured_data=evidence)


OPERATION_REGISTRY = OperationRegistry(
    [
        OperationDefinition("iot", "recent_alarms", RecentAlarmsParameters, True, _recent_alarms, "Retrieve recent alarm events, optionally filtered by code, severity, status, or time range."),
        OperationDefinition("iot", "alarms_by_id", AlarmsByIdParameters, True, _alarms_by_id, "Retrieve exact selected-machine alarm events from their event IDs. Use only when an authorised operation already supplied alarm IDs; this operation does not accept alarm codes."),
        OperationDefinition("iot", "count_alarms", AlarmQueryParameters, True, _count_alarms, "Count alarm events when the user asks how often an alarm or condition occurred."),
        OperationDefinition("iot", "alarm_summary", AlarmSummaryParameters, True, _alarm_summary, "Group alarm events by code to identify frequent or recurring alarm conditions."),
        OperationDefinition("iot", "repeated_alarm_patterns", RepeatedAlarmPatternsParameters, True, _repeated_alarm_patterns, "Return alarm codes that occurred repeatedly, including occurrence count, first and last occurrence, and latest status. Use for diagnostic questions about recurring alarms."),
        OperationDefinition("iot", "alarm_meaning", AlarmMeaningParameters, False, _alarm_meaning, "Return the deterministic display meaning of one valid alarm code. Use when the user asks what an alarm code means and no machine data is needed."),
        OperationDefinition("iot", "telemetry", RecentTelemetryParameters, True, _telemetry, "Retrieve recent machine telemetry snapshots such as production, uptime, temperature, and operational status."),
        OperationDefinition("iot", "telemetry_summary", TelemetryQueryParameters, True, _telemetry_summary, "Aggregate telemetry metrics over a requested time range for averages, totals, minima, maxima, or trends."),
        OperationDefinition("iot", "compare_telemetry_periods", CompareTelemetryPeriodsParameters, True, _compare_telemetry_periods, "Compare aggregate telemetry metrics across two explicit time periods."),
        OperationDefinition("iot", "machine_configuration", OperationParameters, True, _machine_configuration, "Return the selected machine's installed configuration profile."),
        OperationDefinition("iot", "observed_productive_hours", OperationParameters, True, _observed_productive_hours, "Return productive hours and time coverage observed in available machine telemetry."),
        OperationDefinition("iot", "company_machines", OperationParameters, False, _company_machines, "List the authenticated company's available machines and their identity details."),
        OperationDefinition("manuals", "search", ManualSearchParameters, True, _search_manuals, "Search authoritative selected-machine manual excerpts. Prefer it as the default documented-evidence operation for requirements, roles, safety, procedures, configuration, component behaviour, and technical explanations when no narrower operation directly answers the question. Combine it with IoT, Service, or Orders when their records need documented interpretation; do not use it for a pure count, status, or list."),
        OperationDefinition("manuals", "maintenance_requirements", OperationParameters, True, _maintenance_requirements, "Return cited working-hour and operating-hour maintenance requirements from the selected machine's manual."),
        OperationDefinition("service", "maintenance_tickets", MaintenanceTicketsParameters, True, _maintenance_tickets, "Retrieve maintenance tickets and their statuses for the selected machine."),
        OperationDefinition("service", "ticket_detail", TicketDetailParameters, True, _ticket_detail, "Retrieve one authorised selected-machine maintenance ticket by its exact TCK- identifier."),
        OperationDefinition("orders", "orders", OrdersParameters, False, _orders, "Retrieve the authenticated company's orders with filters, shipment statuses, and list-completeness metadata. Use an ORD- identifier only in order_id and a QTE- identifier only in quote_id."),
        OperationDefinition("orders", "quotes", QuotesParameters, False, _quotes, "Retrieve the authenticated company's quotes with filters, revisions, validity, totals, and list-completeness metadata. Use a QTE- identifier in quote_id."),
        OperationDefinition("orders", "order_detail", OrderDetailParameters, False, _order_detail, "Retrieve the authenticated company's detail for one order identified by an exact ORD- identifier, including fulfilment and approved quote content."),
        OperationDefinition("orders", "quote_history", QuoteHistoryParameters, False, _quote_history, "Retrieve the authenticated company's revision history for one quote identified by an exact QTE- identifier."),
    ]
)
