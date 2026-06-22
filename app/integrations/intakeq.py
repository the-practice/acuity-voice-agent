import httpx
from datetime import date
from typing import Any

from app.config import settings


class IntakeQClient:
    """IntakeQ API client (async)."""

    def __init__(self):
        self.base_url = settings.intakeq_api_url
        self.api_key = settings.intakeq_api_key
        self._client = None

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"X-Auth-Token": self.api_key, "Accept": "application/json"},
                timeout=30.0,
            )
        return self._client

    async def get_clients(self, search: str | None = None) -> list[dict]:
        """Get clients. search: email, phone, or name."""
        params = {}
        if search:
            params["search"] = search
        client = await self.client()
        r = await client.get("/clients", params=params)
        r.raise_for_status()
        return r.json()

    async def get_client(self, client_id: int) -> dict:
        """Get single client by ID."""
        client = await self.client()
        r = await client.get(f"/clients/{client_id}")
        r.raise_for_status()
        return r.json()

    async def get_appointments(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[dict]:
        """Get appointments with date range filter."""
        params = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        client = await self.client()
        r = await client.get("/appointments", params=params)
        r.raise_for_status()
        return r.json()

    async def get_appointment(self, appointment_id: int) -> dict:
        """Get single appointment by ID."""
        client = await self.client()
        r = await client.get(f"/appointments/{appointment_id}")
        r.raise_for_status()
        return r.json()

    async def create_appointment(self, data: dict) -> dict:
        """Create new appointment in IntakeQ (for billing sync)."""
        client = await self.client()
        r = await client.post("/appointments", json=data)
        r.raise_for_status()
        return r.json()

    async def update_appointment(self, appointment_id: int, data: dict) -> dict:
        """Update existing appointment."""
        client = await self.client()
        r = await client.put(f"/appointments/{appointment_id}", json=data)
        r.raise_for_status()
        return r.json()

    async def get_questionnaires(self, client_id: int) -> list[dict]:
        """Get questionnaires for a client."""
        client = await self.client()
        r = await client.get(f"/clients/{client_id}/intakes")
        r.raise_for_status()
        return r.json()

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Singleton instance
intakeq = IntakeQClient()
