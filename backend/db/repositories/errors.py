"""Domain-specific lookup errors raised by repositories."""

class MachineNotFoundError(LookupError):
    """The requested machine identifier does not exist."""

class MachineUnavailableError(LookupError):
    """The requested machine must not disclose whether it exists or is accessible."""

class TicketNotFoundError(LookupError):
    """The requested ticket is absent from the authorised machine."""

class QuoteNotFoundError(LookupError):
    """The requested quote is absent or outside the user's company."""

class OrderNotFoundError(LookupError):
    """The requested order is absent or outside the user's company."""
