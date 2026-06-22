import httpx
from datetime import date
from typing import Any
from functools import lru_cache
from itertools import chain
import logging

from app.config import settings

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """Normalize name for matching (lowercase, strip extra spaces)."""
    return " ".join(name.lower().split())


class AcuityClient:
    """Acuity Scheduling API client (async)."""

    def __init__(self):
        self.base_url = settings.acuity_api_url
        self.api_key = settings.acuity_api_key
        self.user_id = settings.acuity_user_id
        self._client = None
        self._cache_version = 0  # Increment to invalidate cache

    async def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                params={"api_key": self.api_key, "owner": self.user_id},
                headers={"Accept": "application/json"},
                timeout=30.0,
            )
        return self._client

    async def get_appointments(
        self, min_date: date | None = None, max_date: date | None = None, status: str | None = None
    ) -> list[dict]:
        """Get appointments with optional filters."""
        params = {}
        if min_date:
            params["minDate"] = min_date.isoformat()
        if max_date:
            params["maxDate"] = max_date.isoformat()
        if status:
            params["show"] = "all"
        client = await self.client()
        r = await client.get("/appointments", params=params)
        r.raise_for_status()
        results = r.json()
        if status:
            results = [a for a in results if a.get("status") == status]
        return results

    async def get_appointment(self, appointment_id: int) -> dict:
        """Get single appointment by ID."""
        client = await self.client()
        r = await client.get(f"/appointments/{appointment_id}")
        r.raise_for_status()
        return r.json()

    async def check_availability(
        self, appointment_type_id: int, calendar_id: int, date: date
    ) -> list[dict]:
        """Get available slots for appointment type, calendar, and date."""
        client = await self.client()
        r = await client.get(
            "/availability/availabilities",
            params={
                "appointmentTypeID": appointment_type_id,
                "calendarID": calendar_id,
                "date": date.isoformat(),
            },
        )
        r.raise_for_status()
        return r.json()

    async def get_appointment_types(self, use_cache: bool = True) -> list[dict]:
        """Get all appointment types (cached)."""
        if use_cache:
            return await self._get_cached_appointment_types()
        client = await self.client()
        r = await client.get("/appointment-types")
        r.raise_for_status()
        return r.json()

    async def _get_cached_appointment_types(self) -> list[dict]:
        """Internal cached getter."""
        cache_key = f"appt_types_{self._cache_version}"
        if hasattr(self, "_cached_appt_types"):
            return self._cached_appt_types
        client = await self.client()
        r = await client.get("/appointment-types")
        r.raise_for_status()
        self._cached_appt_types = r.json()
        return self._cached_appt_types

    async def get_calendars(self, use_cache: bool = True) -> list[dict]:
        """Get all calendars (providers) (cached)."""
        if use_cache:
            return await self._get_cached_calendars()
        client = await self.client()
        r = await client.get("/calendars")
        r.raise_for_status()
        return r.json()

    async def _get_cached_calendars(self) -> list[dict]:
        """Internal cached getter."""
        if hasattr(self, "_cached_calendars"):
            return self._cached_calendars
        client = await self.client()
        r = await client.get("/calendars")
        r.raise_for_status()
        self._cached_calendars = r.json()
        return self._cached_calendars

    def invalidate_cache(self):
        """Invalidate cached calendars/appointment types."""
        self._cache_version += 1
        self._cached_calendars = None
        self._cached_appt_types = None

    async def get_clients(self, email: str | None = None, phone: str | None = None) -> list[dict]:
        """Get clients, optionally filtered by email or phone."""
        params = {}
        if email:
            params["email"] = email
        if phone:
            params["phone"] = phone
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

    async def create_client(self, data: dict) -> dict:
        """Create new client. Returns client data with ID."""
        client = await self.client()
        r = await client.post("/clients", json=data)
        r.raise_for_status()
        return r.json()

    async def book_appointment(self, data: dict) -> dict:
        """Create new appointment. Returns appointment data with ID."""
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

    async def cancel_appointment(self, appointment_id: int, note: str | None = None) -> dict:
        """Cancel appointment."""
        data = {"cancel": True}
        if note:
            data["note"] = note
        client = await self.client()
        r = await client.put(f"/appointments/{appointment_id}", json=data)
        r.raise_for_status()
        return r.json()

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def find_calendar(self, calendars: list[dict], name: str) -> dict | None:
        """Find calendar by exact or fuzzy name match."""
        target = normalize_name(name)
        # Exact match first
        for cal in calendars:
            if normalize_name(cal.get("name", "")) == target:
                return cal
        # Fuzzy: contains match
        for cal in calendars:
            if target in normalize_name(cal.get("name", "")):
                logger.warning(f"Fuzzy calendar match: '{name}' -> '{cal.get('name')}'")
                return cal
        return None

    def find_appointment_type(self, types: list[dict], name: str) -> dict | None:
        """Find appointment type by exact or fuzzy name match."""
        target = normalize_name(name)
        # Exact match first
        for t in types:
            if normalize_name(t.get("name", "")) == target:
                return t
        # Fuzzy: contains match
        for t in types:
            if target in normalize_name(t.get("name", "")):
                logger.warning(f"Fuzzy appointment type match: '{name}' -> '{t.get('name')}'")
                return t
        return None


# Singleton instance
acuity = AcuityClient()
