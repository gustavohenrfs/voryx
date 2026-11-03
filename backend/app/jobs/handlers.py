"""Job handler registry. Each module's handlers are registered here."""

from app.channels.service import refresh_for_account
from app.jobs.runner import Handler, JobContext


async def sync_channels(ctx: JobContext) -> None:
    await refresh_for_account(ctx.db, ctx.job.payload.get("account_id", ctx.job.account_id), ctx.manager)


HANDLERS: dict[str, Handler] = {
    "sync_channels": sync_channels,
}
FAIL_HOOKS: dict[str, Handler] = {}
RETRY_HOOKS: dict[str, Handler] = {}
