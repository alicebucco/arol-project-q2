# ADR 0012: Consistent UI feedback for loading, empty and error states

## Context

The platform loads machines, operational data, business records, manual search results and AI responses from a local backend. A blank screen or a raw technical error would make it unclear whether a request is still in progress, returned no data, or failed.

## Decision

The frontend presents a visible loading state for every asynchronous view, a dedicated empty state when a successful request has no records, and a readable error message when a request fails. It also uses short, non-blocking notifications for completed actions and failures.

Network errors, expired sessions and server errors are translated into user-facing English messages. An expired JWT clears the local session and returns the user to the login page with an explanation.

## Consequences

- Users can distinguish a successful empty result from a loading or failed request.
- Errors remain visible in the relevant page or panel, while the notification gives immediate feedback.
- The approach is reusable without adding an external notification library.
- Technical backend details are not deliberately exposed in the interface.
