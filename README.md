# The Practice Voice Agent

HIPAA-compliant AI voice agent for mental health practice front-desk operations.

## What It Does

- Answers incoming calls and routes intents
- Schedules new patient appointments via Acuity Scheduling
- Looks up returning clients (with identity verification)
- Answers common questions (hours, location, insurance, etc.)
- Transfers to human when needed (crisis, complex requests, clinical questions)
- Logs all calls for audit and review

## Architecture

```
Phone → Twilio → Vapi.ai → FastAPI → {Acuity, IntakeQ} → PostgreSQL
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
# Edit .env with your API credentials

# Setup database
createdb thepractice_voice
alembic upgrade head

# Run dev server
uvicorn app.main:app --reload

# For webhooks (Vapi/Twilio need public URL)
ngrok http 8000
```

## Required Credentials

Before running, you'll need:

1. **Acuity Scheduling**: API key, User ID ([docs](https://acuityscheduling.com/api/v1))
2. **IntakeQ**: API key ([docs](https://intakeq.com/api-docs))
3. **Vapi.ai**: Auth token ([docs](https://vapi.ai))
4. **Twilio**: Account SID, Auth token, phone number
5. **PostgreSQL**: Local or hosted database
6. **Redis**: For call state caching (optional for MVP)

## Development

```bash
# Run tests
pytest

# Run with VCR (no live API calls)
pytest --vcr-record=none

# Re-record cassettes (live calls, use carefully)
pytest --vcr-record=all

# Database migration
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Admin Dashboard

Basic admin endpoints:

- `GET /admin/stats` - Call statistics
- `GET /admin/reviews` - Pending review items (mismatches, failed bookings, etc.)

Full dashboard UI: TODO (Phase 2)

## HIPAA & Compliance

- BAA required with Vapi.ai
- TLS for all API communications
- Encrypted database storage
- Audit logging for all actions
- Configurable transcript retention (default: 0 days)
- PHI minimization (only necessary fields)

## MVP Scope

**Included in MVP:**
- ✅ Vapi integration
- ✅ Acuity scheduling (availability check, booking)
- ✅ Basic question answering
- ✅ New patient flow
- ✅ Human transfer
- ✅ Call logging
- ✅ Admin endpoints

**Phase 2 (Post-MVP):**
- Returning client identity verification
- Rescheduling & cancellation
- IntakeQ integration
- IntakeQ → Acuity migration tool
- Acuity → IntakeQ billing sync
- Insurance eligibility
- Admin dashboard UI

## Open Questions

See [ARCHITECTURE.md](ARCHITECTURE.md) section "Open Questions (User to Answer)".

## License

Internal use - The Practice
# Railway auto-redeploy trigger
