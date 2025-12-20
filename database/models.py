from sqlalchemy import Column, Integer, String, DateTime, BigInteger
from sqlalchemy.orm import declarative_base
from datetime import datetime

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

class Cookie(Base):
    __tablename__ = 'cookies'
    id = Column(Integer, primary_key=True)
    content = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)

class DownloadHistory(Base):
    __tablename__ = 'download_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger)
    username = Column(String)
    platform = Column(String)
    content_type = Column(String)
    url = Column(String)
    title = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
