from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from typing import Dict, Optional, Tuple
import logging
import os
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select

from ..database.db import Database
from ..database.models import UserSession

logger = logging.getLogger(__name__)

class SessionManager:
    CODE_TIMEOUT = 120
    LOGIN_COOLDOWN = 60
    MAX_CONCURRENT_LOGINS = 5

    def __init__(self):
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.active_clients: Dict[int, TelegramClient] = {}
        self.pending_logins: Dict[str, Tuple[datetime, TelegramClient]] = {}
        self.login_locks: Dict[str, asyncio.Lock] = {}
        self.db = Database()

    def _get_login_lock(self, phone: str) -> asyncio.Lock:
        """Get or create a lock for a specific phone number."""
        if phone not in self.login_locks:
            self.login_locks[phone] = asyncio.Lock()
        return self.login_locks[phone]

    async def _cleanup_old_logins(self):
        """Clean up expired login attempts."""
        now = datetime.now()
        expired_phones = [
            phone for phone, (timestamp, _) in self.pending_logins.items()
            if (now - timestamp).total_seconds() > self.CODE_TIMEOUT
        ]
        
        for phone in expired_phones:
            _, client = self.pending_logins.pop(phone)
            try:
                await client.disconnect()
            except:
                pass
            
            if phone in self.login_locks:
                del self.login_locks[phone]

    async def create_client(self, phone_number: str, user_id: int) -> TelegramClient:
        """Create a new Telethon client for the given phone number."""
        await self._cleanup_old_logins()
        
        if len(self.pending_logins) >= self.MAX_CONCURRENT_LOGINS:
            raise ValueError("Too many concurrent login attempts. Please try again later.")

        lock = self._get_login_lock(phone_number)
        
        try:
            async with lock:
                if phone_number in self.pending_logins:
                    last_attempt, old_client = self.pending_logins[phone_number]
                    time_diff = (datetime.now() - last_attempt).total_seconds()
                    
                    if time_diff < self.LOGIN_COOLDOWN:
                        raise ValueError(
                            f"Please wait {int(self.LOGIN_COOLDOWN - time_diff)} seconds "
                            "before requesting another code."
                        )
                    
                    try:
                        await old_client.disconnect()
                    except:
                        pass

                session = StringSession()
                client = TelegramClient(
                    session,
                    self.api_id,
                    self.api_hash,
                    device_model=f"UserBot_{user_id}",
                    system_version="Bot System",
                    app_version="1.0",
                    timeout=30
                )
                
                try:
                    await client.connect()
                    
                    if not await client.is_user_authorized():
                        await client.send_code_request(
                            phone_number,
                            force_sms=False
                        )
                        self.pending_logins[phone_number] = (datetime.now(), client)
                        asyncio.create_task(self._schedule_cleanup(phone_number))
                        return client
                    
                except errors.FloodWaitError as e:
                    await client.disconnect()
                    raise ValueError(
                        f"Too many attempts. Please wait {e.seconds} seconds."
                    )
                except errors.PhoneNumberBannedError:
                    await client.disconnect()
                    raise ValueError("This phone number is banned from Telegram.")
                except Exception as e:
                    await client.disconnect()
                    raise ValueError(f"Error sending code: {str(e)}")

        except Exception as e:
            if phone_number in self.login_locks:
                del self.login_locks[phone_number]
            raise
        return client

    async def _schedule_cleanup(self, phone_number: str):
        """Schedule cleanup of a pending login after timeout."""
        await asyncio.sleep(self.CODE_TIMEOUT)
        if phone_number in self.pending_logins:
            _, client = self.pending_logins.pop(phone_number)
            try:
                await client.disconnect()
            except:
                pass
            
            if phone_number in self.login_locks:
                del self.login_locks[phone_number]

    async def load_session(self, user_id: int) -> Optional[TelegramClient]:
        """Load an existing session from the database."""
        async for db_session in self.db.get_session():
            stmt = select(UserSession).where(UserSession.user_id == user_id)
            result = await db_session.execute(stmt)
            user_session = result.scalar_one_or_none()
            
            if user_session and user_session.session_string:
                try:
                    client = TelegramClient(
                        StringSession(user_session.session_string),
                        self.api_id,
                        self.api_hash,
                        device_model=f"UserBot_{user_id}",
                        system_version="Bot System",
                        app_version="1.0"
                    )
                    await client.connect()
                    if await client.is_user_authorized():
                        self.active_clients[user_id] = client
                        return client
                    else:
                        logger.warning(f"Session for user {user_id} is no longer authorized. Deleting.")
                        await db_session.delete(user_session)
                        await db_session.commit()
                        await client.disconnect()
                except Exception as e:
                    logger.error(f"Error loading session for user {user_id}: {e}")
            return None

    async def get_client(self, user_id: int) -> Optional[TelegramClient]:
        """Get an active client or load it from the database."""
        if user_id in self.active_clients:
            client = self.active_clients[user_id]
            try:
                if not client.is_connected(): await client.connect()
                if await client.is_user_authorized(): return client
                else:
                    logger.warning(f"Active client for {user_id} not authorized. Attempting to reload.")
                    del self.active_clients[user_id]
                    return await self.load_session(user_id)
            except Exception as e:
                logger.error(f"Error checking active client for {user_id}: {e}")
                if user_id in self.active_clients: del self.active_clients[user_id]
                return await self.load_session(user_id)
        return await self.load_session(user_id)

    async def disconnect_client(self, user_id: int):
        """Disconnect a client and remove it from active clients."""
        if user_id in self.active_clients:
            try:
                await self.active_clients[user_id].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client for user {user_id}: {e}")
            finally:
                del self.active_clients[user_id]
                logger.info(f"Disconnected and removed client for user {user_id}")

    async def disconnect_all(self):
        """Disconnect all active clients."""
        active_ids = list(self.active_clients.keys())
        for user_id in active_ids:
            await self.disconnect_client(user_id)
        self.active_clients.clear()
        
        pending_phones = list(self.pending_logins.keys())
        for phone in pending_phones:
            if phone in self.pending_logins:
                _, client = self.pending_logins.pop(phone)
                try: await client.disconnect()
                except: pass
            if phone in self.login_locks:
                del self.login_locks[phone]
        logger.info("Disconnected all active and pending clients.")
