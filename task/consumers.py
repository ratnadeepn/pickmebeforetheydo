import json
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from accounts.models import User

class TaskConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        self.group_names = []

        if not user.is_authenticated:
            await self.close(code=4401)
            return

        if user.role == User.Role.STORE_MANAGER:
            self.group_names.append(
                f"manager_{user.id}"
            )

        elif user.role == User.Role.DELIVERY_PERSON:
            self.group_names.extend(
                ["delivery_all", f"delivery_{user.id}"]
            )

        else:
            await self.close(code=4403)
            return

        for group_name in self.group_names:
            await self.channel_layer.group_add(
                group_name,
                self.channel_name
            )

        await self.accept()

    async def disconnect(self, close_code):
        for group_name in getattr(self, "group_names", []):
            await self.channel_layer.group_discard(
                group_name,
                self.channel_name
            )

    async def task_event(self, event):
        await self.send(text_data=json.dumps(
            event["payload"]
            )
        )