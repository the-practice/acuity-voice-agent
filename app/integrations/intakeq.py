import httpx
from datetime import date
from typing import Any

from app.config import settings


class IntakeQClient:
    """IntakeQ API client."""

    def __init__(self):
        self.base_url = settings.intakeq_api_url
        self.api_key = settings.intakeq_api_key
        self._client = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"X-Auth-Token": self.api_key, "Accept": "application/json"},
                timeout=30.0,
            )
        return self._client

    def get_clients(self, search: str | None = None) -> list[dict]:
        """
        Get clients.
        search: email, phone, or name
        """
        params = {}
        if search:
            params["search"] = search
        r = self.client.get("/clients", params=params)
        r.raise_for_status()
        return r.json()

    def get_client(self, client_id: int) -> dict:
        """Get single client by ID."""
        r = self.client.get(f"/clients/{client_id}")
        r.raise_for_status()
        return r.json()

    def get_appointments(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[dict]:
        """Get appointments with date range filter."""
        params = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        r = self.client.get("/appointments", params=params)
        r.raise_for_status()
        return r.json()

    def get_appointment(self, appointment_id: int) -> dict:
        """Get single appointment by ID."""
        r = self.client.get(f"/appointments/{appointment_id}")
        r.raise_for_status()
        return r.json()

    def create_appointment(self, data: dict) -> dict:
        """Create new appointment in IntakeQ (for billing sync)."""
        r = self.client.post("/appointments", json=data)
        r.raise_for_status()
        return r.json()

    def update_appointment(self, appointment_id: int, data: dict) -> dict:
        """Update existing appointment."""
        r = self.client.put(f"/appointments/{appointment_id}", json=data)
        r.raise_for_status()
        return r.json()

    def get_questionnaires(self, client_id: int) -> list[dict]:
        """Get questionnaires for a client."""
        r = self.client.get(f"/clients/{client_id}/intakes")
        r.raise_for_status()
        return r.json()

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()


# Singleton instance
intakeq = IntakeQClient()
