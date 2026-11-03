"""Job handler registry. Filled by channels/joins/posts modules."""

from app.jobs.runner import Handler

HANDLERS: dict[str, Handler] = {}
FAIL_HOOKS: dict[str, Handler] = {}
RETRY_HOOKS: dict[str, Handler] = {}
