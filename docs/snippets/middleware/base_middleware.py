from wags.middleware.base import BaseMiddleware


class MyWAGSMiddleware(BaseMiddleware):
    def __init__(self, handlers):
        super().__init__(handlers)

    async def handle_on_tool_call(self, context, handler):
        # Access handler's decorators and annotations
        return await super().handle_on_tool_call(context, handler)