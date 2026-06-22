import httpx
from datetime import date
from typing import Any

from app.config import settings


class AcuityClient:
    """Acuity Scheduling API client."""

    def __init__(self):
        self.base_url = settings.acuity_api_url
        self.api_key = settings.acuity_api_key
        self.user_id = settings.acuity_user_id
        self._client = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                params={"api_key": self.api_key, "owner": self.user_id},
                headers={"Accept": "application/json"},
                timeout=30.0,
            )
        return self._client

    def get_appointments(
        self, min_date: date | None = None, max_date: date | None = None, status: str | None = None
    ) -> list[dict]:
        """Get appointments with optional filters."""
        params = {}
        if min_date:
            params["minDate"] = min_date.isoformat()
        if max_date:
            params["maxDate"] = max_date.isoformat()
        if status:
            params["show"] = "all"  # needed to see canceled appointments
        r = self.client.get("/appointments", params=params)
        r.raise_for_status()
        results = r.json()
        if status:
            results = [a for a in results if a.get("status") == status]
        return results

    def get_appointment(self, appointment_id: int) -> dict:
        """Get single appointment by ID."""
        r = self.client.get(f"/appointments/{appointment_id}")
        r.raise_for_status()
        return r.json()

    def check_availability(
        self, appointment_type_id: int, calendar_id: int, date: date
    ) -> list[dict]:
        """Get available slots for appointment type, calendar, and date."""
        r = self.client.get(
            "/availability/availabilities",
            params={
                "appointmentTypeID": appointment_type_id,
                "calendarID": calendar_id,
                "date": date.isoformat(),
            },
        )
        r.raise_for_status()
        return r.json()

    def get_appointment_types(self) -> list[dict]:
        """Get all appointment types."""
        r = self.client.get("/appointment-types")
        r.raise_for_status()
        return r.json()

    def get_calendars(self) -> list[dict]:
        """Get all calendars (providers)."""
        r = self.client.get("/calendars")
        r.raise_for_status()
        return r.json()

    def get_clients(self, email: str | None = None, phone: str | None = None) -> list[dict]:
        """Get clients, optionally filtered by email or phone."""
        params = {}
        if email:
            params["email"] = email
        if phone:
            params["phone"] = phone
        r = self.client.get("/clients", params=params)
        r.raise_for_status()
        return r.json()

    def get_client(self, client_id: int) -> dict:
        """Get single client by ID."""
        r = self.client.get(f"/clients/{client_id}")
        r.raise_for_status()
        return r.json()

    def create_client(self, data: dict) -> dict:
        """Create new client. Returns client data with ID."""
        r = self.client.post("/clients", json=data)
        r.raise_for_status()
        return r.json()

    def book_appointment(self, data: dict) -> dict:
        """
        Create new appointment.
        Returns appointment data with ID.
        """
        r = self.client.post("/appointments", json=data)
        r.raise_for_status()
        return r.json()

    def update_appointment(self, appointment_id: int, data: dict) -> dict:
        """Update existing appointment."""
        r = self.client.put(f"/appointments/{appointment_id}", json=data)
        r.raise_for_status()
        return r.json()

    def cancel_appointment(self, appointment_id: int, note: str | None = None) -> dict:
        """Cancel appointment."""
        data = {"cancel": True}
        if note:
            data["note"] = note
        r = self.client.put(f"/appointments/{appointment_id}", json=data)
        r.raise_for_status()
        return r.json()

    def close(self):
        """Close the HTTP client."""
        if self._client:
            self._client.close()


# Singleton instance
acuity = AcuityClient()
