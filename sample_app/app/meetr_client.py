"""HTTP client for the Meetr Partner API.

All calls use the organization's API key (stored server-side).
No admin API calls — this is what a real third-party app would use.
"""

import logging
import httpx

logger = logging.getLogger(__name__)


class MeetrClient:
    """Proxy to the Meetr Partner API."""

    def __init__(self, base_url: str, api_key: str, customer_id: str):
        self._base_url = base_url
        self._api_key = api_key
        self._customer_id = customer_id
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    def _headers(self) -> dict:
        return {
            "X-API-Key": self._api_key,
            "X-Customer-Id": self._customer_id,
        }

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Make an API request and return {status, data}.

        Error messages are normalized into data["detail"] for consistent
        extraction regardless of the API's error format.
        """
        resp = await self._http.request(method, f"{self._base_url}{path}", headers=self._headers(), **kwargs)
        try:
            data = resp.json()
        except Exception:
            data = {"detail": resp.text}

        # Normalize error messages into "detail" for consistent access
        if resp.status_code >= 400 and "detail" not in data:
            if isinstance(data.get("error"), dict):
                data["detail"] = data["error"].get("message") or data["error"].get("code") or str(data["error"])
            elif isinstance(data.get("error"), str):
                data["detail"] = data["error"]
            elif isinstance(data.get("message"), str):
                data["detail"] = data["message"]
            else:
                data["detail"] = f"HTTP {resp.status_code}: {resp.text[:200]}"

        return {"status": resp.status_code, "data": data}

    # --- Health ---

    async def health_check(self) -> bool:
        """Check if the Meetr service is reachable."""
        try:
            resp = await self._http.get(f"{self._base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False

    # --- Meetings ---

    async def create_meeting(self, data: dict) -> dict:
        return await self._request("POST", "/api/meetings", json=data)

    async def list_meetings(self, state: str | None = None, requester: str | None = None) -> dict:
        params = {}
        if state:
            params["state"] = state
        if requester:
            params["requester"] = requester
        return await self._request("GET", "/api/meetings", params=params)

    async def get_meeting(self, meeting_id: str) -> dict:
        return await self._request("GET", f"/api/meetings/{meeting_id}")

    async def cancel_meeting(self, meeting_id: str) -> dict:
        return await self._request("POST", f"/api/meetings/{meeting_id}/cancel")

    async def intervene(self, meeting_id: str, message: str) -> dict:
        return await self._request("POST", f"/api/meetings/{meeting_id}/intervene", json={"message": message})

    async def select_slot(self, meeting_id: str) -> dict:
        return await self._request("POST", f"/api/meetings/{meeting_id}/select-slot")

    async def notify_participants(self, meeting_id: str) -> dict:
        return await self._request("POST", f"/api/meetings/{meeting_id}/notify")

    # --- Outreach ---

    async def start_outreach(self, meeting_id: str, participant_id: str) -> dict:
        return await self._request("POST", f"/api/meetings/{meeting_id}/outreach/{participant_id}/start")

    async def get_outreach_detail(self, meeting_id: str, participant_id: str) -> dict:
        return await self._request("GET", f"/api/meetings/{meeting_id}/outreach/{participant_id}")

    async def force_fail_outreach(self, meeting_id: str, participant_id: str) -> dict:
        return await self._request("POST", f"/api/meetings/{meeting_id}/outreach/{participant_id}/force-fail")
