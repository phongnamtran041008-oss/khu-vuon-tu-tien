"""Database schema (spec section 4). Every table of the full game is defined here so the
first migration already has the final shape; later stages only add behaviour."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

UserFK = lambda: ForeignKey("users.id", ondelete="CASCADE")  # noqa: E731


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
    recovery_code_hash: Mapped[str] = mapped_column(String(100))
    spirit_stones: Mapped[int] = mapped_column(Integer, default=300)   # Linh Thạch
    immortal_jade: Mapped[int] = mapped_column(Integer, default=0)     # Tiên Ngọc
    pity: Mapped[dict] = mapped_column(JSON, default=dict)             # {banner: {min_rarity: count}}
    daily_new_seeds_count: Mapped[int] = mapped_column(Integer, default=0)
    daily_free_rolls_used: Mapped[int] = mapped_column(Integer, default=0)
    daily_reset_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    current_letter_id: Mapped[str | None] = mapped_column(String(20), nullable=True)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    register_ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    banned_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    chat_banned_until: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    suspicious_flag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    flags: Mapped[dict] = mapped_column(JSON, default=dict)  # tutorial step, decorations, ...
    # LAN worlds: the Firebase account this local user belongs to (None = username/password account)
    firebase_uid: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)


class Word(Base):
    """Mirror of server/data/words/*.json (synced at startup) so other tables can FK it."""
    __tablename__ = "words"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    hanzi: Mapped[str] = mapped_column(String(16))
    tier: Mapped[int] = mapped_column(Integer)
    rarity: Mapped[str] = mapped_column(String(12))


class Plot(Base):
    __tablename__ = "plots"
    __table_args__ = (UniqueConstraint("user_id", "x", "y"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    x: Mapped[int] = mapped_column(Integer)
    y: Mapped[int] = mapped_column(Integer)
    unlocked: Mapped[bool] = mapped_column(Boolean, default=True)
    word_id: Mapped[str | None] = mapped_column(ForeignKey("words.id"), nullable=True)
    stage: Mapped[int] = mapped_column(Integer, default=0)
    planted_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    next_review_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    wither: Mapped[float] = mapped_column(Float, default=0.0)
    wither_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    pollen: Mapped[float] = mapped_column(Float, default=0.0)
    pollinated: Mapped[bool] = mapped_column(Boolean, default=False)
    pollen_boost: Mapped[bool] = mapped_column(Boolean, default=False)   # shorter next wait not used yet
    fire_checked_date: Mapped[str | None] = mapped_column(String(10), nullable=True)


class Seed(Base):
    __tablename__ = "seeds"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    word_id: Mapped[str] = mapped_column(ForeignKey("words.id"))
    duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(20), default="gacha")
    obtained_at: Mapped[dt.datetime] = mapped_column(DateTime)


class Collection(Base):
    __tablename__ = "collection"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    word_id: Mapped[str] = mapped_column(ForeignKey("words.id"), primary_key=True)
    introduced: Mapped[bool] = mapped_column(Boolean, default=False)
    mastery: Mapped[int] = mapped_column(Integer, default=0)
    times_correct: Mapped[int] = mapped_column(Integer, default=0)
    times_wrong: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime)
    last_answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Fruit(Base):
    __tablename__ = "fruits"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    word_id: Mapped[str] = mapped_column(ForeignKey("words.id"), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class CraftedSentence(Base):
    __tablename__ = "crafted_sentences"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    sentence_id: Mapped[str] = mapped_column(String(20))
    crafted_at: Mapped[dt.datetime] = mapped_column(DateTime)


class QuizSession(Base):
    __tablename__ = "quiz_sessions"
    __table_args__ = (Index("ix_quiz_user_created", "user_id", "created_at"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK())
    context: Mapped[str] = mapped_column(String(16))  # garden|combat|td|fishing|realm|tribulation|forge|practice
    ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qtype: Mapped[str] = mapped_column(String(4))
    word_id: Mapped[str] = mapped_column(ForeignKey("words.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    answer_key: Mapped[dict] = mapped_column(JSON)  # never sent to the client before answering
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    answer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    answer_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Friendship(Base):
    __tablename__ = "friendships"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    friend_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending|accepted
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    help_count_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    help_count: Mapped[int] = mapped_column(Integer, default=0)


class Character(Base):
    __tablename__ = "characters"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(20), unique=True)
    realm: Mapped[str] = mapped_column(String(16), default="pham_nhan")
    realm_stage: Mapped[int] = mapped_column(Integer, default=0)
    cultivation_xp: Mapped[int] = mapped_column(Integer, default=0)
    hp: Mapped[int] = mapped_column(Integer, default=100)
    max_hp: Mapped[int] = mapped_column(Integer, default=100)
    qi: Mapped[int] = mapped_column(Integer, default=50)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    zone_id: Mapped[str] = mapped_column(String(32), default="abode")
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    appearance: Mapped[dict] = mapped_column(JSON, default=dict)
    hotbar: Mapped[dict] = mapped_column(JSON, default=dict)
    tribulation_retry_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    facing: Mapped[str] = mapped_column(String(5), default="down")


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    __table_args__ = (UniqueConstraint("user_id", "item_id", "bound"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    item_id: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    bound: Mapped[bool] = mapped_column(Boolean, default=False)


class EquipmentInstance(Base):
    __tablename__ = "equipment_instances"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    item_id: Mapped[str] = mapped_column(String(40))
    rarity: Mapped[str] = mapped_column(String(12))
    enhance_level: Mapped[int] = mapped_column(Integer, default=0)
    inscriptions: Mapped[list] = mapped_column(JSON, default=list)
    equipped_slot: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Skill(Base):
    __tablename__ = "skills"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    unlocked_at: Mapped[dt.datetime] = mapped_column(DateTime)


class Bee(Base):
    __tablename__ = "bees"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    bee_type: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer, default=1)
    xp: Mapped[int] = mapped_column(Integer, default=0)
    hive_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    role: Mapped[str] = mapped_column(String(12), default="hive")  # hive|pollinate|guard
    bond: Mapped[int] = mapped_column(Integer, default=0)
    obtained_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Hive(Base):
    __tablename__ = "hive"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    layout: Mapped[dict] = mapped_column(JSON, default=dict)
    level: Mapped[int] = mapped_column(Integer, default=1)
    decorations: Mapped[list] = mapped_column(JSON, default=list)
    honey_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    honey: Mapped[float] = mapped_column(Float, default=0.0)        # Linh Mật waiting to be collected
    wax: Mapped[float] = mapped_column(Float, default=0.0)
    cells: Mapped[int] = mapped_column(Integer, default=5)          # open hexagon cells
    pollen_checked_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class Pet(Base):
    __tablename__ = "pets"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    pet_type: Mapped[str] = mapped_column(String(32))
    level: Mapped[int] = mapped_column(Integer, default=1)
    equipped: Mapped[bool] = mapped_column(Boolean, default=False)


class FishCatch(Base):
    __tablename__ = "fish_catches"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    fish_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    best_size_cm: Mapped[float] = mapped_column(Float, default=0)
    first_caught_at: Mapped[dt.datetime] = mapped_column(DateTime)


class CodexEntry(Base):
    __tablename__ = "codex_entries"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    codex: Mapped[str] = mapped_column(String(12), primary_key=True)  # plant|fish|bee|monster|pet|item
    entry_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    discovered_at: Mapped[dt.datetime] = mapped_column(DateTime)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)


class TdProgress(Base):
    __tablename__ = "td_progress"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    level_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    stars: Mapped[int] = mapped_column(Integer, default=0)
    best_wave: Mapped[int] = mapped_column(Integer, default=0)
    cleared_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)


class TdLoadout(Base):
    __tablename__ = "td_loadout"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    slots: Mapped[list] = mapped_column(JSON, default=list)


class Quest(Base):
    __tablename__ = "quests"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    quest_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    state: Mapped[str] = mapped_column(String(12), default="active")
    progress: Mapped[dict] = mapped_column(JSON, default=dict)


class RealmRun(Base):
    __tablename__ = "realm_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    realm_id: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[dt.datetime] = mapped_column(DateTime)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(String(12), nullable=True)
    members: Mapped[list] = mapped_column(JSON, default=list)


class RealmMember(Base):
    """Who went into which bí cảnh run (stage 9): the daily entry limit counts these rows."""
    __tablename__ = "realm_members"
    __table_args__ = (Index("ix_realm_members_user_day", "user_id", "day"),)
    run_id: Mapped[int] = mapped_column(ForeignKey("realm_runs.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    realm_id: Mapped[str] = mapped_column(String(32))
    day: Mapped[str] = mapped_column(String(10))                 # UTC+7 date of entry
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime)
    left_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(String(12), nullable=True)


class RealmClaim(Base):
    """One reward of a run for one player: a cleared room ('room0'...) or the final chest.
    The primary key makes it impossible to be paid twice for the same thing (spec 14.3)."""
    __tablename__ = "realm_claims"
    run_id: Mapped[int] = mapped_column(ForeignKey("realm_runs.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    stage: Mapped[str] = mapped_column(String(16), primary_key=True)
    loot: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class RealmLoot(Base):
    __tablename__ = "realm_loot"
    __table_args__ = (UniqueConstraint("run_id", "user_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("realm_runs.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(UserFK())
    item_id: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer, default=1)


class ChatReport(Base):
    __tablename__ = "chat_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    reporter_id: Mapped[int] = mapped_column(UserFK())
    reported_id: Mapped[int] = mapped_column(UserFK())
    message: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class Block(Base):
    __tablename__ = "blocks"
    user_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    blocked_id: Mapped[int] = mapped_column(UserFK(), primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    currency_or_item: Mapped[str] = mapped_column(String(40))
    delta: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(String(40))
    ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)


class TribulationRun(Base):
    """Thiên Kiếp (spec 7.3): one 20-question exam to enter a new realm."""
    __tablename__ = "tribulation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    from_realm: Mapped[str] = mapped_column(String(16))
    to_realm: Mapped[str] = mapped_column(String(16))
    words: Mapped[list] = mapped_column(JSON, default=list)
    index: Mapped[int] = mapped_column(Integer, default=0)       # questions answered so far
    correct: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[str | None] = mapped_column(String(8), nullable=True)   # passed | failed


class TdRun(Base):
    """Ải Thủ Vườn (stage 7): a run being played. The log is saved as it grows (/td/event), so
    a game closed in the middle of a level can continue it, and what is saved can never be
    taken back (/td/finish must start with it)."""
    __tablename__ = "td_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    level_id: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON)
    questions: Mapped[dict] = mapped_column(JSON, default=dict)   # session id -> {kind, word, ok}
    events: Mapped[list] = mapped_column(JSON, default=list)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime)


class AlchemySession(Base):
    """Luyện đan (stage 8): one fire being tended. Ingredients and the fee are taken when it
    is lit; the zones and the readings to type stay here until /alchemy/finish."""
    __tablename__ = "alchemy_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(UserFK(), index=True)
    recipe_id: Mapped[str] = mapped_column(String(32))
    params: Mapped[dict] = mapped_column(JSON)          # zones, periods, characters (with answer keys)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AdminAction(Base):
    """Stage 10: every admin command that changes something (spec 17), from chat or from
    `python -m app.admin_cli`. Names are copied so the log still reads after an account
    is deleted."""
    __tablename__ = "admin_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    admin_name: Mapped[str] = mapped_column(String(40))          # username, or "cli"
    action: Mapped[str] = mapped_column(String(20), index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_name: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detail: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime)
