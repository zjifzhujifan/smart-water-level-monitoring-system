from __future__ import annotations

from typing import Any

import requests


class ApiError(RuntimeError):
    pass


class WaterMonitorApi:
    def __init__(self, base_url: str, timeout: float = 5) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: str | None = None
        self.user: dict[str, Any] | None = None

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        merged_headers = {**self.headers, **headers}
        try:
            response = requests.request(
                method,
                url,
                timeout=self.timeout,
                headers=merged_headers,
                **kwargs,
            )
        except requests.RequestException as exc:
            raise ApiError(f"无法连接后端服务: {exc}") from exc

        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            text = response.text[:300]
            raise ApiError(f"{method} {path} 失败: HTTP {response.status_code} {text}")
        if not response.content:
            return None
        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def login(self, username: str, password: str) -> dict[str, Any]:
        data = self._request(
            "POST",
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"Content-Type": "application/json"},
        )
        self.token = data["token"]
        self.user = data
        return data

    def user_info(self) -> dict[str, Any] | None:
        return self._request("GET", "/api/auth/user-info")

    def devices(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/device/list") or []

    def latest(self, device_id: int) -> dict[str, Any] | None:
        return self._request("GET", f"/api/water-level/latest/{device_id}")

    def history(
        self,
        device_id: int | None = None,
        device_code: str | None = None,
        page_num: int = 1,
        page_size: int = 200,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"pageNum": page_num, "pageSize": page_size}
        if device_id:
            params["deviceId"] = device_id
        if device_code:
            params["deviceCode"] = device_code
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._request("GET", "/api/water-level/history", params=params) or {}

    def water_statistics(self, device_id: int) -> dict[str, Any]:
        return self._request("GET", "/api/water-level/statistics", params={"deviceId": device_id}) or {}

    def alarms(
        self,
        device_id: int | None = None,
        is_resolved: int | None = None,
        page_num: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"pageNum": page_num, "pageSize": page_size}
        if device_id:
            params["deviceId"] = device_id
        if is_resolved is not None:
            params["isResolved"] = is_resolved
        return self._request("GET", "/api/alarm/list", params=params) or {}

    def alarm_statistics(self) -> dict[str, Any]:
        return self._request("GET", "/api/alarm/statistics") or {}

    def resolve_alarm(self, alarm_id: int) -> Any:
        return self._request("PUT", f"/api/alarm/resolve/{alarm_id}")

    def resolve_all_alarms(self) -> Any:
        return self._request("PUT", "/api/alarm/resolve-all")

    def trend(
        self,
        device_id: int,
        start_time: str | None = None,
        end_time: str | None = None,
        window_size: int = 5,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"deviceId": device_id, "windowSize": window_size}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._request("GET", "/api/analysis/trend", params=params) or {}

    def analysis_report(
        self,
        device_id: int,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"deviceId": device_id}
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
        return self._request("GET", "/api/analysis/report", params=params) or {}

    def upload_simulated(
        self,
        device_code: str,
        water_level: float,
        raw_value: int,
        warning_level: float,
        danger_level: float,
    ) -> dict[str, Any]:
        payload = {
            "deviceCode": device_code,
            "waterLevel": water_level,
            "rawValue": raw_value,
            "warningLevel": warning_level,
            "dangerLevel": danger_level,
        }
        return self._request(
            "POST",
            "/api/water-level/upload",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
