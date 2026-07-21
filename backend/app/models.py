"""SQLAlchemy 2.0 모델 — docs/schema.sql 과 1:1 미러링.

스키마의 원본은 SQL 파일이다. 이 파일을 바꾸면 반드시 migrations/NNN_*.sql 도 추가하고
docs/schema.sql 을 동기화할 것. Alembic autogenerate 사용 금지.
(CLAUDE.md 규칙 9, ARCHITECTURE.md §3-1, BACKEND.md §2)
"""

from datetime import date, datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ---------- 매장 ----------
class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    owner_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StoreSettings(Base):
    __tablename__ = "store_settings"

    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )
    tone_examples: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'"))
    default_tone: Mapped[str] = mapped_column(Text, server_default=text("'polite'"))
    notify_urgent: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    notify_digest: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class StoreChannel(Base):
    __tablename__ = "store_channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(Text, nullable=False)  # naver/google/csv
    external_url: Mapped[str | None] = mapped_column(Text)
    is_competitor: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    competitor_of: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stores.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


# ---------- 리뷰 ----------
class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("channel_id", "dedup_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("store_channels.id", ondelete="CASCADE"), nullable=False
    )
    dedup_key: Mapped[str] = mapped_column(Text, nullable=False)
    author_masked: Mapped[str | None] = mapped_column(Text)  # '김**'
    rating: Mapped[int | None] = mapped_column(SmallInteger)  # 1~5, 네이버 미제공 시 null
    body: Mapped[str] = mapped_column(Text, nullable=False)
    written_at: Mapped[date | None] = mapped_column(Date)
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ReviewAnalysis(Base):
    __tablename__ = "review_analysis"

    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True
    )
    sentiment: Mapped[str | None] = mapped_column(Text)  # pos/neu/neg
    severity: Mapped[str | None] = mapped_column(Text)  # normal/uncomfortable/complaint/malicious
    urgent: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    aspects: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'"))
    keywords: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    model_ver: Mapped[str | None] = mapped_column(Text)  # 'haiku-v1' | 'failed'
    alerted_at: Mapped[datetime | None] = mapped_column(  # 알림 발송 시각 (migration 003)
        DateTime(timezone=True)
    )
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ReviewEmbedding(Base):
    __tablename__ = "review_embeddings"

    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reviews.id", ondelete="CASCADE"), primary_key=True
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1024))  # BGE-M3


# ---------- 답글 ----------
class Reply(Base):
    __tablename__ = "replies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    review_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False
    )
    tone: Mapped[str | None] = mapped_column(Text)  # polite/friendly/apologetic
    draft: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, server_default=text("'draft'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ---------- 집계·리포트 ----------
class WeeklyAspectStats(Base):
    __tablename__ = "weekly_aspect_stats"

    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True
    )
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)  # 해당 주 월요일
    aspect: Mapped[str] = mapped_column(Text, primary_key=True)  # 맛/친절/.../전체
    pos_cnt: Mapped[int] = mapped_column(server_default=text("0"))
    neg_cnt: Mapped[int] = mapped_column(server_default=text("0"))
    total_cnt: Mapped[int] = mapped_column(server_default=text("0"))
    avg_rating: Mapped[float | None] = mapped_column(Numeric(3, 2))


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("store_id", "week_start"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    diagnosis: Mapped[list] = mapped_column(JSONB, nullable=False)
    prescriptions: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


# ---------- 알림·대화 ----------
class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stores.id", ondelete="CASCADE")
    )
    review_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reviews.id", ondelete="SET NULL")
    )
    kind: Mapped[str | None] = mapped_column(Text)  # urgent_review/digest/weekly_report/system
    sent_via: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    store_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("stores.id", ondelete="CASCADE")
    )
    role: Mapped[str | None] = mapped_column(Text)  # user/assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


# ---------- ARCHITECTURE.md §3-7: 스펙 DDL에 없던 추가 테이블 ----------
class CrawlJob(Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("store_channels.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, server_default=text("'pending'"))
    requested_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    error: Mapped[str | None] = mapped_column(Text)
    collected: Mapped[int | None] = mapped_column()  # 수집 건수 (migration 002)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KakaoToken(Base):
    __tablename__ = "kakao_tokens"

    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()")
    )
