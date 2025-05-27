from telethon import TelegramClient, events, Button, errors
from telethon.tl.types import InputReportReasonSpam, InputReportReasonViolence, \
                                InputReportReasonPornography, InputReportReasonChildAbuse, \
                                InputReportReasonCopyright, InputReportReasonGeoIrrelevant, \
                                InputReportReasonFake, InputReportReasonOther
from telethon.tl.functions.account import ReportPeerRequest
from telethon.sessions import StringSession
from telethon.utils import get_display_name

from typing import Dict, Optional, List, Callable, Any
import logging
import os
import re
from enum import Enum, auto
import json
from functools import wraps
import traceback

from sqlalchemy import select, delete as sqlalchemy_delete

from .session_manager import SessionManager
from .plugin_loader import PluginLoader
from ..database.models import UserSession, ReportSetting

logger = logging.getLogger(__name__)

def ensure_registered(func: Callable) -> Callable:
    """Decorator to ensure handlers are properly registered."""
    @wraps(func)
    async def wrapper(self, event, *args, **kwargs):
        try:
            return await func(self, event, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error in handler {func.__name__}: {e}")
            try:
                if hasattr(event, 'respond'):
                    await event.respond(
                        "An error occurred while processing your request.\n"
                        "Please try again or contact support."
                    )
                elif hasattr(event, 'chat_id') and event.chat_id:
                    await self.bot.send_message(event.chat_id,
                        "An error occurred while processing your request.\n"
                        "Please try again or contact support."
                    )
            except Exception as resp_err:
                logger.error(f"Failed to send error response in handler {func.__name__}: {resp_err}")
    return wrapper

class LoginState(Enum):
    """Enum for tracking user login state."""
    AWAITING_PHONE = auto()
    AWAITING_CODE = auto()
    AWAITING_2FA = auto()
    PROCESSING_2FA = auto()

class UserState:
    """Class to manage user state during login process."""
    def __init__(self, state: LoginState):
        self.state = state
        self.attempts = 0
        self.phone: Optional[str] = None
        self.client: Optional[TelegramClient] = None
        self.code_digits: List[str] = []
        self.code_message_id: Optional[int] = None
        self.last_message_id: Optional[int] = None

    def increment_attempts(self) -> int:
        """Increment attempt counter and return new value."""
        self.attempts += 1
        return self.attempts

    def reset_attempts(self):
        """Reset attempt counter."""
        self.attempts = 0

    def add_digit(self, digit: str) -> bool:
        """Add a digit to the code. Returns True if code is complete."""
        if len(self.code_digits) < 5:
            self.code_digits.append(digit)
            return len(self.code_digits) == 5
        return False

    def remove_digit(self) -> None:
        """Remove the last digit from the code."""
        if self.code_digits:
            self.code_digits.pop()

    def get_code(self) -> str:
        """Get the current code as a string."""
        return ''.join(self.code_digits)

    def clear_code(self) -> None:
        """Clear the current code."""
        self.code_digits.clear()

    async def cleanup_messages(self, bot: TelegramClient):
        """Clean up bot messages associated with this state."""
        try:
            if self.code_message_id and self.code_message_id != self.last_message_id:
                await bot.delete_messages(None, self.code_message_id)
        except Exception as e:
            logger.warning(f"Could not delete code_message_id {self.code_message_id}: {e}")
        finally:
            self.code_message_id = None

        try:
            if self.last_message_id:
                await bot.delete_messages(None, self.last_message_id)
        except Exception as e:
            logger.warning(f"Could not delete last_message_id {self.last_message_id}: {e}")
        finally:
            self.last_message_id = None

    async def safe_edit_message(self, bot: TelegramClient, chat_id: int, text: str, buttons: Optional[List[List[Button]]] = None) -> bool:
        """Safely edit a message, handling potential errors."""
        if not self.last_message_id:
            logger.warning("safe_edit_message called with no last_message_id")
            try:
                message = await bot.send_message(chat_id, text, buttons=buttons)
                self.last_message_id = message.id
                if self.state == LoginState.AWAITING_CODE:
                    self.code_message_id = message.id
                return True
            except Exception as e:
                logger.error(f"Error sending new message in safe_edit_message: {e}")
            return False
        try:
            await bot.edit_message(
                chat_id,
                self.last_message_id,
                text,
                buttons=buttons
            )
            return True
        except (errors.MessageIdInvalidError, errors.MessageNotModifiedError):
            logger.warning(f"Original message {self.last_message_id} not found or not modified, sending new message.")
            try:
                message = await bot.send_message(
                    chat_id,
                    text,
                    buttons=buttons
                )
                self.last_message_id = message.id
                if self.state == LoginState.AWAITING_CODE:
                     self.code_message_id = message.id
                return True
            except Exception as e:
                logger.error(f"Error sending new message after edit failed: {e}")
        except Exception as e:
            logger.error(f"Error editing message {self.last_message_id}: {e}")
        return False

class PhoneNumberError(Exception):
    """Custom exception for phone number validation errors."""
    pass

class BotManager:
    def __init__(self):
        """Initialize the bot manager with required components."""
        self.api_id = int(os.getenv('API_ID'))
        self.api_hash = os.getenv('API_HASH')
        self.bot_token = os.getenv('BOT_TOKEN')
        
        self.session_manager = SessionManager()
        self.plugin_loader = PluginLoader()
        
        self.pending_logins: Dict[int, UserState] = {}
        
        self.bot = TelegramClient('bot', self.api_id, self.api_hash)

        self.commands = {
            'start': {
                'pattern': re.compile(r'^/start$'),
                'description': 'شروع کار با ربات و مشاهده دستورات موجود'
            },
            'add': {
                'pattern': re.compile(r'^/add$'),
                'description': 'افزودن یک اکانت کاربری جدید (یوزربات)'
            },
            'my_accounts': {
                'pattern': re.compile(r'^/my_accounts$'),
                'description': 'نمایش لیست تمام اکانت‌های یوزربات اضافه شده شما'
            },
            'logout': {
                'pattern': re.compile(r'^/logout\s+(\S+)$'),
                'description': 'خروج از یک اکانت یوزربات مشخص. مثال: <code>/logout +989123456789</code>'
            },
            'set_report_message': {
                'pattern': re.compile(r'^/set_report_message\s+(.+)$', re.DOTALL),
                'description': 'تنظیم پیام پیش‌فرض برای گزارش. مثال: <code>/set_report_message این یک پیام تستی است</code>'
            },
            'report': {
                'pattern': re.compile(r'^/report\s+(@?\S+)\s+(\S+)$'),
                'description': 'گزارش یک هدف (کاربر/کانال/گروه) با تمام اکانت‌های شما. مثال: <code>/report @username spam</code> یا <code>/report 123456789 other</code>'
            },
            'cancel': {
                'pattern': re.compile(r'^/cancel$'),
                'description': 'لغو عملیات فعلی'
            },
            'help': {
                'pattern': re.compile(r'^/help$'),
                'description': 'نمایش پیام راهنما'
            }
        }

        self.phone_regex = re.compile(r'^\+[1-9]\d{6,14}$')

        self.report_reason_map = {
            "spam": InputReportReasonSpam(),
            "violence": InputReportReasonViolence(),
            "porn": InputReportReasonPornography(),
            "childabuse": InputReportReasonChildAbuse(),
            "copyright": InputReportReasonCopyright(),
            "geo": InputReportReasonGeoIrrelevant(),
            "fake": InputReportReasonFake(),
            "other": InputReportReasonOther(),
        }

    async def setup(self):
        """Set up the bot and register all handlers."""
        logger.info("Setting up bot manager...")
        
        self._register_handlers()
        
        await self.bot.start(bot_token=self.bot_token)
        
        await self.plugin_loader.discover_plugins()
        
        logger.info("Bot setup completed successfully")

    def _register_handlers(self):
        """Register all message and callback handlers."""
        self.bot.add_event_handler(
            self.handle_start,
            events.NewMessage(pattern=self.commands['start']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_add_account,
            events.NewMessage(pattern=self.commands['add']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_my_accounts,
            events.NewMessage(pattern=self.commands['my_accounts']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_logout_account,
            events.NewMessage(pattern=self.commands['logout']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_cancel,
            events.NewMessage(pattern=self.commands['cancel']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_help,
            events.NewMessage(pattern=self.commands['help']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_set_report_message,
            events.NewMessage(pattern=self.commands['set_report_message']['pattern'])
        )
        self.bot.add_event_handler(
            self.handle_report_target,
            events.NewMessage(pattern=self.commands['report']['pattern'])
        )
        
        self.bot.add_event_handler(
            self.handle_callback,
            events.CallbackQuery()
        )
        
        self.bot.add_event_handler(
            self.handle_message,
            events.NewMessage(func=lambda e: not self.is_command(e.text))
        )

    @ensure_registered
    async def handle_start(self, event):
        commands_html_list = ""
        for cmd, info in self.commands.items():
            commands_html_list += f"🔹 /<b>{cmd}</b> - {info['description']}\n"
        
        start_message = (
            f"👋 <b>به ربات مدیریت یوزربات خوش آمدید!</b>\n\n"
            f"<i>این ربات به شما کمک می‌کند تا اکانت‌های یوزربات تلگرام خود را به صورت امن مدیریت کنید.</i>\n\n"
            f"<b>دستورات موجود:</b>\n"
            f"{commands_html_list}\n"
            f"ℹ️ برای شروع، از دستور /<b>add</b> برای افزودن اولین اکانت یوزربات خود استفاده کنید."
        )
        await event.respond(start_message, parse_mode='html')

    @ensure_registered
    async def handle_help(self, event):
        commands_html_list = ""
        for cmd, info in self.commands.items():
            commands_html_list += f"🔹 /<b>{cmd}</b> - {info['description']}\n"

        report_reasons_examples = "\n<b>دلایل گزارش موجود برای دستور <code>/report</code>:</b>\n"
        for reason_alias in self.report_reason_map.keys():
            report_reasons_examples += f"  - <code>{reason_alias}</code>\n"
        report_reasons_examples += "\n<i>مثال استفاده از دلیل:</i> <code>/report @target_user spam</code>\n"

        help_message = (
            f"📚 <b>راهنمای ربات مدیریت یوزربات</b>\n\n"
            f"<i>در اینجا لیست تمام دستورات موجود آمده است:</i>\n"
            f"{commands_html_list}\n"
            f"{report_reasons_examples}\n"
            f"📞 به کمک بیشتری نیاز دارید؟ با <b>@YourSupportUsername</b> تماس بگیرید."
        )
        await event.respond(help_message, parse_mode='html')

    @ensure_registered
    async def handle_my_accounts(self, event):
        """Handle /my_accounts command to list accounts for the requesting user."""
        owner_id = event.sender_id
        try:
            user_specific_sessions = []
            async for db_sess in self.session_manager.db.get_session():
                stmt = select(UserSession).where(UserSession.user_id == owner_id)
                result = await db_sess.execute(stmt)
                user_specific_sessions = result.scalars().all()
            
            if not user_specific_sessions:
                await event.respond("You haven't added any accounts yet. Use /add to add one.")
                return

            response_lines = [f"🔑 Your Added Accounts: {len(user_specific_sessions)}"]
            for i, session_info in enumerate(user_specific_sessions):
                identifier = session_info.phone_number if session_info.phone_number else f"User ID: {session_info.user_id} (DB ID: {session_info.id})"
                response_lines.append(f"{i+1}. {identifier}")
            
            await event.respond("\n".join(response_lines))

        except Exception as e:
            logger.error(f"Error handling /my_accounts for user {owner_id}: {e}")
            await event.respond("An error occurred while fetching your account list. Please try again.")

    @ensure_registered
    async def handle_logout_account(self, event):
        """Handle /logout <phone_number> command."""
        owner_id = event.sender_id
        try:
            phone_to_logout = event.pattern_match.group(1)
            if not phone_to_logout:
                await event.respond("Please specify the phone number to logout. Usage: /logout +1234567890")
                return
            
            normalized_phone = phone_to_logout.strip()
            if not self.validate_phone_number(normalized_phone):
                 await event.respond(f"Invalid phone number format: {normalized_phone}. Please use international format like +1234567890")
                 return

            session_deleted = False
            async for db_sess in self.session_manager.db.get_session():
                stmt = select(UserSession).where(
                    UserSession.user_id == owner_id,
                    UserSession.phone_number == normalized_phone
                )
                result = await db_sess.execute(stmt)
                session_to_delete = result.scalar_one_or_none()
                
                if session_to_delete:
                    await db_sess.delete(session_to_delete)
                    await db_sess.commit()
                    session_deleted = True
                    logger.info(f"User {owner_id} logged out account {normalized_phone}.")
                    if owner_id in self.session_manager.active_clients:
                        active_client = self.session_manager.active_clients[owner_id]
                        client_phone = getattr(active_client, '_self_id_phone', None)
                        if client_phone == normalized_phone or not client_phone:
                           await self.session_manager.disconnect_client(owner_id)
                           logger.info(f"Disconnected active client for owner {owner_id} after logging out {normalized_phone}")
                    break
                else:
                    break
            
            if session_deleted:
                await event.respond(f"Successfully logged out and removed account: {normalized_phone}")
            else:
                await event.respond(f"Account {normalized_phone} not found among your added accounts.")

        except Exception as e:
            logger.error(f"Error handling /logout for user {owner_id}: {e}")
            await event.respond("An error occurred during logout. Please try again.")

    def is_command(self, text: str) -> bool:
        """Check if the message is a command."""
        if not text:
            return False
        return any(info['pattern'].match(text) for info in self.commands.values())

    async def start(self):
        """Start the bot with proper setup."""
        try:
            await self.setup()
            logger.info("Bot is running. Press Ctrl+C to stop.")
            await self.bot.run_until_disconnected()
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            await self.stop()
            raise

    def get_code_keyboard(self, current_code: str) -> List[List[Button]]:
        """Generate the inline keyboard for code entry."""
        keyboard = []
        
        for row_start in range(1, 10, 3):
            row = [
                Button.inline(str(num), f"digit_{num}")
                for num in range(row_start, min(row_start + 3, 10))
            ]
            keyboard.append(row)
        
        bottom_row = [
            Button.inline("⌫", "backspace"),
            Button.inline("0", "digit_0"),
            Button.inline("Clear", "clear")
        ]
        keyboard.append(bottom_row)
        
        if len(current_code) == 5:
            keyboard.append([Button.inline("✅ Submit", "submit")])
        
        return keyboard

    def get_code_message(self, code_digits: List[str]) -> str:
        """Generate the message showing current code entry."""
        dots = '●' * len(code_digits) + '○' * (5 - len(code_digits))
        return (
            "📱 Enter the verification code you received:\n\n"
            f"Code: {dots}\n\n"
            "🔹 Use the keypad below to enter the code\n"
            "🔹 Press ⌫ to delete the last digit\n"
            "🔹 Press Clear to start over\n"
            "🔹 Press ✅ Submit when done"
        )

    async def handle_callback(self, event):
        """Handle inline keyboard callbacks."""
        user_id = event.sender_id
        if user_id not in self.pending_logins:
            await event.answer("No active login session. Please use /add to start.")
            return

        state = self.pending_logins[user_id]
        data = event.data.decode()

        try:
            if state.state == LoginState.AWAITING_CODE:
                await self.handle_code_callback(event, state, data)
            else:
                await event.answer("No active operation for this button.", alert=True)
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            await self.handle_callback_error(event, state, str(e))

    async def handle_code_callback(self, event, state: UserState, data: str):
        """Handle callbacks for code entry."""
        update_message_content = True

        try:
            if data.startswith("digit_"):
                digit = data.split("_")[1]
                is_complete = state.add_digit(digit)
                if is_complete:
                    await event.answer("✅ Code complete! Press Submit.")
                else:
                    await event.answer(f"Added: {digit}")
            
            elif data == "backspace":
                state.remove_digit()
                await event.answer("⌫ Backspace")
            
            elif data == "clear":
                state.clear_code()
                await event.answer("✨ Code Cleared")
            
            elif data == "submit":
                code = state.get_code()
                if len(code) == 5:
                    update_message_content = False
                    await state.safe_edit_message(
                        self.bot,
                        event.chat_id,
                        "🔄 Verifying code... Please wait.",
                        buttons=None
                    )
                    await self.process_verification_code(event, state, code)
                else:
                    await event.answer("❌ Code must be 5 digits. Please complete the code.", alert=True)
            
            else:
                await event.answer("Unknown action.", alert=True)
                update_message_content = False

            if update_message_content:
                new_code_str = state.get_code()
                message_text = self.get_code_message(state.code_digits)
                keyboard = self.get_code_keyboard(new_code_str)
                
                await state.safe_edit_message(
                    self.bot, event.chat_id, message_text, buttons=keyboard
                )

        except Exception as e:
            logger.error(f"Error in code callback: {e}")
            await self.handle_callback_error(event, state, str(e))

    async def process_verification_code(self, event, state: UserState, code: str):
        """Process the verification code and handle 2FA if needed."""
        try:
            await state.client.sign_in(state.phone, code)
            await self.complete_login_flow(event, state)

        except errors.SessionPasswordNeededError:
            state.state = LoginState.AWAITING_2FA
            state.reset_attempts()
            
            await state.cleanup_messages(self.bot)
            
            try:
                msg = await event.respond(
                    "🔐 Two-step verification is enabled. "
                    "Please reply with your password.\n\n"
                    "Use /cancel to abort this operation."
                )
                state.last_message_id = msg.id
            except Exception as e:
                logger.error(f"Could not respond to event for 2FA prompt: {e}. Trying to send to chat_id.")
                try:
                     msg = await self.bot.send_message(event.chat_id,
                        "🔐 Two-step verification is enabled. "
                        "Please reply with your password.\n\n"
                        "Use /cancel to abort this operation."
                     )
                     state.last_message_id = msg.id
                except Exception as e_send:
                    logger.error(f"Failed to send 2FA prompt message directly: {e_send}")
                    await self.cleanup_user_state(event.sender_id)

        except errors.PhoneCodeInvalidError:
            state.clear_code()
            await self.handle_callback_error(event, state, "❌ Invalid code. Please try again.")
        
        except errors.PhoneCodeExpiredError:
            await self.cleanup_user_state(event.sender_id)
            try:
                 await state.safe_edit_message(self.bot, event.chat_id, "❌ Code has expired. Please use /add to request a new code.", buttons=None)
            except:
                 await self.bot.send_message(event.chat_id, "❌ Code has expired. Please use /add to request a new code.")
        
        except Exception as e:
            logger.error(f"Error in verification code processing: {e}")
            await self.handle_callback_error(event, state, "❌ An error occurred during code verification. Please try again.")

    async def handle_callback_error(self, event, state: UserState, error_msg: str):
        """Handle errors in callback processing more robustly."""
        try:
            if "Too many" in error_msg:
                message_text = "❌ Too many attempts. Please wait a few minutes before trying again."
            else:
                message_text = f"{error_msg}"
            
            buttons_to_show = None
            if state.state == LoginState.AWAITING_CODE and "Invalid code" in error_msg:
                message_text = self.get_code_message(state.code_digits) + f"\n\n⚠️ {error_msg}"
                buttons_to_show = self.get_code_keyboard(state.get_code())
            
            success = await state.safe_edit_message(
                self.bot,
                event.chat_id,
                message_text,
                buttons=buttons_to_show
            )
            if not success:
                 await self.bot.send_message(event.chat_id, message_text, buttons=buttons_to_show)

        except Exception as e:
            logger.error(f"Critical error in handle_callback_error: {e}")
            try:
                await self.bot.send_message(event.chat_id, "❌ An critical error occurred. Please use /cancel to start over.")
            except: pass

    async def handle_message(self, event):
        """Handle regular messages for the login flow."""
        user_id = event.sender_id
        
        if user_id not in self.pending_logins:
            return
        
        state = self.pending_logins[user_id]
        text_message = event.message.text

        if not text_message:
            if state.state in [LoginState.AWAITING_PHONE, LoginState.AWAITING_2FA]:
                 await event.respond("Please send a text message for this step.")
            return

        try:
            if state.state == LoginState.AWAITING_PHONE:
                await self.handle_phone_number(event, state, text_message)
            
            elif state.state == LoginState.AWAITING_2FA:
                await self.handle_2fa_password(event, state, text_message)

        except Exception as e:
            logger.error(f"Unexpected error in message handler for user {user_id}: {e}")
            try:
                await event.respond("An unexpected error occurred. Please try again with /add")
            except: pass
            await self.cleanup_user_state(user_id)

    async def handle_2fa_password(self, event, state: UserState, password: str):
        """Handle 2FA password submission from a text message."""
        state.state = LoginState.PROCESSING_2FA
        try:
            if state.last_message_id:
                try: await self.bot.delete_messages(event.chat_id, state.last_message_id)
                except: pass
                state.last_message_id = None

            await state.client.sign_in(password=password.strip())
            
            await self.complete_login_flow(event, state)

        except errors.PasswordHashInvalidError:
            state.state = LoginState.AWAITING_2FA
            if state.increment_attempts() >= 3:
                await self.cleanup_user_state(event.sender_id)
                await event.respond(
                    "❌ Too many invalid password attempts.\n"
                    "Please start over with /add"
                )
                return
            
            msg = await event.respond(
                "❌ Invalid password. Please try again.\n\n"
                "💡 The password is case-sensitive.\n"
                "Use /cancel to abort this operation."
            )
            state.last_message_id = msg.id
        
        except Exception as e:
            logger.error(f"Error in 2FA password processing for user {event.sender_id}: {e}")
            await self.cleanup_user_state(event.sender_id)
            await event.respond(
                "❌ An error occurred during 2FA verification.\n"
                "Please try again with /add"
            )

    async def complete_login_flow(self, event, state: UserState):
        """Complete the login flow after successful authentication."""
        owner_id = event.sender_id
        account_phone_number = state.phone
        try:
            session_string = state.client.session.save()
            
            async with self.session_manager.db.get_session() as db_session:
                stmt = select(UserSession).where(
                    UserSession.user_id == owner_id,
                    UserSession.phone_number == account_phone_number
                )
                result = await db_session.execute(stmt)
                specific_account_session = result.scalar_one_or_none()
                
                if specific_account_session:
                    specific_account_session.session_string = session_string
                    logger.info(f"Updated session for account {account_phone_number} owned by user {owner_id}")
                else:
                    user_session_db_entry = UserSession(
                        user_id=owner_id,
                        phone_number=account_phone_number,
                        session_string=session_string
                    )
                    db_session.add(user_session_db_entry)
                    logger.info(f"Saved new session for account {account_phone_number} owned by user {owner_id}")
                
                await db_session.commit()

            self.session_manager.active_clients[owner_id] = state.client
            logger.info(f"Client for account {account_phone_number} (owner: {owner_id}) is now active.")

            await self.plugin_loader.init_plugins(state.client, owner_id)
            await state.cleanup_messages(self.bot)
            
            success_message = (
                f"✅ Login successful for {account_phone_number}! Your userbot is now active.\n\n"
                "Your session has been securely saved and will be automatically "
                "restored when needed.\n\n"
                "You can now use all available commands for this account."
            )
            try:
                await event.respond(success_message)
            except AttributeError:
                 await self.bot.send_message(event.chat_id, success_message)
            except Exception as e:
                logger.warning(f"Could not respond to event for success message, sending directly: {e}")
                await self.bot.send_message(event.chat_id, success_message)

            await self.cleanup_user_state(owner_id)

        except Exception as e:
            logger.error(f"Error completing login flow for account {account_phone_number}, user {owner_id}: {e}")
            logger.error(traceback.format_exc())
            try:
                await event.respond(
                    "An error occurred while saving your session.\n"
                    "Please try again with /add"
                )
            except:
                await self.bot.send_message(event.chat_id, "An error occurred while saving your session. Please try again with /add")
            await self.cleanup_user_state(owner_id)

    @ensure_registered
    async def handle_add_account(self, event):
        """Handle /add command to start the account addition process."""
        user_id = event.sender_id
        
        if user_id in self.pending_logins:
            await event.respond(
                "You already have an ongoing login process.\n"
                "Please complete it or use /cancel to start over."
            )
            return

        self.pending_logins[user_id] = UserState(LoginState.AWAITING_PHONE)
        await event.respond(
            "Please send your phone number in international format.\n"
            "Example: +1234567890\n\n"
            "Use /cancel to abort this operation."
        )

    async def handle_phone_number(self, event, state: UserState, phone: str):
        """Handle phone number submission."""
        user_id = event.sender_id
        normalized_phone = phone.strip()

        if not self.validate_phone_number(normalized_phone):
            if state.increment_attempts() >= 3:
                await self.cleanup_user_state(user_id)
                await event.respond(
                    "Too many invalid attempts. Please start over with /add"
                )
                return
            await event.respond(
                "Invalid phone number format.\n"
                "Please send your phone number in international format (e.g., +1234567890).\n"
                "Use /cancel to abort this operation."
            )
            return

        try:
            async for db_sess in self.session_manager.db.get_session():
                stmt = select(UserSession).where(UserSession.phone_number == normalized_phone)
                result = await db_sess.execute(stmt)
                existing_db_session = result.scalar_one_or_none()
                if existing_db_session:
                    logger.info(f"Attempt to add already existing phone number: {normalized_phone} by user {user_id}")
                    await event.respond(
                        f"⚠️ The account for {normalized_phone} is already added.\n"
                        "Use a different phone number, or manage accounts via /my_accounts (and /logout if implemented)."
                    )
                    await self.cleanup_user_state(user_id)
                    return
        except Exception as db_error:
            logger.error(f"Database error checking phone number {normalized_phone}: {db_error}")
            await event.respond("A database error occurred. Please try again later.")
            await self.cleanup_user_state(user_id)
            return

        try:
            client = await self.session_manager.create_client(normalized_phone, user_id)
            state.client = client
            state.phone = normalized_phone
            state.state = LoginState.AWAITING_CODE
            state.reset_attempts()
            
            msg = await event.respond(
                self.get_code_message([]),
                buttons=self.get_code_keyboard("")
            )
            state.code_message_id = msg.id
            state.last_message_id = msg.id

        except ValueError as ve:
            logger.warning(f"Error creating client for {normalized_phone} by {user_id}: {ve}")
            await event.respond(str(ve))
            await self.cleanup_user_state(user_id)
        except Exception as e:
            logger.error(f"General error creating client for {normalized_phone} by {user_id}: {e}")
            await event.respond(
                f"Failed to initiate login for {normalized_phone}. An unexpected error occurred.\n"
                "Please try again with /add"
            )
            await self.cleanup_user_state(user_id)

    def validate_phone_number(self, phone: str) -> bool:
        """Validate phone number format."""
        if not phone:
            return False
        return bool(self.phone_regex.match(phone.strip()))

    async def cleanup_user_state(self, user_id: int):
        """Clean up user state and resources."""
        if user_id in self.pending_logins:
            state = self.pending_logins[user_id]
            if state.client:
                try:
                    await state.client.disconnect()
                except Exception as e:
                    logger.error(f"Error disconnecting client: {e}")
            del self.pending_logins[user_id]

    async def handle_cancel(self, event):
        """Handle /cancel command to abort ongoing operations."""
        user_id = event.sender_id
        if user_id in self.pending_logins:
            state = self.pending_logins[user_id]
            if state.code_message_id:
                try:
                    await self.bot.edit_message(
                        event.chat_id,
                        state.code_message_id,
                        "Operation cancelled.",
                        buttons=None
                    )
                except:
                    pass
            
            await self.cleanup_user_state(user_id)
            await event.respond("Operation cancelled. You can start again with /add")
        else:
            await event.respond("No ongoing operation to cancel.")

    async def stop(self):
        """Stop the bot and clean up resources."""
        for user_id in list(self.session_manager.active_clients.keys()):
            await self.session_manager.disconnect_client(user_id)
        
        for user_id in list(self.pending_logins.keys()):
            await self.cleanup_user_state(user_id)
        
        await self.bot.disconnect()

    @ensure_registered
    async def handle_set_report_message(self, event):
        """Handle /set_report_message <message> command."""
        owner_id = event.sender_id
        try:
            message_text = event.pattern_match.group(1).strip()
            if not message_text:
                await event.respond("Please provide a message. Usage: /set_report_message <your report message>")
                return

            async with self.session_manager.db.get_session() as db_sess:
                stmt = select(ReportSetting).where(ReportSetting.user_id == owner_id)
                result = await db_sess.execute(stmt)
                setting = result.scalar_one_or_none()

                if setting:
                    setting.report_message = message_text
                    logger.info(f"Updated report message for user {owner_id}")
                else:
                    setting = ReportSetting(user_id=owner_id, report_message=message_text)
                    db_sess.add(setting)
                    logger.info(f"Set new report message for user {owner_id}")
                
                await db_sess.commit()
            
            await event.respond(f"✅ Default report message set to: \n`{message_text}`")

        except Exception as e:
            logger.error(f"Error in /set_report_message for user {owner_id}: {e}")
            logger.error(traceback.format_exc())
            await event.respond("An error occurred while setting the report message. Please try again.\nIf the error persists, it might be an issue with the database session handling.")

    @ensure_registered
    async def handle_report_target(self, event):
        """Handle /report <target> <reason> command."""
        owner_id = event.sender_id
        try:
            target_entity_str = event.pattern_match.group(1).strip()
            reason_alias = event.pattern_match.group(2).strip().lower()

            if not target_entity_str or not reason_alias:
                await event.respond("Usage: /report <@username_or_id_or_link> <reason_alias>")
                return

            report_reason = self.report_reason_map.get(reason_alias)
            if not report_reason:
                valid_reasons = ", ".join(self.report_reason_map.keys())
                await event.respond(f"Invalid reason alias: `{reason_alias}`. Valid reasons are: {valid_reasons}")
                return

            default_message = None
            async with self.session_manager.db.get_session() as db_sess:
                stmt = select(ReportSetting.report_message).where(ReportSetting.user_id == owner_id)
                result = await db_sess.execute(stmt)
                default_message = result.scalar_one_or_none()

            if not default_message:
                await event.respond("❌ No default report message set. Please set one using: /set_report_message <message>")
                return
            
            user_sessions = []
            async with self.session_manager.db.get_session() as db_sess:
                stmt = select(UserSession).where(UserSession.user_id == owner_id, UserSession.is_active == True)
                result = await db_sess.execute(stmt)
                user_sessions = result.scalars().all()

            if not user_sessions:
                await event.respond("You have no active accounts to report with. Add one using /add.")
                return

            await event.respond(f"Starting report process for `{target_entity_str}` with {len(user_sessions)} account(s)... This may take a moment.")
            
            success_reports = 0
            failed_reports = 0
            failed_accounts_details = []

            for session_info in user_sessions:
                temp_client = TelegramClient(
                    StringSession(session_info.session_string),
                    self.api_id,
                    self.api_hash
                )
                try:
                    async with temp_client:
                        await temp_client.connect()
                        if not await temp_client.is_user_authorized():
                            logger.warning(f"Session for {session_info.phone_number} is not authorized. Skipping.")
                            failed_reports += 1
                            failed_accounts_details.append(f"{session_info.phone_number} (Not Authorized)")
                            continue
                        
                        target_peer = await temp_client.get_input_entity(target_entity_str)
                        await temp_client(ReportPeerRequest(
                            peer=target_peer,
                            reason=report_reason,
                            message=default_message
                        ))
                        logger.info(f"Report sent for {target_entity_str} from account {session_info.phone_number} by owner {owner_id}")
                        success_reports += 1
                except Exception as report_err:
                    logger.error(f"Failed to report from {session_info.phone_number} for owner {owner_id}: {report_err}")
                    failed_reports += 1
                    failed_accounts_details.append(f"{session_info.phone_number} ({type(report_err).__name__})")
                finally:
                    if temp_client.is_connected():
                        await temp_client.disconnect()
            
            summary_message = f"📣 Report Summary for `{target_entity_str}`:\n"
            summary_message += f"✅ Successful reports: {success_reports}\n"
            summary_message += f"❌ Failed reports: {failed_reports}"
            if failed_accounts_details:
                summary_message += "\nFailed accounts:\n- " + "\n- ".join(failed_accounts_details)
            
            await event.respond(summary_message)

        except Exception as e:
            logger.error(f"Error in /report for user {owner_id}: {e}")
            await event.respond("An unexpected error occurred while processing the report command.")
