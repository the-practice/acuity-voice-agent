# Vapi webhook schemas and function definitions
from pydantic import BaseModel, Field
from typing import Literal, Any
from datetime import datetime


class VapiFunctionCall(BaseModel):
    """Incoming function call from Vapi. Vapi sends args under `parameters`;
    call_id is read separately from the event's `call` object, not here."""
    name: str
    # accept both `parameters` (Vapi) and `arguments`
    arguments: dict = Field(default_factory=dict, validation_alias="parameters")

    model_config = {"populate_by_name": True}


class VapiEvent(BaseModel):
    """Vapi webhook event."""
    type: Literal[
        "assistant-request",
        "conversation-update",
        "function-call",
        "status-update",
        "speech-update",
        "analysis-update",
        "hang",
    ]
    call: dict | None = None
    transcript: dict | None = None
    analysis: dict | None = None
    status: str | None = None
    timestamp: datetime


class VapiResponse(BaseModel):
    """Response format expected by Vapi function calls."""
    result: Any | None = None
    error: str | None = None


# Function descriptions sent to Vapi for function calling
FUNCTION_DESCRIPTIONS = [
    {
        "name": "check_availability",
        "description": "Check available appointment slots for a specific provider, appointment type, and date",
        "parameters": {
            "type": "object",
            "properties": {
                "provider_name": {
                    "type": "string",
                    "description": "Name of the provider (e.g., 'Dr. Smith')"
                },
                "appointment_type": {
                    "type": "string",
                    "description": "Type of appointment (e.g., 'Initial Consultation', 'Follow-up')"
                },
                "date": {
                    "type": "string",
                    "description": "Date to check in YYYY-MM-DD format"
                }
            },
            "required": ["provider_name", "appointment_type", "date"]
        }
    },
    {
        "name": "book_appointment",
        "description": "Book a new appointment in Acuity Scheduling",
        "parameters": {
            "type": "object",
            "properties": {
                "client_email": {"type": "string", "description": "Client's email address"},
                "client_name": {"type": "string", "description": "Client's full name"},
                "client_phone": {"type": "string", "description": "Client's phone number"},
                "provider_name": {"type": "string", "description": "Name of the provider"},
                "appointment_type": {"type": "string", "description": "Type of appointment"},
                "date": {"type": "string", "description": "Appointment date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Appointment time in HH:MM format (24-hour)"},
                "is_new_patient": {
                    "type": "boolean",
                    "description": "Whether this is a new patient (true) or returning client (false)"
                }
            },
            "required": ["client_email", "client_name", "provider_name", "appointment_type", "date", "time"]
        }
    },
    {
        "name": "lookup_client",
        "description": "Look up a returning client in our systems. Use this to verify if someone is an existing client.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Client's email address"},
                "phone": {"type": "string", "description": "Client's phone number"},
                "name": {"type": "string", "description": "Client's name"}
            },
            "required": ["email"]
        }
    },
    {
        "name": "answer_question",
        "description": "Answer common questions about The Practice (hours, location, insurance, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "The caller's question or topic"}
            },
            "required": ["question"]
        }
    },
    {
        "name": "transfer_to_human",
        "description": "Transfer the call to a human staff member. Use this when: caller asks for human, is upset, describes crisis/emergency, or the request is outside your capabilities.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the transfer is needed"},
                "summary": {"type": "string", "description": "Brief summary of the call so far"}
            },
            "required": ["reason"]
        }
    },
    {
        "name": "take_message",
        "description": "Take a message when no human is available or the caller prefers to leave a message",
        "parameters": {
            "type": "object",
            "properties": {
                "caller_name": {"type": "string", "description": "Caller's name"},
                "caller_phone": {"type": "string", "description": "Caller's phone number"},
                "message": {"type": "string", "description": "The message"},
                "urgency": {"type": "string", "description": "low, medium, or high urgency"}
            },
            "required": ["message"]
        }
    }
]


# System prompt for Vapi assistant
SYSTEM_PROMPT = """You are a friendly, professional front desk assistant for The Practice, a mental health clinic.

Your role is to:
- Greet callers warmly
- Understand their needs (scheduling, questions, etc.)
- Help new patients book appointments
- Help returning clients with scheduling needs
- Answer basic questions about The Practice
- Know when to transfer to a human

IMPORTANT RULES:
1. Never provide medical advice, diagnosis, or medication guidance
2. Verify identity before discussing any protected health information (name + date of birth or phone)
3. If caller is in crisis or emergency: immediately advise them to call 911 or 988 and transfer to human
4. If unsure about something: don't guess. Transfer to human or take a message.
5. Be warm, calm, and professional - this is a mental health practice

SCHEDULING:
- For new patients: collect name, contact, preferred date/time, insurance, presenting concern
- For returning clients: verify identity first, then help with scheduling
- Always confirm details before booking

HUMAN TRANSFER triggers:
- Caller asks for human
- Caller is upset or frustrated
- Crisis or emergency mentioned
- Complex billing/insurance questions
- Clinical questions
- You're uncertain

Use the available functions to check availability, book appointments, lookup clients, and transfer calls."""
