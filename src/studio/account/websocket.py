import asyncio
import json
import traceback
from typing import Callable, Dict

from ...logger import logger

try:
    from ....External.websockets.server import serve
    from ....External.websockets.exceptions import ConnectionClosedOK, ConnectionClosed
except Exception:
    from websockets.server import serve
    from websockets import WebSocketServerProtocol
    from websockets.exceptions import ConnectionClosedOK, ConnectionClosed


class WebSocketClient:
    """WebSocket 服务器客户端

    用于在本地启动 WebSocket 服务器，接收浏览器登录页面的回调消息。
    """

    _host = "127.0.0.1"

    def __init__(self, port: int):
        self.host = self._host
        self.port = port
        self.logger = logger
        self._handlers: Dict[str, Callable] = {}
        self.stop_event = asyncio.Event()

        # 注册默认处理器
        self.reg_handler("_default", self._default)
        self.reg_handler("query_status", self._query_status)

    def reg_handler(self, etype: str, handler: Callable):
        self._handlers[etype] = handler

    def unreg_handler(self, etype: str):
        if etype in self._handlers:
            del self._handlers[etype]

    async def call_handler(self, websocket: "WebSocketServerProtocol", message: str):
        try:
            event: dict = json.loads(message)
        except json.JSONDecodeError:
            return

        if not isinstance(event, dict):
            event = {}

        etype = event.get("type", "_default")
        handler = self._handlers.get(etype, self._default)

        try:
            await handler(self, websocket, event)
        except Exception as e:
            self.logger.error(f"Error in handler {handler.__name__}: {e}")
            self.logger.error(traceback.format_exc())

    @staticmethod
    async def _default(server: "WebSocketClient", websocket: "WebSocketServerProtocol", event: dict):
        try:
            server.logger.warning(f"默认消息: {event}")
            response = {
                "type": "default",
                "data": event,
            }
            await websocket.send(json.dumps(response))
        except ConnectionClosedOK:
            pass

    @staticmethod
    async def _query_status(server: "WebSocketClient", websocket: "WebSocketServerProtocol", event: dict):
        try:
            server.logger.warning(f"查询状态: {event}")
            response = {
                "type": "query_status_return",
                "data": {
                    "status": "ok",
                    "host": "Blender",
                },
            }
            await websocket.send(json.dumps(response))
        except ConnectionClosedOK:
            pass

    async def handle(self, websocket: "WebSocketServerProtocol", path: str):
        try:
            self.logger.debug(f"Client Connected: {websocket}")
            async for message in websocket:
                await self.call_handler(websocket, message)
        except ConnectionClosed as e:
            self.logger.debug(f"客户端断开: {e.code} (code={e.code}, reason='{e.reason}')")
        except Exception as e:
            self.logger.critical(f"客户端异常: {e}")

    async def main(self):
        async with serve(self.handle, self.host, self.port, max_size=None):
            self.logger.warning(f"Server running on port {self.port}")
            await self.stop_event.wait()

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.main())
