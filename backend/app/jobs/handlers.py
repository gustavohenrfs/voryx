"""Job handler registry. Each module's handlers are registered here."""

from app.channels.service import refresh_for_account
from app.jobs.runner import Handler, JobContext
from app.joins.handlers import approve_all, approve_join, reject_join
from app.posts.service import on_send_fail, on_send_retry, send_post


async def sync_channels(ctx: JobContext) -> None:
    await refresh_for_account(ctx.db, ctx.job.payload.get("account_id", ctx.job.account_id), ctx.manager)


HANDLERS: dict[str, Handler] = {
    "sync_channels": sync_channels,
    "approve_join": approve_join,
    "reject_join": reject_join,
    "approve_all": approve_all,
    "send_post": send_post,
}
FAIL_HOOKS: dict[str, Handler] = {"send_post": on_send_fail}
RETRY_HOOKS: dict[str, Handler] = {"send_post": on_send_retry}
