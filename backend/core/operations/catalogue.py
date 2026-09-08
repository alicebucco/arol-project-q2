"""The single catalogue of planner-authorised operations."""

from core.operations import handlers
from core.operations.parameters import AlarmsByIdParameters, AlarmMeaningParameters, AlarmQueryParameters, AlarmSummaryParameters, CompareTelemetryPeriodsParameters, MaintenanceTicketsParameters, ManualSearchParameters, OperationParameters, OrderDetailParameters, OrdersParameters, QuoteHistoryParameters, QuotesParameters, RecentAlarmsParameters, RecentTelemetryParameters, RepeatedAlarmPatternsParameters, TelemetryQueryParameters, TicketDetailParameters
from core.operations.registry import OperationDefinition, OperationRegistry


OPERATION_REGISTRY = OperationRegistry(
    [
        OperationDefinition("iot", "recent_alarms", RecentAlarmsParameters, True, handlers._recent_alarms, "Retrieve recent alarm events, optionally filtered by code, severity, status, or time range."),
        OperationDefinition("iot", "alarms_by_id", AlarmsByIdParameters, True, handlers._alarms_by_id, "Retrieve exact selected-machine alarm events from their event IDs. Use only when an authorised operation already supplied alarm IDs; this operation does not accept alarm codes."),
        OperationDefinition("iot", "count_alarms", AlarmQueryParameters, True, handlers._count_alarms, "Count alarm events when the user asks how often an alarm or condition occurred."),
        OperationDefinition("iot", "alarm_summary", AlarmSummaryParameters, True, handlers._alarm_summary, "Group alarm events by code to identify frequent or recurring alarm conditions."),
        OperationDefinition("iot", "repeated_alarm_patterns", RepeatedAlarmPatternsParameters, True, handlers._repeated_alarm_patterns, "Return alarm codes that occurred repeatedly, including occurrence count, first and last occurrence, and latest status. Use for diagnostic questions about recurring alarms."),
        OperationDefinition("iot", "alarm_meaning", AlarmMeaningParameters, False, handlers._alarm_meaning, "Return the deterministic display meaning of one valid alarm code. Use when the user asks what an alarm code means and no machine data is needed."),
        OperationDefinition("iot", "telemetry", RecentTelemetryParameters, True, handlers._telemetry, "Retrieve recent machine telemetry snapshots such as production, uptime, temperature, and operational status."),
        OperationDefinition("iot", "telemetry_summary", TelemetryQueryParameters, True, handlers._telemetry_summary, "Aggregate telemetry metrics over a requested time range for averages, totals, minima, maxima, or trends."),
        OperationDefinition("iot", "compare_telemetry_periods", CompareTelemetryPeriodsParameters, True, handlers._compare_telemetry_periods, "Compare aggregate telemetry metrics across two explicit time periods."),
        OperationDefinition("iot", "machine_configuration", OperationParameters, True, handlers._machine_configuration, "Return the selected machine's installed configuration profile."),
        OperationDefinition("iot", "observed_productive_hours", OperationParameters, True, handlers._observed_productive_hours, "Return productive hours and time coverage observed in available machine telemetry."),
        OperationDefinition("iot", "company_machines", OperationParameters, False, handlers._company_machines, "List the authenticated company's available machines and their identity details."),
        OperationDefinition("manuals", "search", ManualSearchParameters, True, handlers._search_manuals, "Search authoritative selected-machine manual excerpts. Prefer it as the default documented-evidence operation for requirements, roles, safety, procedures, configuration, component behaviour, and technical explanations when no narrower operation directly answers the question. Combine it with IoT, Service, or Orders when their records need documented interpretation; do not use it for a pure count, status, or list."),
        OperationDefinition("manuals", "maintenance_requirements", OperationParameters, True, handlers._maintenance_requirements, "Return cited working-hour and operating-hour maintenance requirements from the selected machine's manual."),
        OperationDefinition("service", "maintenance_tickets", MaintenanceTicketsParameters, True, handlers._maintenance_tickets, "Retrieve maintenance tickets and their statuses for the selected machine."),
        OperationDefinition("service", "ticket_detail", TicketDetailParameters, True, handlers._ticket_detail, "Retrieve one authorised selected-machine maintenance ticket by its exact TCK- identifier."),
        OperationDefinition("orders", "orders", OrdersParameters, False, handlers._orders, "Retrieve the authenticated company's orders with filters, shipment statuses, and list-completeness metadata. Use an ORD- identifier only in order_id and a QTE- identifier only in quote_id."),
        OperationDefinition("orders", "quotes", QuotesParameters, False, handlers._quotes, "Retrieve the authenticated company's quotes with filters, revisions, validity, totals, and list-completeness metadata. Use a QTE- identifier in quote_id."),
        OperationDefinition("orders", "order_detail", OrderDetailParameters, False, handlers._order_detail, "Retrieve the authenticated company's detail for one order identified by an exact ORD- identifier, including fulfilment and approved quote content."),
        OperationDefinition("orders", "quote_history", QuoteHistoryParameters, False, handlers._quote_history, "Retrieve the authenticated company's revision history for one quote identified by an exact QTE- identifier."),
    ]
)
