"""Minimal asserts for the logic touched by the fix pass. No framework needed:

    python -m tests.test_smoke

Pure logic only — no DB/Redis/network, so it runs anywhere.
"""
import asyncio
from datetime import date

from app.integrations.vapi import VapiFunctionCall
from app.integrations.acuity import normalize_name, AcuityClient
from app.services.state import CallState


def test_vapi_function_call_accepts_both_arg_shapes():
    # Vapi sends "parameters"; we also accept "arguments". call_id no longer required.
    a = VapiFunctionCall(name="check_availability", parameters={"date": "2026-06-22"})
    b = VapiFunctionCall(name="check_availability", arguments={"date": "2026-06-22"})
    assert a.arguments == b.arguments == {"date": "2026-06-22"}
    assert VapiFunctionCall(name="x").arguments == {}  # missing args -> empty, no crash


def test_date_parsing():
    assert date.fromisoformat("2026-06-22") == date(2026, 6, 22)


def test_acuity_cache_survives_invalidation():
    c = AcuityClient()
    c._cached_appt_types = [{"id": 1, "name": "Initial"}]
    assert c.find_appointment_type(c._cached_appt_types, "initial")["id"] == 1
    c.invalidate_cache()
    assert c._cached_appt_types is None  # not a stale None lurking behind hasattr


def test_calendar_fuzzy_match():
    cals = [{"id": 9, "name": "Dr. Jane Smith"}]
    assert AcuityClient().find_calendar(cals, "smith")["id"] == 9
    assert AcuityClient().find_calendar(cals, "nobody") is None


def test_callstate_memory_fallback_isolates_keys():
    cs = CallState()  # _enabled=False -> in-memory path

    async def run():
        await cs.set("call1", "outcome", "booked")
        await cs.set("call1", "appointment_id", 42)
        assert await cs.get("call1", "outcome") == "booked"
        assert await cs.get("call1", "appointment_id") == 42  # set didn't clobber
        assert await cs.get("missing", "outcome") is None

    asyncio.run(run())


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
