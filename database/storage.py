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
from database.models import Base, WhitelistedUser, DownloadStat, ActiveUser, ActiveGroup, Cookie, DownloadHistory, UserProfile, AppSetting

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
                
                # Auto-migrate new columns
                from sqlalchemy import text
                with self.Session() as sess:
                    try:
                        sess.execute(text("ALTER TABLE user_profiles ADD COLUMN notified_expiry_soon INTEGER DEFAULT 0"))
                        sess.commit()
                    except Exception:
                        sess.rollback()
                    try:
                        sess.execute(text("ALTER TABLE user_profiles ADD COLUMN notified_expired INTEGER DEFAULT 0"))
                        sess.commit()
                    except Exception:
                        sess.rollback()
                    try:
                        sess.execute(text("ALTER TABLE user_profiles ADD COLUMN referred_by BIGINT"))
                        sess.commit()
                    except Exception:
                        sess.rollback()
                    try:
                        sess.execute(text("ALTER TABLE user_profiles ADD COLUMN referral_count INTEGER DEFAULT 0"))
                        sess.commit()
                    except Exception:
                        sess.rollback()
            except Exception as e:
                logging.error(f"❌ Failed to connect to database: {e}")
                self.db_engine = None
        else:
            logging.warning("⚠️ DATABASE_URL not found. Using local files (data will be lost on Heroku restart).")
        
        # In-memory cache
        self.downloads_count = defaultdict(int)
        self.active_users: Dict[str, Set[int]] = {}
        self.whitelisted_users = set()
        self.active_groups = set()
        
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
                        
                    # Load active groups
                    groups = session.query(ActiveGroup).all()
                    for group in groups:
                        self.active_groups.add(group.chat_id)
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
                    self.active_groups = set(data.get('active_groups', []))
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
                    'active_users': active_users_data,
                    'active_groups': list(self.active_groups)
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

    def add_active_group(self, chat_id: int):
        if chat_id in self.active_groups:
            return
            
        self.active_groups.add(chat_id)
        if self.Session:
            try:
                with self.Session() as session:
                    exists = session.query(ActiveGroup).filter_by(chat_id=chat_id).first()
                    if not exists:
                        session.add(ActiveGroup(chat_id=chat_id))
                        session.commit()
            except Exception as e:
                logging.error(f"Error adding active group to DB: {e}")
        else:
            self._save_data()

    def get_username_by_id(self, user_id: int) -> str:
        """Returns the username associated with standard user id, or None."""
        if self.Session:
            try:
                from database.models import DownloadHistory
                with self.Session() as session:
                    # Get the most recent download for this user to get their current username
                    history = session.query(DownloadHistory).filter_by(user_id=user_id).order_by(DownloadHistory.timestamp.desc()).first()
                    if history and history.username:
                        return history.username
            except Exception as e:
                logging.error(f"Error getting username by ID: {e}")
        return None
    
    def get_user_downloads_count(self, user_id: int) -> int:
        if self.Session:
            try:
                from database.models import DownloadHistory
                with self.Session() as session:
                    count = session.query(func.count(DownloadHistory.id)).filter_by(user_id=user_id).scalar()
                    return count or 0
            except Exception as e:
                logging.error(f"Error getting user downloads count: {e}")
        return 0

    def get_total_premium_users(self) -> int:
        if self.Session:
            try:
                from database.models import UserProfile
                from datetime import datetime
                with self.Session() as session:
                    count = session.query(func.count(UserProfile.user_id)).filter(
                        (UserProfile.is_premium == 1) &
                        ((UserProfile.premium_expiry.is_(None)) | (UserProfile.premium_expiry > datetime.now()))
                    ).scalar()
                    return count or 0
            except Exception as e:
                logging.error(f"Error getting total premium users: {e}")
        return 0

    def get_all_premium_users(self) -> list:
        """Get list of all users with active premium."""
        if self.Session:
            try:
                from database.models import UserProfile
                from datetime import datetime
                with self.Session() as session:
                    users = session.query(UserProfile).filter(
                        (UserProfile.is_premium == 1) &
                        ((UserProfile.premium_expiry.is_(None)) | (UserProfile.premium_expiry > datetime.now()))
                    ).order_by(UserProfile.premium_expiry.asc()).all()
                    return [
                        {
                            'user_id': u.user_id,
                            'premium_expiry': u.premium_expiry,
                            'referral_count': u.referral_count or 0,
                            'referred_by': u.referred_by,
                        }
                        for u in users
                    ]
            except Exception as e:
                logging.error(f"Error getting all premium users: {e}")
        return []

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
                        'active_users': active_users,
                        'active_groups_count': len(self.active_groups),
                        'active_groups': list(self.active_groups)
                    }
            except Exception as e:
                logging.error(f"Error getting stats from DB: {e}")
                return {'video_count': 0, 'audio_count': 0, 'active_users_count': 0, 'active_users': set(), 'active_groups_count': 0, 'active_groups': []}
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
                'active_users': active_users,
                'active_groups_count': len(self.active_groups),
                'active_groups': list(self.active_groups)
            }

    def remove_history_entry(self, history_id: int) -> bool:
        if self.Session:
            try:
                with self.Session() as session:
                    entry = session.query(DownloadHistory).filter_by(id=history_id).first()
                    if entry:
                        session.delete(entry)
                        session.commit()
                        return True
                    return False
            except Exception as e:
                logging.error(f"Error removing history entry from DB: {e}")
                return False
        else:
            # File fallback for history is a text log, not easily removable by ID
            # In file mode, we just return False for now or recommend manually editing logs/downloads.log
            return False

    # Premium and Settings Methods
    def get_user_profile(self, user_id: int) -> dict:
        if not self.Session:
            return {"is_premium": False, "premium_expiry": None, "daily_premium_site_downloads": 0}
            
        with self.Session() as session:
            profile = session.query(UserProfile).filter_by(user_id=user_id).first()
            if not profile:
                profile = UserProfile(user_id=user_id)
                session.add(profile)
                session.commit()
                session.refresh(profile)
                
            today = datetime.now().strftime("%Y-%m-%d")
            if profile.last_reset_date != today:
                profile.daily_premium_site_downloads = 0
                profile.last_reset_date = today
                session.commit()
                
            is_premium = bool(profile.is_premium)
            if is_premium and profile.premium_expiry and profile.premium_expiry < datetime.now():
                is_premium = False
                profile.is_premium = 0
                session.commit()
                
            return {
                "is_premium": is_premium,
                "premium_expiry": profile.premium_expiry,
                "daily_premium_site_downloads": profile.daily_premium_site_downloads
            }

    def unlock_premium(self, user_id: int, days: int = 30) -> bool:
        if not self.Session:
            return False
            
        with self.Session() as session:
            profile = session.query(UserProfile).filter_by(user_id=user_id).first()
            if not profile:
                profile = UserProfile(user_id=user_id)
                session.add(profile)
                
            profile.is_premium = 1
            if profile.premium_expiry and profile.premium_expiry > datetime.now():
                profile.premium_expiry = profile.premium_expiry + timedelta(days=days)
            else:
                profile.premium_expiry = datetime.now() + timedelta(days=days)
                
            session.commit()
            return True

    def increment_daily_premium(self, user_id: int) -> int:
        if not self.Session:
            return 0
            
        with self.Session() as session:
            profile = session.query(UserProfile).filter_by(user_id=user_id).first()
            if not profile:
                profile = UserProfile(user_id=user_id)
                session.add(profile)
                
            today = datetime.now().strftime("%Y-%m-%d")
            if profile.last_reset_date != today:
                profile.daily_premium_site_downloads = 0
                profile.last_reset_date = today
                
            profile.daily_premium_site_downloads += 1
            count = profile.daily_premium_site_downloads
            session.commit()
            return count

    def get_app_setting(self, key: str, default: str = "False") -> str:
        if not self.Session:
            return default
            
        with self.Session() as session:
            setting = session.query(AppSetting).filter_by(key=key).first()
            if setting:
                return setting.value
            
            # Create if not exists
            new_setting = AppSetting(key=key, value=default)
            session.add(new_setting)
            session.commit()
            return default

    def toggle_app_setting(self, key: str) -> str:
        if not self.Session:
            return "False"
            
        with self.Session() as session:
            setting = session.query(AppSetting).filter_by(key=key).first()
            if not setting:
                setting = AppSetting(key=key, value="False")
                session.add(setting)
                
            new_val = "False" if setting.value == "True" else "True"
            setting.value = new_val
            session.commit()
            return new_val

    def set_app_setting(self, key: str, value: str) -> None:
        if not self.Session:
            return
            
        with self.Session() as session:
            setting = session.query(AppSetting).filter_by(key=key).first()
            if not setting:
                setting = AppSetting(key=key, value=value)
                session.add(setting)
            else:
                setting.value = value
            session.commit()

    def process_referral(self, new_user_id: int, referrer_id: int) -> dict:
        """Process a referral: record who referred the new user, increment referrer's count.
        Returns dict with 'success', 'referral_count', 'premium_granted', 'error'."""
        if not self.Session:
            return {'success': False, 'referral_count': 0, 'premium_granted': False}
        
        if new_user_id == referrer_id:
            return {'success': False, 'referral_count': 0, 'premium_granted': False, 'error': 'self_referral'}
        
        with self.Session() as session:
            # CHECK IF USER IS NEW
            # 1. Check if they have any download history
            has_history = session.query(DownloadHistory).filter_by(user_id=new_user_id).first() is not None
            if has_history:
                return {'success': False, 'referral_count': 0, 'premium_granted': False, 'error': 'not_new_user'}
            
            # 2. Check if they have been active before today
            today = datetime.now().date().isoformat()
            was_active_before = session.query(ActiveUser).filter(ActiveUser.user_id == new_user_id, ActiveUser.date < today).first() is not None
            if was_active_before:
                return {'success': False, 'referral_count': 0, 'premium_granted': False, 'error': 'not_new_user'}

            # Ensure new user profile exists
            new_profile = session.query(UserProfile).filter_by(user_id=new_user_id).first()
            if not new_profile:
                new_profile = UserProfile(user_id=new_user_id)
                session.add(new_profile)
                session.flush()
            
            # Check if this user was already referred by someone
            if new_profile.referred_by:
                return {'success': False, 'referral_count': 0, 'premium_granted': False, 'error': 'already_referred'}
            
            # Record the referral
            new_profile.referred_by = referrer_id
            
            # Increment referrer's count
            referrer = session.query(UserProfile).filter_by(user_id=referrer_id).first()
            if not referrer:
                referrer = UserProfile(user_id=referrer_id)
                session.add(referrer)
                session.flush()
            
            referrer.referral_count = (referrer.referral_count or 0) + 1
            count = referrer.referral_count
            
            # Grant 1 day premium every 3 referrals
            premium_granted = False
            if count % 3 == 0:
                referrer.is_premium = 1
                if referrer.premium_expiry and referrer.premium_expiry > datetime.now():
                    referrer.premium_expiry = referrer.premium_expiry + timedelta(days=1)
                else:
                    referrer.premium_expiry = datetime.now() + timedelta(days=1)
                premium_granted = True
            
            session.commit()
            return {'success': True, 'referral_count': count, 'premium_granted': premium_granted}

    def get_referral_count(self, user_id: int) -> int:
        """Get the referral count for a user."""
        if not self.Session:
            return 0
        with self.Session() as session:
            profile = session.query(UserProfile).filter_by(user_id=user_id).first()
            if profile:
                return profile.referral_count or 0
            return 0

    def get_total_referral_users(self) -> int:
        """Get the total number of users who joined via a referral link."""
        if not self.Session:
            return 0
        try:
            with self.Session() as session:
                count = session.query(func.count(UserProfile.user_id)).filter(
                    UserProfile.referred_by.isnot(None)
                ).scalar()
                return count or 0
        except Exception as e:
            logging.error(f"Error getting total referral users: {e}")
            return 0

    def get_total_referral_premium_users(self) -> int:
        """Get the number of users who have premium AND were referred by someone."""
        if not self.Session:
            return 0
        try:
            with self.Session() as session:
                count = session.query(func.count(UserProfile.user_id)).filter(
                    UserProfile.referred_by.isnot(None),
                    UserProfile.is_premium == 1
                ).scalar()
                return count or 0
        except Exception as e:
            logging.error(f"Error getting total referral premium users: {e}")
            return 0

stats = Stats()
