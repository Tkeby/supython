from ..jobs.decorators import job


@job("send_auth_email", max_attempts=5, backoff="exponential", backoff_base_s=10.0)
async def send_auth_email(ctx, payload):
    await ctx.send_email(
        to=payload["to"],
        subject=payload["subject"],
        text=payload["text"],
        html=payload.get("html"),
    )
