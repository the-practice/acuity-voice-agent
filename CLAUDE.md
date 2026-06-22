# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

HIPAA-compliant AI voice agent for The Practice (mental health clinic). Handles incoming calls, schedules appointments via Acuity, syncs with IntakeQ for billing.

**Live site:** https://thepractice.co

## Architecture

**Stack:** Python + FastAPI + Vapi.ai (voice) + PostgreSQL + Redis

**Key integrations:**
- Vapi.ai: Voice telephony, speech-to-text, LLM orchestration
- Acuity Scheduling: Primary scheduling system (availability, bookings)
- IntakeQ: Patient records, billing workflow, legacy scheduling data
- Office Ally: Insurance eligibility (future)

**Data flow:** Phone → Twilio → Vapi → FastAPI → {Acuity, IntakeQ} → PostgreSQL

**Migration direction:** IntakeQ → Acuity (one-time + sync until cutover)
**Billing sync:** Acuity → IntakeQ (nightly)

## Key Concepts

**Provider matching:** Score-based matching considering specialty, insurance, new/returning status, telehealth preference, location. Logic in `services/provider_match.py`.

**Identity verification:** Required before discussing PHI. Name + DOB/phone → lookup → verification question → proceed.

**Crisis escalation:** Immediate human transfer + 911/988 guidance. Keywords trigger override.

**Audit logging:** Every booking, lookup, sync, transfer logged to `call_logs` table.

**PHI minimization:** Only request/necessary fields. Transcripts retention: 0 days by default (configurable). Summaries only.

## File Structure

```
app/
├── main.py                 # FastAPI app, webhook endpoints
├── config.py              # Environment-based config
├── db/
│   ├── models.py          # SQLAlchemy models
│   ├── session.py         # DB session management
│   └── migrations/        # Alembic migrations
├── integrations/
│   ├── acuity.py          # Acuity API client
│   ├── intakeq.py         # IntakeQ API client
│   └── vapi.py            # Vapi webhook schemas & tools
├── services/
│   ├── scheduler.py       # Scheduling logic
│   ├── provider_match.py  # Provider matching
│   ├── identity.py        # Verification logic
│   └── sync.py            # Acuity→IntakeQ billing sync
├── admin/
│   ├── router.py          # Admin dashboard API
│   └── frontend/          # Simple HTML dashboard
├── prompts/
│   ├── system.py          # Vapi system prompts
│   └── functions.py       # Function descriptions for Vapi
└── scripts/
    ├── migrate_intakeq.py # IntakeQ→Acuity migration
    └── billing_sync.py    # Nightly billing sync
```

## Development

```bash
# Install deps
pip install -r requirements.txt

# Setup database
createdb thepractice_voice
alembic upgrade head

# Run dev server (use ngrok for webhooks)
uvicorn app.main:app --reload

# Run billing sync (nightly via cron)
python -m app.scripts.billing_sync

# Dry-run migration test
python -m app.scripts.migrate_intakeq --dry-run
```

## Environment

Required in `.env`:
```
DATABASE_URL=postgresql://user:pass@localhost/thepractice_voice
REDIS_URL=redis://localhost:6379/0
ACUITY_API_KEY=
ACUITY_USER_ID=
ACUITY_BUSINESS_ID=
INTAKEQ_API_KEY=
VAPI_AUTH_TOKEN=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
```

## Vapi Functions

The backend exposes functions to Vapi via `/webhooks/vapi`. Key functions:
- `check_availability`: Get open slots for provider + date
- `book_appointment`: Create appointment in Acuity
- `lookup_client`: Search IntakeQ/Acuity for returning patient
- `transfer_to_human`: Trigger Twilio warm transfer
- `create_review_task`: Queue item for human review

Vapi calls these during conversation; backend validates and executes.

## Important Constraints

- **No medical advice:** Agent answers scheduling questions only. Clinical queries → human transfer.
- **Verify identity:** Never discuss PHI without verification.
- **Don't guess:** Uncertain → take message or transfer.
- **Sync safety:** Billing sync excludes canceled/no-show. Only confirmed appointments.
- **Migration safety:** Dry-run first. Confirm counts. External IDs preserved for reconciliation.

## Testing

Acuity/IntakeQ integrations use `pytest` with VCR.py cassettes. Run:
```bash
pytest --vcr-record=none  # Use cassettes (no live calls)
pytest --vcr-record=all   # Re-record (live calls, use carefully)
```
