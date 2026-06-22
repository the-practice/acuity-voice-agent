from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, Depends, Header
from fastapi.concurrency import run_in_threadpool
from datetime import datetime, date
import logging

from app.config import settings
from app.db.session import SessionLocal
from app.db.models import CallLog, ReviewItem, Client
from app.integrations.acuity import acuity
from app.integrations.intakeq import intakeq
from app.integrations.vapi import VapiFunctionCall, FUNCTION_DESCRIPTIONS, SYSTEM_PROMPT
from app.services.state import call_state

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup/shutdown."""
    await call_state.init()
    yield
    await acuity.close()
    await intakeq.close()
    await call_state.close()


app = FastAPI(title="The Practice Voice Agent", lifespan=lifespan)


@app.get("/")
def health():
    return {"status": "healthy", "service": "thepractice-voice-agent"}


@app.post("/webhooks/vapi")
async def vapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_vapi_secret: str | None = Header(default=None),
):
    """Handle Vapi webhooks - function calls and events."""
    # ponytail: shared-secret check. Set the same value as Vapi's Server Secret;
    # match the header name to your Vapi config if it isn't X-Vapi-Secret.
    if not settings.vapi_auth_token or x_vapi_secret != settings.vapi_auth_token:
        raise HTTPException(status_code=401, detail="unauthorized")

    payload = await request.json()
    # Newer Vapi wraps events under "message"; tolerate both shapes.
    msg = payload.get("message", payload)

    event_type = msg.get("type")
    call_id = (msg.get("call") or {}).get("id")

    if event_type == "assistant-request":
        return {
            "response": {
                "assistant": {
                    "firstMessage": "Thank you for calling The Practice. How can I help you today?",
                    "systemPrompt": SYSTEM_PROMPT,
                    "functions": FUNCTION_DESCRIPTIONS,
                }
            }
        }

    elif event_type == "function-call":
        func_call = VapiFunctionCall(**(msg.get("functionCall") or {}))
        return await handle_function_call(func_call, call_id, background_tasks)

    elif event_type == "conversation-update":
        background_tasks.add_task(log_call_completed, msg)
        return {"status": "logged"}

    return {"status": "received"}


async def handle_function_call(
    func_call: VapiFunctionCall, call_id: str, background_tasks: BackgroundTasks
) -> dict:
    """Route and execute Vapi function calls."""
    try:
        if func_call.name == "check_availability":
            return await check_availability(func_call.arguments)

        elif func_call.name == "book_appointment":
            return await book_appointment(func_call.arguments, call_id, background_tasks)

        elif func_call.name == "lookup_client":
            return await lookup_client(func_call.arguments)

        elif func_call.name == "answer_question":
            return await answer_question(func_call.arguments)

        elif func_call.name == "transfer_to_human":
            return await transfer_to_human(func_call.arguments, call_id)

        elif func_call.name == "take_message":
            return await take_message(func_call.arguments, call_id)

        else:
            return {"error": f"Unknown function: {func_call.name}"}

    except Exception as e:
        logger.error(f"Function call error: {e}", exc_info=True)
        return {"error": str(e)}


async def check_availability(args: dict) -> dict:
    """Check available slots for provider + appointment type + date."""
    provider_name = args.get("provider_name")
    appt_type = args.get("appointment_type")
    date_str = args.get("date")

    try:
        appt_date = date.fromisoformat(date_str)
    except (ValueError, TypeError, AttributeError):
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    # Get calendars and appointment types (cached)
    calendars = await acuity.get_calendars()
    appt_types = await acuity.get_appointment_types()

    # Find matching calendar
    calendar = acuity.find_calendar(calendars, provider_name)
    if not calendar:
        return {"error": f"Provider '{provider_name}' not found."}

    # Find matching appointment type
    appt_type_obj = acuity.find_appointment_type(appt_types, appt_type)
    if not appt_type_obj:
        return {"error": f"Appointment type '{appt_type}' not found."}

    slots = await acuity.check_availability(
        appointment_type_id=appt_type_obj["id"],
        calendar_id=calendar["id"],
        date=appt_date,
    )

    if not slots:
        return {
            "available": False,
            "message": f"No available slots for {provider_name} on {date_str}. Would you like to check another date?"
        }

    available_times = [slot.get("time") for slot in slots[:5]]
    return {
        "available": True,
        "date": date_str,
        "times": available_times,
        "message": f"Available times on {date_str} with {provider_name}: {', '.join(available_times)}"
    }


async def book_appointment(args: dict, call_id: str, background_tasks: BackgroundTasks) -> dict:
    """Book a new appointment in Acuity."""
    email = args.get("client_email")
    name = args.get("client_name")
    phone = args.get("client_phone")
    provider_name = args.get("provider_name")
    appt_type = args.get("appointment_type")
    date_str = args.get("date")
    time_str = args.get("time")
    is_new = args.get("is_new_patient", True)

    if not all([email, name, provider_name, appt_type, date_str, time_str]):
        return {"error": "Missing required fields."}

    calendars = await acuity.get_calendars()
    appt_types = await acuity.get_appointment_types()

    calendar = acuity.find_calendar(calendars, provider_name)
    appt_type_obj = acuity.find_appointment_type(appt_types, appt_type)

    if not calendar:
        return {"error": f"Provider '{provider_name}' not found."}
    if not appt_type_obj:
        return {"error": f"Appointment type '{appt_type}' not found."}

    # Don't split names - let Acuity handle it
    appt_data = {
        "firstName": "",
        "lastName": "",
        "name": name,  # Send full name
        "email": email,
        "phone": phone,
        "appointmentTypeID": appt_type_obj["id"],
        "calendarID": calendar["id"],
        "date": date_str,
        "time": time_str,
    }

    result = await acuity.book_appointment(appt_data)

    await call_state.set(call_id, "outcome", "booked")
    await call_state.set(call_id, "appointment_id", result.get("id"))

    background_tasks.add_task(
        log_booking,
        call_id=call_id,
        appointment_id=result.get("id"),
        client_email=email,
        provider_name=provider_name,
    )

    return {
        "success": True,
        "appointment_id": result.get("id"),
        "date": date_str,
        "time": time_str,
        "provider": provider_name,
        "message": f"Appointment confirmed for {date_str} at {time_str} with {provider_name}. You'll receive a confirmation email shortly."
    }


def _lookup_local_client(email: str | None, phone: str | None) -> dict | None:
    """Sync DB read; run via threadpool to avoid blocking the event loop."""
    db = SessionLocal()
    try:
        if email:
            c = db.query(Client).filter(Client.email == email).first()
        elif phone:
            c = db.query(Client).filter(Client.phone == phone).first()
        else:
            c = None
        return {"client_id": c.id, "name": c.name} if c else None
    finally:
        db.close()


def _upsert_acuity_client(client: dict) -> dict:
    """Sync DB upsert by acuity_id; returns local client info."""
    db = SessionLocal()
    try:
        acuity_id = client.get("id")
        existing = db.query(Client).filter(Client.acuity_id == acuity_id).first()
        if existing:
            return {"client_id": existing.id, "name": existing.name}
        new_client = Client(
            email=client.get("email"),
            phone=client.get("phone"),
            name=f"{client.get('firstName', '')} {client.get('lastName', '')}".strip(),
            acuity_id=acuity_id,
        )
        db.add(new_client)
        db.commit()
        return {"client_id": new_client.id, "name": new_client.name}
    finally:
        db.close()


async def lookup_client(args: dict) -> dict:
    """Lookup a returning client in IntakeQ and Acuity."""
    email = args.get("email")
    phone = args.get("phone")

    if not email and not phone:
        return {"error": "Email or phone required for lookup."}

    # Check local DB first
    local = await run_in_threadpool(_lookup_local_client, email, phone)
    if local:
        return {"found": True, **local, "is_returning": True}

    # Check Acuity
    acuity_clients = await acuity.get_clients(email=email, phone=phone)
    if acuity_clients:
        result = await run_in_threadpool(_upsert_acuity_client, acuity_clients[0])
        return {"found": True, **result, "is_returning": True}

    return {
        "found": False,
        "message": "Client not found in our system. This appears to be a new patient."
    }


async def answer_question(args: dict) -> dict:
    """Answer common questions from knowledge base."""
    question = args.get("question", "").lower()

    if any(word in question for word in ["hour", "open", "close", "time"]):
        return {
            "answer": "The Practice is open Monday through Friday, 9am to 5pm. We're closed on weekends."
        }
    elif any(word in question for word in ["location", "address", "where"]):
        return {
            "answer": "We're located at 123 Main Street, Suite 200. Parking is available in the adjacent lot."
        }
    elif any(word in question for word in ["insurance", "accept", "take"]):
        return {
            "answer": "We accept Aetna, Blue Cross Blue Shield, Cigna, and United Healthcare. Please contact us to verify your specific coverage."
        }
    elif any(word in question for word in ["telehealth", "online", "video", "zoom"]):
        return {
            "answer": "Yes, we offer telehealth appointments via secure video. You can request a telehealth appointment when scheduling."
        }
    elif "medication" in question or "prescription" in question:
        return {
            "answer": "For questions about medications or prescriptions, please speak with one of our providers directly. Let me transfer you.",
            "transfer": True
        }
    else:
        return {
            "answer": "I'd be happy to help with that. Let me connect you with a staff member who can better assist you.",
            "transfer": True
        }


async def transfer_to_human(args: dict, call_id: str) -> dict:
    """Transfer call to human."""
    reason = args.get("reason", "")
    summary = args.get("summary", "")

    await call_state.set(call_id, "outcome", "transferred")
    await call_state.set(call_id, "transfer_reason", reason)

    is_crisis = any(word in reason.lower() for word in ["crisis", "emergency", "suicide", "harm"])

    return {
        "transfer": True,
        "phone_number": settings.human_transfer_number or "+15555555555",
        "message": "Connecting you with a staff member now.",
        "is_crisis": is_crisis,
        "crisis_message": "If you're in immediate danger, please call 911 or 988 for the suicide and crisis lifeline." if is_crisis else None
    }


def _save_review_message(caller_name: str, caller_phone: str, message: str, urgency: str, call_id: str) -> None:
    db = SessionLocal()
    try:
        db.add(ReviewItem(
            type="message",
            severity=urgency,
            context={
                "caller_name": caller_name,
                "caller_phone": caller_phone,
                "message": message,
                "call_id": call_id,
            },
        ))
        db.commit()
    finally:
        db.close()


async def take_message(args: dict, call_id: str) -> dict:
    """Take a message and queue for follow-up."""
    caller_name = args.get("caller_name", "Unknown")
    caller_phone = args.get("caller_phone", "")
    message = args.get("message", "")
    urgency = args.get("urgency", "medium")

    await run_in_threadpool(_save_review_message, caller_name, caller_phone, message, urgency, call_id)
    await call_state.set(call_id, "outcome", "message")

    return {
        "success": True,
        "message": f"Thank you. I've taken your message and someone will get back to you within {24 if urgency == 'low' else 4 if urgency == 'medium' else 1} hours."
    }


def log_booking(call_id: str, appointment_id: int, client_email: str, provider_name: str):
    """Log successful booking to database."""
    db = SessionLocal()
    try:
        # Booking happens mid-call, before the end-of-call row exists — upsert.
        call_log = db.query(CallLog).filter(CallLog.vapi_call_id == call_id).first()
        if not call_log:
            call_log = CallLog(vapi_call_id=call_id)
            db.add(call_log)
        call_log.outcome = "booked"
        call_log.summary = f"Booked appointment {appointment_id} for {client_email} with {provider_name}"
        call_log.contains_phi = True  # summary holds patient email
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log booking: {e}")
    finally:
        db.close()


def log_call_completed(payload: dict):
    """Log call completion to database."""
    db = SessionLocal()
    try:
        call = payload.get("call", {})
        call_id = call.get("id")
        status = payload.get("status", "")

        existing = db.query(CallLog).filter(CallLog.vapi_call_id == call_id).first()
        if existing:
            existing.ended_at = datetime.utcnow()
            if status == "completed":
                existing.outcome = existing.outcome or "completed"
            db.commit()
            return

        call_log = CallLog(
            vapi_call_id=call_id,
            caller_phone=call.get("phoneNumber", {}).get("number"),
            started_at=datetime.fromisoformat(call.get("startedAt", "").replace("Z", "+00:00")) if call.get("startedAt") else None,
            ended_at=datetime.fromisoformat(call.get("endedAt", "").replace("Z", "+00:00")) if call.get("endedAt") else None,
            outcome=payload.get("outcome", "unknown"),
        )
        db.add(call_log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log call: {e}")
    finally:
        db.close()


def require_admin(authorization: str | None = Header(default=None)):
    """Bearer-token gate for admin endpoints (they return PHI)."""
    if not settings.admin_token or authorization != f"Bearer {settings.admin_token}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/admin/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    """Basic call statistics for admin dashboard."""
    db = SessionLocal()
    try:
        total_calls = db.query(CallLog).count()
        booked = db.query(CallLog).filter(CallLog.outcome == "booked").count()
        transferred = db.query(CallLog).filter(CallLog.outcome == "transferred").count()
        pending_reviews = db.query(ReviewItem).filter(ReviewItem.resolved_at == None).count()

        return {
            "total_calls": total_calls,
            "booked": booked,
            "transferred": transferred,
            "pending_reviews": pending_reviews,
        }
    finally:
        db.close()


@app.get("/admin/reviews", dependencies=[Depends(require_admin)])
def admin_reviews():
    """Get pending review items."""
    db = SessionLocal()
    try:
        reviews = (
            db.query(ReviewItem)
            .filter(ReviewItem.resolved_at == None)
            .order_by(ReviewItem.created_at.desc())
            .limit(50)
            .all()
        )
        return [
            {
                "id": r.id,
                "type": r.type,
                "severity": r.severity,
                "context": r.context,
                "created_at": r.created_at.isoformat(),
            }
            for r in reviews
        ]
    finally:
        db.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
