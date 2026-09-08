"""Validated planner parameters for each allowed operation."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.alarm_codes import normalise_alarm_code


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
