"""Implementations of allow-listed evidence operations."""

from agents.iot import alarms_by_id, alarm_summary, company_machines, compare_telemetry_periods, count_alarms, machine_configuration, observed_productive_hours, recent_alarms, repeated_alarm_patterns, telemetry, telemetry_summary
from agents.manuals import maintenance_requirements, search_with_match_status
from agents.orders import order_detail, quote_history, search_orders, search_quotes
from agents.service import search_tickets, ticket_detail
from core.alarm_codes import alarm_meaning
from core.contracts import AgentResult
from core.evidence_formatters import agent_result, manual_search_result
from core.operations.parameters import AlarmsByIdParameters, AlarmMeaningParameters, AlarmQueryParameters, AlarmSummaryParameters, CompareTelemetryPeriodsParameters, MaintenanceTicketsParameters, ManualSearchParameters, OperationParameters, OrderDetailParameters, OrdersParameters, QuoteHistoryParameters, QuotesParameters, RecentAlarmsParameters, RecentTelemetryParameters, RepeatedAlarmPatternsParameters, TelemetryQueryParameters, TicketDetailParameters
from core.operations.registry import OperationContext


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
