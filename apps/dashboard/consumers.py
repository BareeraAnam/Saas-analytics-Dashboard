from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django_tenants.utils import get_public_schema_name, schema_context


class MetricsConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        # The Host header only chooses the schema. Login is checked separately
        # because the HTML page's login_required does not protect this socket.
        user = self.scope.get("user")
        tenant = self.scope.get("tenant")
        if (
            tenant is None
            or tenant.schema_name == get_public_schema_name()
            or not getattr(user, "is_authenticated", False)
            or not user.is_active
        ):
            await self.close()
            return
        self.schema = tenant.schema_name
        self.group = f"metrics_{self.schema}"
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()
        await self.send_json(await self._summary())

    async def disconnect(self, code):
        if hasattr(self, "group"):
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def metrics_update(self, event):
        # The publisher already computed the summary once. Recomputing here
        # would run the same query on every open dashboard.
        summary = event.get("summary")
        if summary is None:
            summary = await self._summary()
        await self.send_json(summary)

    @database_sync_to_async
    def _summary(self):
        from .services import get_summary
        with schema_context(self.schema):
            return get_summary()
