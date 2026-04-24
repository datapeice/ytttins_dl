from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from sqlalchemy.orm import declarative_base
from datetime import datetime, UTC

Base = declarative_base()

class WhitelistedUser(Base):
    __tablename__ = 'whitelisted_users'
    username = Column(String, primary_key=True)
    added_at = Column(DateTime, default=datetime.utcnow)

class DownloadStat(Base):
    __tablename__ = 'download_stats'
    content_type = Column(String, primary_key=True) # 'Video' or 'Music'
    count = Column(Integer, default=0)

class ActiveUser(Base):
    __tablename__ = 'active_users'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    date = Column(String) # YYYY-MM-DD

class ActiveGroup(Base):
    __tablename__ = 'active_groups'
    chat_id = Column(BigInteger, primary_key=True)
    added_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

class Cookie(Base):
    __tablename__ = 'cookies'
    id = Column(Integer, primary_key=True)
    content = Column(String)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

class DownloadHistory(Base):
    __tablename__ = 'download_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    username = Column(String)
    platform = Column(String)
    content_type = Column(String)
    url = Column(String)
    title = Column(String)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

class UserProfile(Base):
    __tablename__ = 'user_profiles'
    user_id = Column(BigInteger, primary_key=True)
    is_premium = Column(Integer, default=0) # 1 for True, 0 for False
    premium_expiry = Column(DateTime, nullable=True)
    daily_premium_site_downloads = Column(Integer, default=0)
    last_reset_date = Column(String)
    notified_expiry_soon = Column(Integer, default=0)
    notified_expired = Column(Integer, default=0)
    referred_by = Column(BigInteger, nullable=True)
    referral_count = Column(Integer, default=0)

class AppSetting(Base):
    __tablename__ = 'app_settings'
    key = Column(String, primary_key=True)
    value = Column(String)

class DownloadQueueItem(Base):
    __tablename__ = 'download_queue'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    url = Column(String)
    status = Column(String, default='pending')
    added_at = Column(DateTime, default=datetime.utcnow)
