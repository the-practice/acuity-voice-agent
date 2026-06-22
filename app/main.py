from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime, date
from typing import Any
import logging

from app.config import settings
from app.db.session import SessionLocal
from app.db.models import CallLog, ReviewItem, Client
from app.integrations.acuity import acuity
from app.integrations.intakeq import intakeq
from app.integrations.vapi import VapiFunctionCall, FUNCTION_DESCRIPTIONS, SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="The Practice Voice Agent")


@app.get("/")
def health():
    return {"status": "healthy", "service": "thepractice-voice-agent"}


# Store call state in-memory (Redis in production)
_call_state = {}


@app.post("/webhooks/vapi")
async def vapi_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle Vapi webhooks - function calls and events."""
    payload = await request.json()

    event_type = payload.get("type")
    call_id = payload.get("call", {}).get("id")

    if event_type == "assistant-request":
        # Initial request - return config
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
        # Execute function call
        func_call = VapiFunctionCall(**payload.get("functionCall", {}))
        return await handle_function_call(func_call, call_id, background_tasks)

    elif event_type == "conversation-update":
        # Log call completion
        background_tasks.add_task(log_call_completed, payload)
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

    # Parse date
    try:
        appt_date = date.fromisoformat(date_str.replace("-", ""))
    except ValueError:
        return {"error": "Invalid date format. Use YYYY-MM-DD."}

    # Get calendars and appointment types
    calendars = acuity.get_calendars()
    appt_types = acuity.get_appointment_types()

    # Find matching calendar
    calendar = next((c for c in calendars if provider_name.lower() in c.get("name", "").lower()), None)
    if not calendar:
        return {"error": f"Provider '{provider_name}' not found."}

    # Find matching appointment type
    appt_type_obj = next(
        (t for t in appt_types if appt_type.lower() in t.get("name", "").lower()), None
    )
    if not appt_type_obj:
        return {"error": f"Appointment type '{appt_type}' not found."}

    # Check availability
    slots = acuity.check_availability(
        appointment_type_id=appt_type_obj["id"],
        calendar_id=calendar["id"],
        date=appt_date,
    )

    if not slots:
        return {
            "available": False,
            "message": f"No available slots for {provider_name} on {date_str}. Would you like to check another date?"
        }

    # Return first few available slots
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

    # Validate required fields
    if not all([email, name, provider_name, appt_type, date_str, time_str]):
        return {"error": "Missing required fields."}

    # Get calendar and appointment type IDs
    calendars = acuity.get_calendars()
    appt_types = acuity.get_appointment_types()

    calendar = next((c for c in calendars if provider_name.lower() in c.get("name", "").lower()), None)
    appt_type_obj = next(
        (t for t in appt_types if appt_type.lower() in t.get("name", "").lower()), None
    )

    if not calendar:
        return {"error": f"Provider '{provider_name}' not found."}
    if not appt_type_obj:
        return {"error": f"Appointment type '{appt_type}' not found."}

    # Build appointment data
    appt_data = {
        "firstName": name.split()[0] if name else "",
        "lastName": " ".join(name.split()[1:]) if len((name or "").split()) > 1 else "",
        "email": email,
        "phone": phone,
        "appointmentTypeID": appt_type_obj["id"],
        "calendarID": calendar["id"],
        "date": date_str,
        "time": time_str,
    }

    # Book in Acuity
    result = acuity.book_appointment(appt_data)

    # Store call state for summary
    _call_state[call_id] = _call_state.get(call_id, {})
    _call_state[call_id]["outcome"] = "booked"
    _call_state[call_id]["appointment_id"] = result.get("id")

    # Log to database in background
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


async def lookup_client(args: dict) -> dict:
    """Lookup a returning client in IntakeQ and Acuity."""
    email = args.get("email")
    phone = args.get("phone")
    name = args.get("name")

    if not email and not phone:
        return {"error": "Email or phone required for lookup."}

    db = SessionLocal()

    # Check local DB first
    if email:
        local_client = db.query(Client).filter(Client.email == email).first()
    elif phone:
        local_client = db.query(Client).filter(Client.phone == phone).first()
    else:
        local_client = None

    if local_client:
        return {
            "found": True,
            "client_id": local_client.id,
            "name": local_client.name,
            "is_returning": True,
        }

    # Check Acuity
    acuity_clients = acuity.get_clients(email=email, phone=phone)
    if acuity_clients:
        client = acuity_clients[0]
        # Store in local DB
        new_client = Client(
            email=client.get("email"),
            phone=client.get("phone"),
            name=f"{client.get('firstName', '')} {client.get('lastName', '')}".strip(),
            acuity_id=client.get("id"),
        )
        db.add(new_client)
        db.commit()
        return {
            "found": True,
            "client_id": new_client.id,
            "name": new_client.name,
            "is_returning": True,
        }

    return {
        "found": False,
        "message": "Client not found in our system. This appears to be a new patient."
    }


async def answer_question(args: dict) -> dict:
    """Answer common questions from knowledge base."""
    question = args.get("question", "").lower()

    db = SessionLocal()

    # Simple keyword matching for MVP
    # In production, use vector search or more sophisticated KB
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

    _call_state[call_id] = _call_state.get(call_id, {})
    _call_state[call_id]["outcome"] = "transferred"
    _call_state[call_id]["transfer_reason"] = reason

    # If crisis/emergency, include special handling
    is_crisis = any(word in reason.lower() for word in ["crisis", "emergency", "suicide", "harm"])

    return {
        "transfer": True,
        "phone_number": settings.human_transfer_number or "+15555555555",  # Fallback
        "message": "Connecting you with a staff member now.",
        "is_crisis": is_crisis,
        "crisis_message": "If you're in immediate danger, please call 911 or 988 for the suicide and crisis lifeline." if is_crisis else None
    }


async def take_message(args: dict, call_id: str) -> dict:
    """Take a message and queue for follow-up."""
    caller_name = args.get("caller_name", "Unknown")
    caller_phone = args.get("caller_phone", "")
    message = args.get("message", "")
    urgency = args.get("urgency", "medium")

    db = SessionLocal()

    review_item = ReviewItem(
        type="message",
        severity=urgency,
        context={
            "caller_name": caller_name,
            "caller_phone": caller_phone,
            "message": message,
            "call_id": call_id,
        },
    )
    db.add(review_item)

    _call_state[call_id] = _call_state.get(call_id, {})
    _call_state[call_id]["outcome"] = "message"

    db.commit()

    return {
        "success": True,
        "message": f"Thank you. I've taken your message and someone will get back to you within {24 if urgency == 'low' else 4 if urgency == 'medium' else 1} hours."
    }


# Background task functions

def log_booking(call_id: str, appointment_id: int, client_email: str, provider_name: str):
    """Log successful booking to database."""
    db = SessionLocal()
    try:
        call_log = db.query(CallLog).filter(CallLog.vapi_call_id == call_id).first()
        if call_log:
            call_log.outcome = "booked"
            call_log.summary = f"Booked appointment {appointment_id} for {client_email} with {provider_name}"
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log booking: {e}")


def log_call_completed(payload: dict):
    """Log call completion to database."""
    db = SessionLocal()
    try:
        call = payload.get("call", {})
        call_id = call.get("id")
        status = payload.get("status", "")

        # Check if we already logged this call
        existing = db.query(CallLog).filter(CallLog.vapi_call_id == call_id).first()
        if existing:
            existing.ended_at = datetime.utcnow()
            if status == "completed":
                existing.outcome = existing.outcome or "completed"
            db.commit()
            return

        # Create new call log
        call_log = CallLog(
            vapi_call_id=call_id,
            caller_phone=call.get("phoneNumber", {}).get("number"),
            started_at=datetime.fromisoformat(call.get("startedAt", "").replace("Z", "+00:00")) if call.get("startedAt") else None,
            ended_at=datetime.fromisoformat(call.get("endedAt", "").replace("Z", "+00:00")) if call.get("endedAt") else None,
            outcome=_call_state.get(call_id, {}).get("outcome", "unknown"),
        )
        db.add(call_log)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to log call: {e}")
    finally:
        db.close()


# Admin routes (basic for MVP)

@app.get("/admin/stats")
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


@app.get("/admin/reviews")
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
