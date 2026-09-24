from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database import Base

def now_utc(): return datetime.now(timezone.utc)

class Model(Base):
    __tablename__ = "models"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    provider: Mapped[str] = mapped_column(String, default="demo")
    display_name: Mapped[str] = mapped_column(String)
    model_id: Mapped[str] = mapped_column(String)
    data_source: Mapped[str] = mapped_column(String, default="demo")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[str] = mapped_column(String, default="configured")

class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String, index=True)
    domain: Mapped[str] = mapped_column(String, index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    products: Mapped[list] = mapped_column(JSON, default=list)

class BrandAlias(Base):
    __tablename__ = "brand_aliases"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    alias: Mapped[str] = mapped_column(String, unique=True, index=True)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    canonical_name: Mapped[str] = mapped_column(String)
    product_family: Mapped[str] = mapped_column(String, default="")
    __table_args__ = (UniqueConstraint("brand_id", "canonical_name", name="uq_product_brand_name"),)

class PromptGroup(Base):
    __tablename__ = "prompt_groups"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    domain: Mapped[str] = mapped_column(String)

class Prompt(Base):
    __tablename__ = "prompts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String, index=True)
    group_id: Mapped[str | None] = mapped_column(ForeignKey("prompt_groups.id"), nullable=True)
    variant: Mapped[str] = mapped_column(String, default="baseline")
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)

class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    domain: Mapped[str] = mapped_column(String, index=True)
    mode: Mapped[str] = mapped_column(String, default="demo")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

class LLMResponse(Base):
    __tablename__ = "llm_responses"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[str] = mapped_column(ForeignKey("experiments.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("experiment_runs.id"), index=True)
    prompt_id: Mapped[str] = mapped_column(ForeignKey("prompts.id"), index=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), index=True)
    repetition: Mapped[int] = mapped_column(Integer, default=1)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, index=True)
    response_text: Mapped[str] = mapped_column(Text, default="")
    token_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    execution_status: Mapped[str] = mapped_column(String, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_source: Mapped[str] = mapped_column(String, default="demo", index=True)
    model_configuration: Mapped[dict] = mapped_column(JSON, default=dict)
    search_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[str] = mapped_column(String, default="dictionary-v1")
    observations: Mapped[list["BrandObservation"]] = relationship(back_populates="response", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_response_source_domain_date", "data_source", "timestamp"),)

class ExtractionRun(Base):
    __tablename__ = "extraction_runs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("llm_responses.id"), index=True)
    method: Mapped[str] = mapped_column(String)
    pipeline_version: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="complete")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class BrandObservation(Base):
    __tablename__ = "brand_observations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("llm_responses.id"), index=True)
    brand_id: Mapped[str] = mapped_column(ForeignKey("brands.id"), index=True)
    extraction_run_id: Mapped[str] = mapped_column(ForeignKey("extraction_runs.id"), index=True)
    mention_order: Mapped[int] = mapped_column(Integer)
    explicit_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product: Mapped[str | None] = mapped_column(String, nullable=True)
    sentiment: Mapped[str] = mapped_column(String, default="unknown")
    attributes: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[str] = mapped_column(Text, default="")
    entity_type: Mapped[str] = mapped_column(String, default="brand")
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    response: Mapped[LLMResponse] = relationship(back_populates="observations")

class Annotation(Base):
    __tablename__ = "annotations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    observation_id: Mapped[str] = mapped_column(ForeignKey("brand_observations.id"), index=True)
    corrected_sentiment: Mapped[str | None] = mapped_column(String, nullable=True)
    corrected_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ModelUpdateEvent(Base):
    __tablename__ = "model_update_events"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    model_id: Mapped[str] = mapped_column(ForeignKey("models.id"), index=True)
    event_type: Mapped[str] = mapped_column(String)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class ExecutionLog(Base):
    __tablename__ = "execution_logs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    experiment_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    level: Mapped[str] = mapped_column(String, default="INFO")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

class SourceCitation(Base):
    __tablename__ = "source_citations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    response_id: Mapped[str] = mapped_column(ForeignKey("llm_responses.id"), index=True)
    url: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    citation_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
