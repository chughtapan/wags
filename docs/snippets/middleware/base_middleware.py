from wags.middleware.base import WagsMiddlewareBase


class MyWAGSMiddleware(WagsMiddlewareBase):
    def __init__(self, handlers):
        super().__init__(handlers)

    async def handle_on_tool_call(self, context, handler):
        # Custom processing logic here
        return await super().handle_on_tool_call(context, handler)