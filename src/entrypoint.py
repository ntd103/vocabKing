"""Worker entrypoint: verify the Telegram webhook secret, forward to the DO.

Uses RPC (a plain method call on the DO stub) instead of forwarding the raw
HTTP request — RPC is the recommended way to talk to a DO from a Worker.
"""

from workers import Response, WorkerEntrypoint

# The DO class must be re-exported from the worker's main module.
from vocab_do import VocabularyDO  # noqa: F401 — re-export for wrangler


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        expected = self.env.WEBHOOK_SECRET
        if not expected or secret != expected:
            return Response("forbidden", status=403)

        update = await request.json()
        stub = self.env.VOCAB_DO.getByName("owner")
        await stub.handle_update(update)
        return Response("ok")
