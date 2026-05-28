from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import urlparse

import websocket
from PySide6.QtCore import QThread, Signal


def _stomp_frame(command: str, headers: dict[str, str] | None = None, body: str = "") -> str:
    lines = [command]
    for key, value in (headers or {}).items():
        lines.append(f"{key}:{value}")
    return "\n".join(lines) + "\n\n" + body + "\x00"


def _sockjs_payload(frame: str) -> str:
    return json.dumps([frame])


def _ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc or parsed.path
    session_id = uuid.uuid4().hex[:16]
    return f"{scheme}://{netloc}/ws/000/{session_id}/websocket"


def _parse_stomp_message(frame: str) -> tuple[str, dict[str, str], str]:
    frame = frame.rstrip("\x00")
    head, _, body = frame.partition("\n\n")
    lines = head.splitlines()
    command = lines[0] if lines else ""
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key] = value
    return command, headers, body


class StompSockJsClient(QThread):
    water_level = Signal(dict)
    alarm = Signal(dict)
    device_status = Signal(dict)
    status = Signal(str)
    error = Signal(str)

    def __init__(self, base_url: str, parent: Any = None) -> None:
        super().__init__(parent)
        self.base_url = base_url
        self._running = True
        self._ws: websocket.WebSocket | None = None

    def stop(self) -> None:
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def run(self) -> None:
        url = _ws_url(self.base_url)
        try:
            self.status.emit(f"连接实时推送: {url}")
            self._ws = websocket.create_connection(url, timeout=8)
            self._connect_and_subscribe()
            while self._running:
                raw = self._ws.recv()
                if not raw:
                    continue
                self._handle_raw(raw)
        except Exception as exc:
            if self._running:
                self.error.emit(f"实时推送连接失败: {exc}")
        finally:
            self.status.emit("实时推送已断开")

    def _connect_and_subscribe(self) -> None:
        assert self._ws is not None
        # SockJS opens with an "o" frame before STOMP frames are accepted.
        opened = self._ws.recv()
        if opened != "o":
            self.status.emit(f"SockJS 握手返回: {opened}")
        self._ws.send(_sockjs_payload(_stomp_frame("CONNECT", {"accept-version": "1.2", "heart-beat": "10000,10000"})))
        self._ws.send(_sockjs_payload(_stomp_frame("SUBSCRIBE", {"id": "water-level", "destination": "/topic/water-level"})))
        self._ws.send(_sockjs_payload(_stomp_frame("SUBSCRIBE", {"id": "device-status", "destination": "/topic/device-status"})))
        self._ws.send(_sockjs_payload(_stomp_frame("SUBSCRIBE", {"id": "alarm", "destination": "/topic/alarm"})))
        self.status.emit("实时推送订阅完成")

    def _handle_raw(self, raw: str) -> None:
        if raw in {"h", "o"}:
            return
        if not raw.startswith("a"):
            return
        try:
            frames = json.loads(raw[1:])
        except json.JSONDecodeError:
            return
        for frame in frames:
            command, headers, body = _parse_stomp_message(frame)
            if command == "CONNECTED":
                self.status.emit("实时推送已连接")
                continue
            if command != "MESSAGE":
                continue
            destination = headers.get("destination", "")
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                payload = {"raw": body}
            if destination == "/topic/water-level":
                self.water_level.emit(payload)
            elif destination == "/topic/device-status":
                self.device_status.emit(payload)
            elif destination == "/topic/alarm":
                self.alarm.emit(payload)
