import json
import logging
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Set
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from config import DATABASE_URL, DATA_DIR, WHITELISTED_ENV
from database.models import Base, WhitelistedUser, DownloadStat, ActiveUser, Cookie, DownloadHistory

class Stats:
    def __init__(self):
        self.users_file = DATA_DIR / "users.json"
        self.stats_file = DATA_DIR / "stats.json"
        
        self.db_engine = None
        self.Session = None
        
        if DATABASE_URL:
            db_url = DATABASE_URL
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            try:
                self.db_engine = create_engine(db_url)
                Base.metadata.create_all(self.db_engine)
                self.Session = sessionmaker(bind=self.db_engine)
                logging.info("✅ Connected to database successfully")
            except Exception as e:
                logging.error(f"❌ Failed to connect to database: {e}")
                self.db_engine = None
        else:
            logging.warning("⚠️ DATABASE_URL not found. Using local files (data will be lost on Heroku restart).")
        
        # In-memory cache
        self.downloads_count = defaultdict(int)
        self.active_users: Dict[str, Set[int]] = {}
        self.whitelisted_users = set()
        
        self._load_data()
        
    def _load_data(self):
        """Load data from DB or JSON files"""
        # Load from ENV
        if WHITELISTED_ENV:
            for user in WHITELISTED_ENV.split(";"):
                if user.strip():
                    self.whitelisted_users.add(user.strip())

        if self.Session:
            try:
                with self.Session() as session:
                    # Load whitelist
                    users = session.query(WhitelistedUser).all()
                    for u in users:
                        self.whitelisted_users.add(u.username)
                    
                    # Load stats
                    stats = session.query(DownloadStat).all()
                    for stat in stats:
                        self.downloads_count[stat.content_type] = stat.count
            except Exception as e:
                logging.error(f"Error loading from DB: {e}")
        else:
            # File fallback
            if self.users_file.exists():
                try:
                    with open(self.users_file, 'r') as f:
                        data = json.loads(f.read())
                    self.whitelisted_users.update(data.get('whitelisted_users', []))
                except Exception as e:
                    logging.error(f"Error loading whitelist file: {e}")
                    
            if self.stats_file.exists():
                try:
                    with open(self.stats_file, 'r') as f:
                        data = json.loads(f.read())
                    self.downloads_count = defaultdict(int, data.get('downloads_count', {}))
                    active_users_data = data.get('active_users', {})
                    self.active_users = {
                        date: set(users) 
                        for date, users in active_users_data.items()
                    }
                except Exception as e:
                    logging.error(f"Error loading stats file: {e}")

    def _save_data(self):
        """Save to JSON files (only used in file mode)"""
        if self.Session:
            return

        try:
            with open(self.users_file, 'w') as f:
                json.dump({'whitelisted_users': list(self.whitelisted_users)}, f, indent=4)
                
            with open(self.stats_file, 'w') as f:
                active_users_data = {date: list(users) for date, users in self.active_users.items()}
                json.dump({
                    'downloads_count': dict(self.downloads_count),
                    'active_users': active_users_data
                }, f, indent=4)
        except Exception as e:
            logging.error(f"Error saving data: {e}")

    def add_download(self, content_type: str, user_id: int = None, username: str = None, platform: str = None, url: str = None, title: str = None):
        self.downloads_count[content_type] += 1
        
        if self.Session:
            try:
                with self.Session() as session:
                    # Update stats
                    stat = session.query(DownloadStat).filter_by(content_type=content_type).first()
                    if not stat:
                        stat = DownloadStat(content_type=content_type, count=0)
                        session.add(stat)
                    stat.count += 1
                    
                    # Add history
                    if user_id:
                        history = DownloadHistory(
                            user_id=user_id,
                            username=username,
                            platform=platform,
                            content_type=content_type,
                            url=url,
                            title=title
                        )
                        session.add(history)
                    
                    session.commit()
            except Exception as e:
                logging.error(f"Error saving download stat/history to DB: {e}")
        else:
            self._save_data()
        
    def add_to_whitelist(self, username: str) -> bool:
        if username in self.whitelisted_users:
            return False
        self.whitelisted_users.add(username)
        
        if self.Session:
            try:
                with self.Session() as session:
                    if not session.query(WhitelistedUser).filter_by(username=username).first():
                        session.add(WhitelistedUser(username=username))
                        session.commit()
            except Exception as e:
                logging.error(f"Error adding to whitelist DB: {e}")
        else:
            self._save_data()
        return True
        
    def remove_from_whitelist(self, username: str) -> bool:
        if username not in self.whitelisted_users:
            return False
        self.whitelisted_users.remove(username)
        
        if self.Session:
            try:
                with self.Session() as session:
                    session.query(WhitelistedUser).filter_by(username=username).delete()
                    session.commit()
            except Exception as e:
                logging.error(f"Error removing from whitelist DB: {e}")
        else:
            self._save_data()
        return True
        
    def is_whitelisted(self, username: str) -> bool:
        return username in self.whitelisted_users
    
    def add_active_user(self, user_id: int):
        today = datetime.now().date().isoformat()
        
        if self.Session:
            try:
                with self.Session() as session:
                    exists = session.query(ActiveUser).filter_by(user_id=user_id, date=today).first()
                    if not exists:
                        session.add(ActiveUser(user_id=user_id, date=today))
                        session.commit()
            except Exception as e:
                logging.error(f"Error adding active user to DB: {e}")
        else:
            if today not in self.active_users:
                self.active_users[today] = set()
            self.active_users[today].add(user_id)
            self._save_data()
    
    def get_weekly_stats(self):
        today = datetime.now().date()
        week_ago = today - timedelta(days=7)
        
        if self.Session:
            try:
                with self.Session() as session:
                    video_stat = session.query(DownloadStat).filter_by(content_type='Video').first()
                    audio_stat = session.query(DownloadStat).filter_by(content_type='Music').first()
                    total_video = video_stat.count if video_stat else 0
                    total_audio = audio_stat.count if audio_stat else 0
                    
                    week_ago_str = week_ago.isoformat()
                    active_count = session.query(func.count(func.distinct(ActiveUser.user_id)))\
                        .filter(ActiveUser.date >= week_ago_str).scalar()
                        
                    active_users_query = session.query(func.distinct(ActiveUser.user_id))\
                        .filter(ActiveUser.date >= week_ago_str).all()
                    active_users = {u[0] for u in active_users_query}
                    
                    return {
                        'video_count': total_video,
                        'audio_count': total_audio,
                        'active_users_count': active_count,
                        'active_users': active_users
                    }
            except Exception as e:
                logging.error(f"Error getting stats from DB: {e}")
                return {'video_count': 0, 'audio_count': 0, 'active_users_count': 0, 'active_users': set()}
        else:
            total_video = self.downloads_count['Video']
            total_audio = self.downloads_count['Music']
            
            active_users = set()
            for date_str, users in list(self.active_users.items()):
                date = datetime.fromisoformat(date_str).date()
                if date >= week_ago:
                    active_users.update(users)
                elif date < week_ago:
                    del self.active_users[date_str]
                    self._save_data()
                    
            return {
                'video_count': total_video,
                'audio_count': total_audio,
                'active_users_count': len(active_users),
                'active_users': active_users
            }

stats = Stats()
