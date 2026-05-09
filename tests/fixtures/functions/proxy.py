"""Authenticated function that forwards a request to PostgREST via ctx.postgrest."""


async def handler(req, ctx):
    resource = req.query_params.get("resource", "/todos")
    resp = await ctx.postgrest.get(resource)
    return resp.json()
