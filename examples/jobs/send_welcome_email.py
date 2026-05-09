"""Example: send a welcome email via @app.job + @app.on_signup."""

from supython.jobs.decorators import job
from supython import hooks


@job("send_welcome_email", version=1, accepts_payload=False, max_attempts=5)
async def send_welcome_email(ctx):
    user_id = ctx.job_id
    await ctx.send_email(
        to="user@example.com",
        subject="Welcome!",
        text="Thanks for signing up.",
    )


@hooks.on("signup")
async def on_signup(user, ctx):
    from supython.jobs.service import enqueue as svc_enqueue

    await svc_enqueue(
        ctx.db,
        name="send_welcome_email",
        idempotency_key=f"welcome:{user.id}",
    )
