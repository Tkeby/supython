# functions/

Drop a `.py` file here and supython will serve it under `POST /functions/<name>` — no server restart required.

```python
# functions/hello.py
auth = "anon"          # "anon" | "authenticated" (default)
methods = ["GET", "POST"]

async def handler(req, ctx):
    name = ctx.user.email if ctx.user else "world"
    return {"msg": f"hello, {name}"}
```

`ctx` gives you:
- `ctx.db` — a role-scoped `asyncpg.Connection` (RLS already applied)
- `ctx.user` — caller identity (`id`, `email`, `role`, `claims`)
- `ctx.storage` — `upload / download / sign` over the storage subsystem
- `ctx.postgrest` — `httpx.AsyncClient` pre-authed with the caller's JWT
- `ctx.send_email(to=..., subject=..., text=...)` — send transactional email
- `ctx.request` — the raw FastAPI `Request` (escape hatch)
