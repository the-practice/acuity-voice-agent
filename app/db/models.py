from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    phone = Column(String(50), index=True)
    name = Column(String(255))
    date_of_birth = Column(DateTime)
    intakeq_id = Column(String(100))
    acuity_id = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)


class CallLog(Base):
    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True)
    call_sid = Column(String(100), unique=True)
    caller_phone = Column(String(50))
    started_at = Column(DateTime)
    ended_at = Column(DateTime)
    outcome = Column(String(50))  # booked, transferred, message, failed
    summary = Column(Text)
    contains_phi = Column(Boolean, default=False)
    transcript_retention_days = Column(Integer, default=0)
    vapi_call_id = Column(String(100), unique=True, index=True)  # de-facto key for lookups/upserts


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id = Column(Integer, primary_key=True)
    type = Column(String(20))  # intakeq_to_acuity, acuity_to_intakeq
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    status = Column(String(20))  # running, completed, failed
    records_processed = Column(Integer)
    records_failed = Column(Integer)
    error_summary = Column(Text)
    log_url = Column(String(500))  # S3 or similar for large logs


class ReviewItem(Base):
    __tablename__ = "review_items"

    id = Column(Integer, primary_key=True)
    type = Column(String(50))  # mismatched_client, failed_booking, etc.
    severity = Column(String(20))  # low, medium, high, critical
    context = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime)
    resolution = Column(Text)


class ProviderRule(Base):
    __tablename__ = "provider_rules"

    id = Column(Integer, primary_key=True)
    provider_name = Column(String(255))
    acuity_calendar_id = Column(String(100))
    accepts_new_patients = Column(Boolean)
    accepted_insurance = Column(JSON)  # ["Aetna", "Blue Cross", ...]
    specialties = Column(JSON)  # ["depression", "anxiety", ...]
    offers_telehealth = Column(Boolean)
    location = Column(String(255))
    is_active = Column(Boolean, default=True)


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id = Column(Integer, primary_key=True)
    slug = Column(String(100), unique=True, index=True)
    title = Column(String(255))
    content = Column(Text)
    category = Column(String(50))  # hours, location, insurance, etc.
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
