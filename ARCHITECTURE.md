# The Practice - Voice Agent Architecture

## System Overview

HIPAA-compliant AI voice agent for mental health practice front-desk operations.

**Core flows:**
- Incoming call → Greeting & routing → Intent detection
- New patient: Information gathering → Provider matching → Acuity scheduling
- Returning client: Identity verification → Lookup → Scheduling/changes
- General questions: Knowledge base query → Answer or human transfer
- Crisis/Emergency: Immediate escalation per protocol

## Recommended Voice Platform: **Vapi.ai**

**Rationale:**
- HIPAA BAA available
- Native function calling for API integrations
- Low latency (~800ms first token)
- Good phone call quality
- Built-in transcription (optional)
- Reasonable pricing
- Python SDK

**Alternative:** Twilio Media Streams (more control, more work)

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Phone Call (Twilio)                         │
└──────────────────────────────┬────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Vapi.ai (Voice Layer)                       │
│  - Speech-to-text                                                   │
│  - LLM orchestration                                                │
│  - Function calling to backend                                      │
│  - Text-to-speech                                                   │
└──────────────────────────────┬────────────────────────────────────┘
                               │ HTTP webhook
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python)                         │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  /webhooks/vapi        # Vapi function calls & events      │    │
│  │  /webhooks/twilio      # Call status updates                │    │
│  │  /admin/*              # Admin dashboard API                │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐              │
│  │  Router     │  │  Services   │  │  Integrations│              │
│  │             │  │             │  │              │              │
│  │ - intent    │  │ - scheduler │  │ - Acuity     │              │
│  │ - authz     │  │ - client    │  │ - IntakeQ    │              │
│  │ - escalate  │  │ - provider  │  │ - Eligibility│              │
│  └─────────────┘  └─────────────┘  └──────────────┘              │
│                                                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐              │
│  │  Database   │  │  Queue      │  │  Cache       │              │
│  │             │  │             │  │              │              │
│  │ - clients   │  │ - tasks     │  │ - avail      │              │
│  │ - calls     │  │ - reviews   │  │ - kb         │              │
│  │ - logs      │  │ - sync      │  │              │              │
│  └─────────────┘  └─────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
                               │
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
         ┌──────────┐   ┌──────────┐   ┌──────────┐
         │ Acuity   │   │ IntakeQ  │   │ Office   │
         │ Schedul. │   │          │   │ Ally     │
         └──────────┘   └──────────┘   └──────────┘
```

## Data Flow

### New Patient Scheduling
```
Call → Vapi → Collect: name, contact, concern, insurance, preferences
     → Provider matching service → Acuity availability check
     → Present options → Book in Acuity → Trigger confirmation
     → Queue for IntakeQ sync → Return summary
```

### Returning Client Lookup
```
Call → Vapi → Request identifier (name/DOB/phone)
     → Lookup in IntakeQ & Acuity → Verify identity
     → Confirm client status → Scheduling operations
     → Update in Acuity → Queue billing sync
```

### Human Transfer
```
Call → Vapi → Trigger condition met → Warm transfer endpoint
     → Twilio transfer → Human receives context summary
     → If no answer: Take message → Queue task → SMS staff
```

## IntakeQ → Acuity Migration Plan

**Phase 1: Discovery & Dry Run**
```python
# Map fields between systems
FIELD_MAPPINGS = {
    "intakeq.client": "acuity.client",
    "intakeq.appointment": "acuity.appointment",
    "intakeq.provider": "acuity.calendar",
    # ... detailed mappings in migration.py
}

# Deduplication: match by email + phone
# Conflict resolution: IntakeQ source of truth for migration
# Dry-run mode: validate without writing
```

**Phase 2: Bulk Import**
- Export from IntakeQ
- Transform & validate
- Import to Acuity with external IDs preserved
- Generate import report

**Phase 3: Ongoing Sync**
- Poll IntakeQ for new appointments
- Sync to Acuity until cutoff date
- Eventually: Acuity becomes source of truth

## Acuity → Billing Sync

**Direction:** Acuity → IntakeQ (daily)

**Rationale:** IntakeQ remains billing workflow entry point

**Process:**
```python
# Nightly job
1. Fetch completed appointments from Acuity (yesterday)
2. Exclude: canceled, no-show, pending
3. Match clients by external ID or lookup
4. Create/update in IntakeQ for billing
5. Log sync results
6. Flag unmatched for review
```

## Provider Matching Logic

```python
def match_provider(client_info, available_providers):
    """
    Returns ranked providers based on:
    - Specialty match to presenting concern
    - Insurance acceptance
    - New vs returning status
    - Telehealth/in-person preference
    - Location proximity (if in-person)
    - Availability
    """
    scored = []
    for provider in available_providers:
        score = 0
        if client_info.insurance in provider.accepted_insurance:
            score += 50
        if client_info.is_new and provider.accepts_new_patients:
            score += 30
        if matches_specialty(client_info.concern, provider.specialties):
            score += 40
        if client_info.prefers_telehealth and provider.offers_telehealth:
            score += 20
        # ... more rules
        scored.append((score, provider))
    return sorted(scored, reverse=True)
```

## Identity Verification

**Before discussing PHI:**
1. Request: name + date of birth OR name + phone
2. Lookup in systems
3. Ask verification question (last appointment date, provider name)
4. Only proceed if match + verification passes

**Failure:** Transfer to human or take message

## HIPAA & Compliance

- **Minimum PHI:** Only request/necessary fields
- **Audit logging:** Every API call, lookup, booking
- **Encryption:** TLS in transit, encrypted at rest
- **Retention:** Configurable transcript retention (default: 0 days)
- **BAA:** Vapi BAA on file
- **Access control:** Role-based admin dashboard

## Admin Dashboard

**Pages:**
- Dashboard: Call stats, pending reviews, sync status
- Providers: Rules, availability, mappings
- Clients: Search, verification status
- Calls: Transcripts (retention-limited), summaries
- Reviews: Failed bookings, mismatched records
- Settings: Hours, locations, knowledge base

## Database Schema (PostgreSQL)

```sql
-- Clients (unified view across systems)
CREATE TABLE clients (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    phone VARCHAR(50),
    name VARCHAR(255),
    date_of_birth DATE,
    intakeq_id VARCHAR(100),
    acuity_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Call logs (audit trail)
CREATE TABLE call_logs (
    id SERIAL PRIMARY KEY,
    call_sid VARCHAR(100) UNIQUE,
    caller_phone VARCHAR(50),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    outcome VARCHAR(50), -- booked, transferred, message, etc.
    summary TEXT,
    contains_phi BOOLEAN DEFAULT FALSE,
    transcript_retention_days INT DEFAULT 0
);

-- Sync jobs (IntakeQ↔Acuity)
CREATE TABLE sync_jobs (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20), -- intakeq_to_acuity, acuity_to_intakeq
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    status VARCHAR(20),
    records_processed INT,
    records_failed INT,
    error_summary TEXT
);

-- Human review queue
CREATE TABLE review_items (
    id SERIAL PRIMARY KEY,
    type VARCHAR(50), -- mismatched_client, failed_booking, etc.
    severity VARCHAR(20), -- low, medium, high, critical
    context JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP,
    resolution TEXT
);

-- Provider rules
CREATE TABLE provider_rules (
    id SERIAL PRIMARY KEY,
    provider_name VARCHAR(255),
    acuity_calendar_id VARCHAR(100),
    accepts_new_patients BOOLEAN,
    accepted_insurance JSONB,
    specialties JSONB,
    offers_telehealth BOOLEAN,
    location VARCHAR(255)
);
```

## MVP Scope

**Phase 1 (MVP):**
1. ✅ Vapi integration with FastAPI backend
2. ✅ Acuity API integration (availability, booking)
3. ✅ Basic question answering from knowledge base
4. ✅ New patient scheduling flow
5. ✅ Human transfer capability
6. ✅ Call summaries
7. ✅ Simple admin dashboard
8. ✅ Audit logging
9. ✅ IntakeQ → Acuity migration (dry run + execute)

**Phase 2:**
10. Returning client lookup + identity verification
11. Rescheduling & cancellation
12. Insurance eligibility integration
13. Acuity → IntakeQ billing sync
14. Advanced provider matching

**Phase 3:**
15. Office Ally direct claims integration
16. SMS/email notifications
17. Advanced analytics

## Open Questions (User to Answer)

1. **Acuity credentials:** API key, User ID, Business ID
2. **IntakeQ credentials:** API key
3. **Office Ally:** API access? Or is IntakeQ sufficient for billing?
4. **Insurance eligibility:** Which service? (Office Ally, Change Healthcare, etc.)
5. **Provider list:** Names, specialties, insurance accepted, telehealth capability
6. **Appointment types:** Full list with durations
7. **Business hours:** By day, by location
8. **Crisis protocol:** Exact script and escalation path
9. **BAA status:** Is Vapi BAA already executed?
10. **Phone system:** Twilio? Existing number to port?

## Implementation Order

1. Set up project structure + dependencies
2. Implement Acuity integration (test API)
3. Implement Vapi webhook handler
4. Build new patient scheduling flow
5. Add human transfer
6. Create admin dashboard
7. Implement IntakeQ integration
8. Build migration tool
9. Add identity verification
10. Add eligibility integration
11. Build billing sync
