import html
import logging

import telebot

from private_bot_manager import PrivateBotError

logger = logging.getLogger(__name__)


class PrivateBotHandler:
    STATE_WAIT_TOKEN = "private_bot_waiting_token"

    def __init__(self, bot, db, language, config, manager=None, is_private_instance=False):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.manager = manager
        self.is_private_instance = is_private_instance
        self._register()

    def _register(self):
        @self.bot.callback_query_handler(func=lambda call: call.data == "menu_private_bot")
        def open_private_bot(call):
            self.show_panel(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "private_bot_connect")
        def connect(call):
            self._prompt_token(call, replace=False)

        @self.bot.callback_query_handler(func=lambda call: call.data == "private_bot_replace")
        def replace(call):
            self._prompt_token(call, replace=True)

        @self.bot.callback_query_handler(func=lambda call: call.data == "private_bot_disconnect")
        def disconnect(call):
            self._disconnect(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "private_bot_disconnect_confirm")
        def disconnect_confirm(call):
            self._disconnect_confirm(call)

        @self.bot.callback_query_handler(func=lambda call: call.data == "private_bot_back")
        def back(call):
            try:
                self.db.clear_user_state(call.from_user.id)
            except Exception:
                pass
            try:
                self.bot.answer_callback_query(call.id)
            except Exception:
                pass
            call.data = "main_menu"
            # This callback is registered before the main router; sending a new menu is safer
            # than trying to redispatch the same callback through pyTelegramBotAPI.
            user = self.db.get_or_create_user(call.from_user.id)
            lang = user.get("language_code", "ro") if user else "ro"
            markup = telebot.types.InlineKeyboardMarkup()
            buttons = self.language.get_main_menu_buttons(lang, call.from_user.id, None)
            for row in buttons:
                markup.row(*[
                    telebot.types.InlineKeyboardButton(text=b["text"], callback_data=b["callback_data"])
                    for b in row
                ])
            self.bot.send_message(call.message.chat.id, "🏠 <b>Meniu Principal</b>", parse_mode="HTML", reply_markup=markup)

        @self.bot.message_handler(func=self._is_waiting_token, content_types=["text"])
        def receive_token(message):
            self._receive_token(message)

    def _is_waiting_token(self, message):
        if (getattr(message, "text", None) or "").startswith("/"):
            return False
        try:
            state = self.db.get_user_state(message.from_user.id)
            if not state:
                return False
            if isinstance(state, dict):
                return state.get("state") == self.STATE_WAIT_TOKEN
            return str(state) == self.STATE_WAIT_TOKEN
        except Exception:
            return False

    def show_panel(self, call):
        try:
            self.db.clear_user_state(call.from_user.id)
        except Exception:
            pass
        if self.is_private_instance or self.manager is None:
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🔙 Înapoi", callback_data="main_menu"))
            self.bot.send_message(
                call.message.chat.id,
                "🔐 <b>Botul personal se administrează din botul principal.</b>",
                parse_mode="HTML",
                reply_markup=markup,
            )
            try:
                self.bot.answer_callback_query(call.id)
            except Exception:
                pass
            return

        record = self.manager.status(call.from_user.id)
        markup = telebot.types.InlineKeyboardMarkup()
        if record:
            text = (
                "🔐 <b>Botul tău personal</b>\n\n"
                f"🤖 <b>Bot:</b> @{html.escape(record.bot_username)}\n"
                f"🟢 <b>Status:</b> {html.escape(record.status)}\n\n"
                "Folosește aceeași bază de date, balanță, produse și comenzi ca botul principal."
            )
            markup.row(
                telebot.types.InlineKeyboardButton("🤖 Deschide botul", url=f"https://t.me/{record.bot_username}"),
            )
            markup.row(
                telebot.types.InlineKeyboardButton("🔑 Schimbă tokenul", callback_data="private_bot_replace"),
                telebot.types.InlineKeyboardButton("🗑 Deconectează", callback_data="private_bot_disconnect"),
            )
        else:
            text = (
                "🔐 <b>Creează un bot personal</b>\n\n"
                "1️⃣ Deschide @BotFather.\n"
                "2️⃣ Trimite <code>/newbot</code>.\n"
                "3️⃣ Alege numele și username-ul botului.\n"
                "4️⃣ BotFather îți va trimite un token.\n"
                "5️⃣ Apasă butonul de mai jos și trimite tokenul aici.\n\n"
                "🔒 Tokenul este verificat la Telegram, mesajul cu tokenul este șters, "
                "iar tokenul este salvat criptat pe server."
            )
            markup.add(telebot.types.InlineKeyboardButton("➕ Conectează botul", callback_data="private_bot_connect"))
        markup.add(telebot.types.InlineKeyboardButton("🔙 Înapoi", callback_data="private_bot_back"))
        self.bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=markup)
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass

    def _prompt_token(self, call, replace=False):
        if self.manager is None:
            self.bot.answer_callback_query(call.id, "Disponibil doar în botul principal.", show_alert=True)
            return
        self.db.set_user_state(
            call.from_user.id,
            self.STATE_WAIT_TOKEN,
            {"replace": bool(replace)},
        )
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("❌ Anulează", callback_data="menu_private_bot"))
        self.bot.send_message(
            call.message.chat.id,
            "🔑 <b>Trimite acum tokenul primit de la @BotFather.</b>\n\n"
            "Exemplu format: <code>123456789:AA...</code>\n\n"
            "Nu trimite alt text împreună cu tokenul.",
            parse_mode="HTML",
            reply_markup=markup,
        )
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass

    def _receive_token(self, message):
        token = (message.text or "").strip()
        try:
            # Best effort removal of the sensitive token from Telegram chat.
            try:
                self.bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass

            record = self.manager.connect_bot(message.from_user.id, token)
            self.db.clear_user_state(message.from_user.id)
            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton("🤖 Deschide botul", url=f"https://t.me/{record.bot_username}"))
            markup.add(telebot.types.InlineKeyboardButton("🔙 Înapoi", callback_data="menu_private_bot"))
            self.bot.send_message(
                message.chat.id,
                "✅ <b>Bot conectat!</b>\n\n"
                f"🤖 @{html.escape(record.bot_username)}\n\n"
                "Deschide botul și trimite <code>/start</code>. Vei avea același cont și aceleași date.",
                parse_mode="HTML",
                reply_markup=markup,
            )
        except PrivateBotError as exc:
            self.bot.send_message(
                message.chat.id,
                f"❌ <b>Nu am putut conecta botul.</b>\n\n{html.escape(str(exc))}\n\n"
                "Trimite din nou un token valid sau apasă Înapoi.",
                parse_mode="HTML",
            )
        except Exception:
            logger.exception("Private bot connection failed for user %s", message.from_user.id)
            self.bot.send_message(message.chat.id, "❌ A apărut o eroare internă la conectarea botului.")

    def _disconnect(self, call):
        if self.manager is None or not self.manager.status(call.from_user.id):
            self.bot.answer_callback_query(call.id, "Nu ai niciun bot conectat.", show_alert=True)
            return
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("✅ Da, deconectează", callback_data="private_bot_disconnect_confirm"),
            telebot.types.InlineKeyboardButton("❌ Nu", callback_data="menu_private_bot"),
        )
        self.bot.send_message(
            call.message.chat.id,
            "⚠️ <b>Deconectezi botul personal?</b>\n\nBotul Telegram rămâne al tău în BotFather, dar nu va mai folosi sistemul nostru.",
            parse_mode="HTML",
            reply_markup=markup,
        )
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass

    def _disconnect_confirm(self, call):
        try:
            self.manager.disconnect_bot(call.from_user.id)
            self.db.clear_user_state(call.from_user.id)
            self.bot.send_message(call.message.chat.id, "✅ Botul personal a fost deconectat.")
        except Exception:
            logger.exception("Private bot disconnect failed")
            self.bot.send_message(call.message.chat.id, "❌ Nu am putut deconecta botul.")
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass
