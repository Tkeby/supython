"""Example: periodic cleanup cron job."""

from supython.jobs.decorators import cron


@cron("*/5 * * * *", name="cleanup", job_name="cleanup_job", accepts_payload=False)
async def cleanup_job(ctx):
    ctx.logger.info("running cleanup cron")
