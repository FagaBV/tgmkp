import telebot
import sqlite3
import logging
import json
import os
import threading
import time
from performance_optimizations import handler_operation
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class AdminHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.category_handler = None  # Will be set later
        self.product_handler = None  # Will be set later
        self.currency_handler = None  # Will be set later
        self.payment_handler = None  # Will be set later
        
    def load_store_images(self):
        try:
            with open('store_images.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}

    def send_page_with_image(self, chat_id, page_key, text, markup=None):
        images = self.load_store_images()
        image_file_id = images.get(page_key)

        if image_file_id:
            self.bot.send_photo(
                chat_id=chat_id,
                photo=image_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        else:
            self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def handle_admin_panel(self, call):
        """Handle admin panel callback"""
        user_id = call.from_user.id
        self.db.clear_user_state(user_id)
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get admin panel welcome message
        welcome_text = self.language.get_text('admin_panel_welcome', lang_code)
        
        # Create admin menu buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add admin action buttons with dynamic currency button
        admin_buttons = self.language.get_admin_buttons(lang_code)
        for button_row in admin_buttons:
            row_buttons = []
            for btn in button_row:
                button_text = btn['text']
                callback_data = btn['callback_data']
                
                # If it's the currency button, add current currency symbol
                if callback_data == 'admin_currency_settings':
                    current_currency = self.config.get('currency', {'symbol': '$'})
                    button_text = f"{button_text}: {current_currency['symbol']}"
                
                row_buttons.append(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=callback_data
                ))
            markup.row(*row_buttons)
        
        # Add back to main menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Show admin panel with optional image
        try:
            self.send_page_with_image(
                call.message.chat.id,
                "admin_panel",
                welcome_text,
                markup
            )
        except Exception as e:
            logger.error(f"Error showing admin panel with image: {e}")
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_admin_panel_from_message(self, message):
        """Handle /amenu command"""

        user_id = message.from_user.id

        # Verificăm dacă utilizatorul este admin
        if not self.db.is_admin(
            user_id,
            self.config['admin_ids']
        ):
            self.bot.send_message(
                message.chat.id,
                "❌ Access denied! Admin only."
            )
            return

        # Oprim orice state activ
        self.db.clear_user_state(user_id)

        # Luăm utilizatorul și limba
        user = self.db.get_or_create_user(user_id)

        if not user:
            self.bot.send_message(
                message.chat.id,
                "❌ Database error. Please try again."
            )
            return

        lang_code = user['language_code']

        # Textul panoului
        welcome_text = self.language.get_text(
            'admin_panel_welcome',
            lang_code
        )

        # Construim meniul admin
        markup = telebot.types.InlineKeyboardMarkup()

        admin_buttons = self.language.get_admin_buttons(
            lang_code
        )

        for button_row in admin_buttons:

            row_buttons = []

            for btn in button_row:

                button_text = btn['text']
                callback_data = btn['callback_data']

                # Currency button
                if callback_data == 'admin_currency_settings':

                    current_currency = self.config.get(
                        'currency',
                        {'symbol': '$'}
                    )

                    button_text = (
                        f"{button_text}: "
                        f"{current_currency['symbol']}"
                    )

                row_buttons.append(
                    telebot.types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=callback_data
                    )
                )

            if row_buttons:
                markup.row(*row_buttons)

        # Buton înapoi la meniul principal
        back_text = self.language.get_text(
            'back_to_menu',
            lang_code
        )

        markup.add(
            telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            )
        )

        # Afișăm panoul
        try:

            self.send_page_with_image(
                message.chat.id,
                "admin_panel",
                welcome_text,
                markup
            )

        except Exception as e:

            logger.error(
                f"Error showing admin panel from /amenu: {e}"
            )

            # Fallback fără imagine
            self.bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode='HTML',
                reply_markup=markup
            )
    
    def handle_admin_buttons(self, call):
        """Handle admin button clicks with new ID-based system"""
        user_id = call.from_user.id
        
        print("ADMIN CALLBACK:", call.data)
     
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract button ID from callback data
        button_id = call.data
        
        # Handle different admin options based on ID
        if button_id == 'admin_broadcast':
            self.show_broadcast_menu(call)
            return
        elif button_id == 'admin_broadcast_text':
            self.start_broadcast_text(call)
            return
        elif button_id == 'admin_broadcast_photo':
            self.start_broadcast_photo(call)
            return
        elif button_id == 'admin_broadcast_cancel':
            self.db.clear_user_state(user_id)
            try:
                self.bot.answer_callback_query(call.id, 'Broadcast anulat.')
            except Exception:
                pass
            self.handle_admin_panel(call)
            return
        elif button_id == 'admin_broadcast_confirm':
            self.confirm_broadcast(call)
            return
        elif button_id in ['store_settings', 'admin_store_settings']:
            self.show_store_settings_menu(call, lang_code)
            return
        elif button_id in ['categories', 'admin_categories']:
            # Call the category handler directly 
            if self.category_handler:
                self.category_handler.handle_categories_management(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Category handler not available")
            return
        elif button_id in ['products', 'admin_products']:
            # Products are handled by the product handler
            if self.product_handler:
                self.product_handler.handle_products_management(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Product handler not available")
            return
        elif button_id in ['cashout_requests', 'admin_cashout_requests']:
            self.show_pending_cashouts(call)
            return    
        elif button_id in [
            'crypto_cashout_requests',
            'admin_crypto_cashout_requests'
        ]:
            self.show_pending_crypto_cashouts(call)
            return
        elif button_id in ['admin_order_management', 'order_management']:
            # Order management is handled by the order management handler
            if hasattr(self, 'order_management_handler') and self.order_management_handler:
                self.order_management_handler.handle_order_management(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Order management handler not available")
            return
        elif button_id in [
            'admin_dispute_view',
            'admin_disputes',
            'admin_admin_disputes',
            'disputes'
        ]:
            # Dispute management is handled by the dispute handler
            if hasattr(self, 'dispute_handler') and self.dispute_handler:
                self.dispute_handler.show_admin_disputes(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Dispute handler not available")
            return
        elif button_id in ['edit_buttons', 'admin_edit_buttons']:
            # Button editor is handled by the button editor handler
            if hasattr(self, 'button_editor_handler') and self.button_editor_handler:
                self.button_editor_handler.handle_export_buttons(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Button editor not available")
            return
        elif button_id in ['currency_settings', 'admin_currency_settings']:
            # Currency settings are handled by the currency handler
            if self.currency_handler:
                self.currency_handler.handle_currency_settings(call)
            else:
                self.bot.answer_callback_query(call.id, "❌ Currency handler not available")
            return
        elif button_id in ['language_settings', 'admin_language_settings']:
            response_text = f"🌐 <b>Language Settings</b>\n\n🔤 <i>Manage bot languages</i>\n\n<b>Available Languages:</b>\n• 🇺🇸 English (Active)\n• 🇪🇸 Español (Active)\n• 🇫🇷 Français (Active)\n• 🇩🇪 Deutsch (Active)\n\n<b>Language Management:</b>\n• ➕ Add new languages\n• ✏️ Edit translations\n• 🔧 Set default language\n• 📊 Usage statistics\n\n<i>Advanced language management coming soon!</i>"
            
            # Add Coming Soon button
            markup = telebot.types.InlineKeyboardMarkup()
            coming_soon_text = self.language.get_text('coming_soon', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=coming_soon_text,
                callback_data='coming_soon_feature'
            ))
            
            # Add back buttons
            back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_admin_text,
                callback_data='admin_panel'
            ))
            
            back_text = self.language.get_text('back_to_menu', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            # Edit the message
            try:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=response_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=response_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            
            # Answer callback query
            self.bot.answer_callback_query(call.id)
            return
        elif button_id in [
            'admin_user_management',
            'user_management'
        ]:

            text = (
                "👥 <b>Gestionare Utilizatori</b>\n\n"
                "🔍 Caută utilizator după Telegram ID"
            )

            markup = telebot.types.InlineKeyboardMarkup()

            markup.add(
                telebot.types.InlineKeyboardButton(
                    text="🔍 Cauta Utilizator",
                    callback_data="admin_search_user"
                )
            )

            markup.add(
                telebot.types.InlineKeyboardButton(
                    text="🔙 Înapoi",
                    callback_data="admin_panel"
                )
            )

            

            self.bot.send_message(
                call.message.chat.id,
                text,
                parse_mode='HTML',
                reply_markup=markup
            )
            return        
        elif button_id == 'admin_search_user':

            self.db.set_user_state(
                user_id,
                'admin_search_user'
            )

            

            self.bot.send_message(
                call.message.chat.id,
                "🆔 Introdu Telegram ID:"
            )
            return

        elif button_id.startswith('admin_user_warn_menu_'):

            target_id = int(
                button_id.replace(
                    'admin_user_warn_menu_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT warnings
                FROM users
                WHERE user_id = ?
                """,
                (target_id,)
            )

            warnings = int(
                cursor.fetchone()[0]
            )

            conn.close()

            text = (
                f"⚠️ <b>Gestionare Warning-uri</b>\n\n"
                f"Warn actual: {warnings}/3"
            )

            markup = telebot.types.InlineKeyboardMarkup()

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="➕ Adaugă",
                    callback_data=f"admin_user_warn_add_{target_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    text="➖ Elimină",
                    callback_data=f"admin_user_warn_remove_{target_id}"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="♻️ Reset",
                    callback_data=f"admin_user_warn_reset_{target_id}"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                parse_mode='HTML',
                reply_markup=markup
            )

            return    
            
        elif button_id.startswith(
            'admin_user_warn_add_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_user_warn_add_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE users
                SET warnings = warnings + 1
                WHERE user_id = ?
                """,
                (target_id,)
            )

            conn.commit()

            cursor.execute(
                """
                SELECT warnings
                FROM users
                WHERE user_id = ?
                """,
                (target_id,)
            )

            warnings = cursor.fetchone()[0]

            if warnings >= 3:

                cursor.execute(
                    """
                    UPDATE users
                    SET is_banned = 1
                    WHERE user_id = ?
                    """,
                    (target_id,)
                )

                conn.commit()

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                f"⚠️ Warning: {warnings}/3"
            )

            return

        elif button_id.startswith(
            'admin_user_warn_remove_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_user_warn_remove_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE users
                SET warnings =
                CASE
                    WHEN warnings > 0
                    THEN warnings - 1
                    ELSE 0
                END
                WHERE user_id = ?
                """,
                (target_id,)
            )

            conn.commit()

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                "➖ Warning eliminat"
            )

            return

        elif button_id.startswith(
            'admin_user_warn_reset_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_user_warn_reset_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE users
                SET warnings = 0
                WHERE user_id = ?
                """,
                (target_id,)
            )

            conn.commit()

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                "♻️ Warning-uri resetate"
            )

            return

        elif button_id.startswith('admin_user_ban_'):

            target_id = int(
                button_id.replace(
                    'admin_user_ban_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT is_banned
                FROM users
                WHERE user_id = ?
                """,
                (target_id,)
            )

            current = int(
                cursor.fetchone()[0]
            )

            new_value = 0 if current else 1

            cursor.execute(
                """
                UPDATE users
                SET is_banned = ?
                WHERE user_id = ?
                """,
                (
                    new_value,
                    target_id
                )
            )

            conn.commit()
            conn.close()

            self.bot.answer_callback_query(
                call.id,
                "🚫 Ban actualizat"
            )

            return

        elif button_id.startswith('admin_user_orders_'):

            target_id = int(
                button_id.replace(
                    'admin_user_orders_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    total_cost,
                    order_date
                FROM selling_history
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (target_id,)
            )

            rows = cursor.fetchall()

            conn.close()

            markup = telebot.types.InlineKeyboardMarkup()

            if not rows:

                self.bot.send_message(
                    call.message.chat.id,
                    "📦 Nu există comenzi.",
                    parse_mode='HTML'
                )

            else:

                for row in rows:

                    order_id = row[0]
                    total = row[1]

                    markup.add(
                        telebot.types.InlineKeyboardButton(
                            text=f"📦 #{order_id} | {total} RON",
                            callback_data=f"admin_view_order_{order_id}"
                        )
                    )

                self.bot.send_message(
                    call.message.chat.id,
                    "📦 <b>Comenzile utilizatorului</b>",
                    parse_mode='HTML',
                    reply_markup=markup
                )

            return

        elif button_id.startswith('admin_user_tickets_'):

            target_id = int(
                button_id.replace(
                    'admin_user_tickets_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    status
                FROM disputes
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 20
                """,
                (target_id,)
            )

            rows = cursor.fetchall()

            conn.close()

            markup = telebot.types.InlineKeyboardMarkup()

            if not rows:

                self.bot.send_message(
                    call.message.chat.id,
                    "🎫 Nu există tichete.",
                    parse_mode='HTML'
                )

            else:

                for row in rows:

                    ticket_id = row[0]
                    status = row[1]

                    markup.add(
                        telebot.types.InlineKeyboardButton(
                            text=f"🎫 #{ticket_id} | {status}",
                            callback_data=f"admin_view_ticket_{ticket_id}"
                        )
                    )

                self.bot.send_message(
                    call.message.chat.id,
                    "🎫 <b>Tichetele utilizatorului</b>",
                    parse_mode='HTML',
                    reply_markup=markup
                )

            return            

        elif button_id.startswith('admin_view_ticket_'):

            dispute_id = int(
                button_id.replace(
                    'admin_view_ticket_',
                    ''
                )
            )

            if self.dispute_handler:

                self.dispute_handler.show_admin_dispute_full(
                    call,
                    dispute_id
                )

            return

        elif button_id.startswith('admin_view_order_'):

            order_id = int(
                button_id.replace(
                    'admin_view_order_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id,
                    products,
                    total_cost,
                    order_date,
                    review
                FROM selling_history
                WHERE id = ?
                """,
                (order_id,)
            )

            row = cursor.fetchone()

            conn.close()
            
            product_text = ""

            try:

                products = json.loads(
                    row[1]
                )

                for p in products:

                    name = p.get(
                        'name',
                        'Unknown'
                    )

                    qty = p.get(
                        'quantity',
                        1
                    )

                    total = p.get(
                        'total_price',
                        0
                    )

                    product_text += (
                        f"• {name}\n"
                        f"  Cantitate: {qty}\n"
                        f"  Total: {total} RON\n\n"
                    )

            except Exception as e:

                print(
                    f"JSON ERROR: {e}"
                )

                product_text = str(
                    row[1]
                )

            if not row:

                self.bot.answer_callback_query(
                    call.id,
                    "❌ Comanda nu există"
                )

                return

            text = (
                f"📦 <b>Comanda #{row[0]}</b>\n\n"
                f"💰 <b>Total:</b> {row[2]} RON\n"
                f"📅 <b>Data:</b> {row[3]}\n\n"
                f"📋 <b>Produse:</b>\n{product_text}"
            )

            if row[4]:

                text += (
                    f"\n\n⭐ <b>Review:</b>\n"
                    f"{row[4]}"
                )

            self.bot.send_message(
                call.message.chat.id,
                text,
                parse_mode='HTML'
            )

            return
        
        elif button_id.startswith(
            'admin_user_balance_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_user_balance_',
                    ''
                )
            )

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT balance
                FROM users
                WHERE user_id = ?
                """,
                (target_id,)
            )

            balance = float(
                cursor.fetchone()[0] or 0
            )

           

            conn.close()

            text = (
                f"💰 <b>Gestionare Balanță</b>\n\n"
                f"Balanță actuală: "
                f"{balance:.2f} RON"
            )

            markup = telebot.types.InlineKeyboardMarkup()

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="➕ Adaugă",
                    callback_data=f"admin_balance_add_{target_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    text="➖ Scade",
                    callback_data=f"admin_balance_remove_{target_id}"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="✏️ Setează",
                    callback_data=f"admin_balance_set_{target_id}"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                parse_mode='HTML',
                reply_markup=markup
            )

            return

        elif button_id.startswith(
            'admin_balance_add_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_balance_add_',
                    ''
                )
            )

            self.db.set_user_state(
                user_id,
                'admin_balance_add',
                str(target_id)
            )

            self.bot.send_message(
                call.message.chat.id,
                "➕ Introdu suma:"
            )

            return

        elif button_id.startswith(
            'admin_balance_remove_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_balance_remove_',
                    ''
                )
            )

            self.db.set_user_state(
                user_id,
                'admin_balance_remove',
                str(target_id)
            )

            self.bot.send_message(
                call.message.chat.id,
                "➖ Introdu suma:"
            )

            return

        elif button_id.startswith(
            'admin_balance_set_'
        ):

            target_id = int(
                button_id.replace(
                    'admin_balance_set_',
                    ''
                )
            )

            self.db.set_user_state(
                user_id,
                'admin_balance_set',
                str(target_id)
            )

            self.bot.send_message(
                call.message.chat.id,
                "✏️ Introdu noua balanță:"
            )

            return

        elif button_id in ['statistics', 'admin_statistics']:
            # Show upgrade alert instead of statistics
            upgrade_alert_text = self.language.get_text('upgrade_bot_alert', lang_code)
            self.bot.answer_callback_query(call.id, upgrade_alert_text, show_alert=True)
            return
        elif button_id in ['setup_payment', 'admin_setup_payment']:
            # Legacy OxaPay button from an old Telegram message: return safely.
            self.handle_admin_panel(call)
            return
        elif button_id in ['setup_admin', 'admin_setup_admin']:
            self.show_admin_setup(call, lang_code)
            return
        else:
            response_text = f"🔧 <b>Admin Function</b>\n\nYou selected: {button_id.replace('_', ' ').title()}\n\nThis admin feature will be implemented soon!"
        
        # Add back buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Back to admin panel button
        back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_admin_text,
            callback_data='admin_panel'
        ))
        
        # Back to main menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=response_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=response_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_admin_panel_keyboard(self, message):
        """Handle admin panel keyboard button press"""
        user_id = message.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            
            self.bot.send_message(message.chat.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            
            self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get admin panel welcome message
        welcome_text = self.language.get_text('admin_panel_welcome', lang_code)
        
        # Create admin menu buttons
        import time
        button_creation_start = time.time()
        logger.info(f"🔍 DEBUG: Starting button creation for admin panel at {button_creation_start:.3f}")
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add admin action buttons
        admin_buttons = self.language.get_admin_buttons(lang_code)
        button_loop_start = time.time()
        for button_row in admin_buttons:
            markup.row(*[
                telebot.types.InlineKeyboardButton(
                    text=btn['text'],
                    callback_data=btn['callback_data']
                ) for btn in button_row
            ])
        button_loop_time = time.time() - button_loop_start
        
        # Add back to main menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        button_creation_time = time.time() - button_creation_start
        logger.info(f"🔍 DEBUG: Button creation took {button_creation_time:.3f}s (loop: {button_loop_time:.3f}s)")
        
        # Send admin panel
        import time
        telegram_api_start = time.time()
        logger.info(f"🔍 DEBUG: Starting Telegram API send_message call for admin panel at {telegram_api_start:.3f}")
        
        self.send_page_with_image(
            message.chat.id,
            "admin_panel",
            welcome_text,
            markup
        )
        
        telegram_api_time = time.time() - telegram_api_start
        logger.info(f"🔍 DEBUG: Telegram API send_message call took {telegram_api_time:.3f}s")
    
    def show_pending_cashouts(
        self,
        call
    ):

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                seller_id,
                amount,
                fee,
                amount_after_fee
            FROM cashout_requests
            WHERE status='pending'
            AND method='cash'
            ORDER BY created_at
        """)

        requests = cursor.fetchall()

        conn.close()

        if not requests:

            self.bot.send_message(

                call.message.chat.id,

                "✅ Nu există cereri."

            )

            return

        markup = telebot.types.InlineKeyboardMarkup()

        text = "💸 <b>Cereri Retragere</b>\n\n"

        for row in requests:

            request_id = row[0]

            seller = row[1]

            amount = row[2]

            text += f"""

    #{request_id}

    Seller:

    <code>{seller}</code>

    Sumă:

    {amount:.2f} RON

    """

            markup.add(

                telebot.types.InlineKeyboardButton(

                    f"Deschide #{request_id}",

                    callback_data=f"cashout_view_{request_id}"

                )

            )

        self.bot.send_message(

            call.message.chat.id,

            text,

            parse_mode="HTML",

            reply_markup=markup

        )
        
    def show_pending_crypto_cashouts(
        self,
        call
    ):

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                seller_id,
                amount,
                fee,
                amount_after_fee,
                crypto_amount,
                wallet_address,
                payout_track_id,
                payout_status,
                status
            FROM cashout_requests
            WHERE method='crypto'
            AND status NOT IN (
                'completed',
                'rejected_refunded'
            )
            ORDER BY created_at
        """)

        requests = cursor.fetchall()

        conn.close()

        if not requests:

            self.bot.send_message(
                call.message.chat.id,
                "✅ Nu există retrageri crypto active."
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

            return

        text = "🪙 <b>Cereri Retragere Crypto</b>\n\n"

        markup = telebot.types.InlineKeyboardMarkup()

        for row in requests:

            request_id = row[0]
            seller_id = row[1]
            amount = float(row[2])
            fee = float(row[3])
            receive = float(row[4])
            crypto_amount = float(row[5] or 0)
            wallet_address = row[6] or "-"
            payout_track_id = row[7] or "-"
            payout_status = row[8] or "unknown"
            status = row[9]

            text += (
                f"🆔 <b>#{request_id}</b>\n"
                f"👤 Seller: <code>{seller_id}</code>\n"
                f"💰 Sumă: {amount:.2f} RON\n"
                f"💸 Taxă: {fee:.2f} RON\n"
                f"📤 Net: {receive:.2f} RON\n"
                f"🪙 LTC: {crypto_amount:.8f}\n"
                f"📌 Status: <b>{payout_status}</b>\n\n"
            )

            markup.add(
                telebot.types.InlineKeyboardButton(
                    f"🪙 Deschide #{request_id}",
                    callback_data=f"cashout_crypto_view_{request_id}"
                )
            )

        markup.add(
            telebot.types.InlineKeyboardButton(
                "🔙 Înapoi",
                callback_data="admin_cashout_requests"
            )
        )

        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_store_settings_menu(self, call, lang_code):
        """Show store settings menu"""
        menu_text = "🏪 <b>Modificari Magazin</b>\n\nAlege ce vrei să configurezi:"

        markup = telebot.types.InlineKeyboardMarkup()

        markup.add(telebot.types.InlineKeyboardButton(
            text="🖼 Imagini",
            callback_data='store_tab_images'
        ))

        back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_admin_text,
            callback_data='admin_panel'
        ))

        # Show store settings as a new message
        
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=menu_text,
            reply_markup=markup,
            parse_mode='HTML'
        )

        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def finish_cashout(
        self,
        call,
        request_id
    ):

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                seller_id,
                amount,
                fee,
                amount_after_fee,
                pickup_photo_file_id,
                status
            FROM cashout_requests
            WHERE id=?
        """,(request_id,))

        row = cursor.fetchone()

        if not row:

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                "Cererea nu există."
            )

            return

        seller_id = row[0]
        amount = float(row[1])
        fee = float(row[2])
        receive = float(row[3])
        file_id = row[4]
        status = row[5]

        if status != "waiting_photo":

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                "Mai întâi trebuie încărcată fotografia."
            )

            return

        cursor.execute("""

            SELECT balance

            FROM users

            WHERE user_id=?

        """,(seller_id,))

        balance = float(
            cursor.fetchone()[0]
        )

        balance_before = balance
        balance_after = balance - amount

        cursor.execute("""

            UPDATE users

            SET balance=?

            WHERE user_id=?

        """,(balance_after,seller_id))

        cursor.execute("""

            UPDATE cashout_requests

            SET

                status='completed',

                completed_at=CURRENT_TIMESTAMP,

                completed_by=?

            WHERE id=?

        """,(call.from_user.id,request_id))

        conn.commit()

        conn.close()

        self.db.add_wallet_transaction(

            user_id=seller_id,

            transaction_type="CASHOUT",

            amount=-amount,

            balance_before=balance_before,

            balance_after=balance_after,

            description=f"Cashout #{request_id}",

            reference_id=str(request_id)

        )

        self.db.add_platform_fee(

            "cashout",

            fee

        )

        caption = f"""
    ✅ <b>Retragerea a fost aprobată.</b>

    💰 Retragere:
    {amount:.2f} RON

    💸 Taxă:
    {fee:.2f} RON

    📤 Primești:
    {receive:.2f} RON

    Banii vor fi la poza indicata, foloseste-te de coordonate pentru a putea gasi drop-ul cu banii!
    """

        try:

            self.bot.send_photo(

                seller_id,

                photo=file_id,

                caption=caption,

                parse_mode="HTML"

            )

        except Exception as e:

            logger.error(e)

        self.bot.edit_message_text(

            f"""
    ✅ Cererea #{request_id} a fost finalizată.

    Seller:

    <code>{seller_id}</code>

    Retragere:

    {amount:.2f} RON
    """,

            call.message.chat.id,

            call.message.message_id,

            parse_mode="HTML"

        )

        self.bot.answer_callback_query(

            call.id,

            "Retragerea a fost finalizată."

        )
    
    def show_tab_images_menu(self, call, lang_code):
        """Show tab image settings menu"""
        text = (
            "🖼 <b>Modifica poze</b>\n\n"
            "Alege tab-ul pentru care vrei să setezi poza:"
        )

        markup = telebot.types.InlineKeyboardMarkup(row_width=2)

        buttons = [
            ("🏠 Meniu Principal", "tabimg_main_menu"),
            ("⚙️ Panou Admin", "tabimg_admin_panel"),
            ("🛍 Instant Drop", "tabimg_products_menu"),
            ("🛒 Coș", "tabimg_cart_menu"),
            ("💰 Depozit", "tabimg_topup_menu"),
            ("⭐ Recenzii", "tabimg_reviews_menu"),
            ("⚠️ Probleme", "tabimg_disputes_menu"),
            ("📋 Comenzi Prec.", "tabimg_history_menu"),
        ]

        for text_btn, callback in buttons:
            markup.add(telebot.types.InlineKeyboardButton(
                text=text_btn,
                callback_data=callback
            ))

        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Înapoi la Setări",
            callback_data='admin_store_settings'
        ))

        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing tab images menu: {e}")
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )

        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
        
    def prompt_tab_image_upload(self, call, page_key, page_name):
        """Ask admin to send a photo for a tab"""
        user_id = call.from_user.id
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'ro'

        self.db.set_user_state(
            user_id=user_id,
            state='uploading_tab_image',
            data=json.dumps({
                'lang_code': lang_code,
                'page_key': page_key,
                'page_name': page_name
            })
        )

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Înapoi",
            callback_data='store_tab_images'
        ))

        
        self.bot.send_message(
            call.message.chat.id,
            f"🖼 Trimite acum poza pentru: <b>{page_name}</b>",
            reply_markup=markup,
            parse_mode='HTML'
        )

        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass

    def save_tab_image(self, page_key, file_id):
        """Save tab image file_id to store_images.json"""
        data = self.load_store_images()
        data[page_key] = file_id

        with open('store_images.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)    
    
    def handle_store_edit_buttons(self, call):
        """Handle store edit button clicks"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        logger.info(f"User language code: {lang_code}")
        
        # Extract edit type from callback data
        edit_type = call.data.replace('store_edit_', '')
        logger.info(f"Edit type: {edit_type}")
        
        # Show edit prompt based on type
        if edit_type == 'welcome':
            self.show_edit_prompt(call, lang_code, 'welcome_message', 'welcome_edit_prompt')
        elif edit_type == 'about':
            self.show_edit_prompt(call, lang_code, 'about', 'about_edit_prompt')
        elif edit_type == 'contact':
            self.show_edit_prompt(call, lang_code, 'contact', 'contact_edit_prompt')
        elif edit_type == 'delivery_prompt':
            self.show_edit_prompt(call, lang_code, 'delivery_address_prompt', 'delivery_prompt_edit_prompt')
    
    def show_edit_prompt(self, call, lang_code, content_key, prompt_key):
        """Show edit prompt for a specific content type"""
        logger.info(f"show_edit_prompt called with lang_code: {lang_code}, content_key: {content_key}")
        # Get current content based on content_key
        if content_key == 'welcome_message':
            current_text = self.language.get_text('welcome_message', lang_code)
        elif content_key == 'about':
            current_text = self.language.get_button_response('about', 'message', lang_code)
        elif content_key == 'contact':
            current_text = self.language.get_button_response('contact', 'message', lang_code)
        else:
            current_text = "Content not found"
        
        # Get prompt text and format with current content
        prompt_template = self.language.get_text(prompt_key, lang_code)
        prompt_text = prompt_template.format(current_text=current_text)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_store_settings', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='store_back_to_settings'
        ))
        
        # Set user state for input handling
        self.db.set_user_state(
            user_id=call.from_user.id,
            state=f'editing_{content_key}',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Send prompt as a new message
        
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=prompt_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    # ==================== BROADCAST ====================
    def show_broadcast_menu(self, call):
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config.get('admin_ids', [])):
            self.bot.answer_callback_query(call.id, "❌ Acces interzis.", show_alert=True)
            return

        self.db.clear_user_state(user_id)
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📝 Doar text", callback_data="admin_broadcast_text"),
            telebot.types.InlineKeyboardButton("🖼 Poză + descriere", callback_data="admin_broadcast_photo")
        )
        markup.add(telebot.types.InlineKeyboardButton("🔙 Înapoi", callback_data="admin_panel"))
        self.bot.send_message(
            call.message.chat.id,
            "📢 <b>Broadcast către utilizatori</b>\n\n"
            "Alege tipul mesajului. Înainte de trimitere vei primi un preview și confirmare.",
            parse_mode='HTML',
            reply_markup=markup
        )
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass

    def start_broadcast_text(self, call):
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config.get('admin_ids', [])):
            return
        self.db.set_user_state(user_id, 'admin_broadcast_waiting_text', data='{}')
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("❌ Anulează", callback_data="admin_broadcast_cancel"))
        self.bot.send_message(
            call.message.chat.id,
            "📝 Trimite acum textul broadcast-ului.\n\nMaxim 4096 caractere.",
            reply_markup=markup
        )
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass

    def start_broadcast_photo(self, call):
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config.get('admin_ids', [])):
            return
        self.db.set_user_state(user_id, 'admin_broadcast_waiting_photo', data='{}')
        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton("❌ Anulează", callback_data="admin_broadcast_cancel"))
        self.bot.send_message(
            call.message.chat.id,
            "🖼 Trimite acum poza. Poți pune descrierea direct în caption.\n\n"
            "Dacă nu pui caption, poza va fi trimisă fără descriere.",
            reply_markup=markup
        )
        try:
            self.bot.answer_callback_query(call.id)
        except Exception:
            pass

    def handle_broadcast_text_input(self, message):
        user_id = message.from_user.id
        if not self.db.is_admin(user_id, self.config.get('admin_ids', [])):
            self.db.clear_user_state(user_id)
            return False

        text = message.text or ''
        if not text.strip():
            self.bot.send_message(message.chat.id, "❌ Mesajul nu poate fi gol.")
            return True
        if len(text) > 4096:
            self.bot.send_message(message.chat.id, f"❌ Mesaj prea lung ({len(text)}/4096).")
            return True

        payload = json.dumps({"type": "text", "text": text}, ensure_ascii=False)
        self.db.set_user_state(user_id, 'admin_broadcast_ready', data=payload)
        self._show_broadcast_preview(message.chat.id, user_id, {"type": "text", "text": text})
        return True

    def handle_broadcast_photo_input(self, message):
        user_id = message.from_user.id
        state = self.db.get_user_state(user_id)
        if not state or state.get('state') != 'admin_broadcast_waiting_photo':
            return False
        if not self.db.is_admin(user_id, self.config.get('admin_ids', [])):
            self.db.clear_user_state(user_id)
            return False
        if not getattr(message, 'photo', None):
            self.bot.send_message(message.chat.id, "❌ Trimite o poză, nu document/video.")
            return True

        file_id = message.photo[-1].file_id
        caption = message.caption or ''
        if len(caption) > 1024:
            self.bot.send_message(message.chat.id, f"❌ Descriere prea lungă ({len(caption)}/1024).")
            return True

        data = {"type": "photo", "file_id": file_id, "caption": caption}
        self.db.set_user_state(user_id, 'admin_broadcast_ready', data=json.dumps(data, ensure_ascii=False))
        self._show_broadcast_preview(message.chat.id, user_id, data)
        return True

    def _show_broadcast_preview(self, chat_id, user_id, data):
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("✅ Trimite tuturor", callback_data="admin_broadcast_confirm"),
            telebot.types.InlineKeyboardButton("❌ Anulează", callback_data="admin_broadcast_cancel")
        )

        self.bot.send_message(chat_id, "👁 <b>Preview broadcast:</b>", parse_mode='HTML')
        if data.get('type') == 'photo':
            self.bot.send_photo(
                chat_id,
                data['file_id'],
                caption=data.get('caption') or None,
                reply_markup=markup
            )
        else:
            self.bot.send_message(chat_id, data.get('text', ''), reply_markup=markup)

    def confirm_broadcast(self, call):
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config.get('admin_ids', [])):
            self.bot.answer_callback_query(call.id, "❌ Acces interzis.", show_alert=True)
            return

        state = self.db.get_user_state(user_id)
        if not state or state.get('state') != 'admin_broadcast_ready':
            self.bot.answer_callback_query(call.id, "❌ Draft-ul a expirat.", show_alert=True)
            return

        try:
            data = state.get('data')
            payload = data if isinstance(data, dict) else json.loads(data or '{}')
        except Exception:
            self.db.clear_user_state(user_id)
            self.bot.answer_callback_query(call.id, "❌ Draft invalid.", show_alert=True)
            return

        self.db.clear_user_state(user_id)
        try:
            self.bot.answer_callback_query(call.id, "📤 Broadcast pornit.")
        except Exception:
            pass
        self.bot.send_message(call.message.chat.id, "📤 Broadcast pornit. Vei primi raportul la final.")

        thread = threading.Thread(
            target=self._run_broadcast,
            args=(user_id, call.message.chat.id, payload),
            daemon=True,
            name=f"broadcast-{user_id}"
        )
        thread.start()

    def _run_broadcast(self, admin_user_id, admin_chat_id, payload):
        conn = None
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            # Trimitem tuturor utilizatorilor cunoscuți de bot. Userii care au blocat
            # botul vor fi numărați ca failed și broadcast-ul continuă.
            cursor.execute("SELECT DISTINCT user_id FROM users WHERE user_id IS NOT NULL")
            recipients = [int(row[0]) for row in cursor.fetchall()]
        except Exception as e:
            logger.exception("Broadcast recipient query failed: %s", e)
            try:
                self.bot.send_message(admin_chat_id, f"❌ Broadcast oprit: nu am putut citi utilizatorii.\n{e}")
            except Exception:
                pass
            return
        finally:
            if conn:
                conn.close()

        total = len(recipients)
        sent = 0
        failed = 0
        started = time.time()

        logger.info("Broadcast started by admin %s to %s users", admin_user_id, total)

        for index, target_id in enumerate(recipients, start=1):
            try:
                if payload.get('type') == 'photo':
                    self.bot.send_photo(
                        target_id,
                        payload['file_id'],
                        caption=payload.get('caption') or None
                    )
                else:
                    self.bot.send_message(target_id, payload.get('text', ''))
                sent += 1
            except Exception as e:
                failed += 1
                logger.warning("Broadcast failed for user %s: %s", target_id, e)

            # Telegram allows substantially more, but ~20 msg/s gives headroom for
            # normal bot traffic and avoids burst rate limits.
            time.sleep(0.05)

        elapsed = time.time() - started
        report = (
            "✅ <b>Broadcast finalizat</b>\n\n"
            f"👥 Total: <b>{total}</b>\n"
            f"✅ Trimise: <b>{sent}</b>\n"
            f"❌ Eșuate/blocate: <b>{failed}</b>\n"
            f"⏱ Durată: <b>{elapsed:.1f}s</b>"
        )
        logger.info("Broadcast completed: total=%s sent=%s failed=%s", total, sent, failed)
        try:
            self.bot.send_message(admin_chat_id, report, parse_mode='HTML')
        except Exception as e:
            logger.error("Could not send broadcast report: %s", e)

    @handler_operation
    def handle_text_input(self, message):
        """Handle text input when user is in editing state"""
        import time
        start_time = time.time()
        user_id = message.from_user.id
        
        logger.info(f"🔍 DEBUG: Admin handler text input START for user {user_id} at {start_time:.3f}")
        
        # Get user state
        db_start = time.time()
        user_state = self.db.get_user_state(user_id)
        db_time = time.time() - db_start
        logger.info(f"🔍 DEBUG: Admin handler get_user_state took {db_time:.3f}s")
        logger.info(f"🔍 DEBUG: Admin handler text input for user {user_id}, state: {user_state}")
        
        # Check if user is waiting for API key input
        if user_state and user_state['state'] == 'waiting_api_key':
            handler_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Admin handler API key input processing in {handler_time:.3f}s")
            return self.handle_api_key_input(message)
        
        # Broadcast text input
        if user_state and user_state['state'] == 'admin_broadcast_waiting_text':
            return self.handle_broadcast_text_input(message)

        # Check if user is waiting for admin link input
        if user_state and user_state['state'] == 'waiting_admin_link':
            handler_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Admin handler admin link input processing in {handler_time:.3f}s")
            logger.info(f"User {user_id} in waiting_admin_link state, handling input")
            return self.handle_admin_link_input(message)
                    
        if user_state and user_state['state'] == 'admin_search_user':
            return self.handle_user_search(
                message
            )
        
        if user_state and user_state['state'] in [
            'admin_balance_add',
            'admin_balance_remove',
            'admin_balance_set'
        ]:
            return self.handle_balance_edit(
                message
            )
        
        # Only handle store content editing states, not category states
        if not user_state or not (
            user_state['state'] == 'editing_welcome_message' or
            user_state['state'] == 'editing_about' or
            user_state['state'] == 'editing_contact' or
            user_state['state'] == 'editing_delivery_address_prompt'
        ):
            handler_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Admin handler not in editing state, returning False in {handler_time:.3f}s")
            return False  # Not in admin editing state
        
        # Check if user is admin
        admin_check_start = time.time()
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            admin_check_time = time.time() - admin_check_start
            logger.info(f"🔍 DEBUG: Admin handler user not admin, returning False in {admin_check_time:.3f}s")
            return False
        admin_check_time = time.time() - admin_check_start
        logger.info(f"🔍 DEBUG: Admin handler admin check passed in {admin_check_time:.3f}s")
        
        # Extract content type from state
        content_type = user_state['state'].replace('editing_', '')
        lang_code = user_state['data']
        new_text = message.text
        
        logger.info(f"🔍 DEBUG: Admin handler processing content update: {content_type}, lang: {lang_code}")
        
        # Update the JSON file
        json_update_start = time.time()
        success = self.update_language_json(content_type, lang_code, new_text)
        json_update_time = time.time() - json_update_start
        logger.info(f"🔍 DEBUG: Admin handler JSON update took {json_update_time:.3f}s, success: {success}")
        
        if success:
            # Show success message
            response_start = time.time()
            success_text = self.language.get_text('text_updated_success', lang_code)
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=f"{success_text} ✅",
                parse_mode='HTML'
            )
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Reload language system
            self.language.reload_languages()
            
            # Show store settings menu again
            markup = telebot.types.InlineKeyboardMarkup()
            back_settings_text = self.language.get_text('back_to_store_settings', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_settings_text,
                callback_data='admin_store_settings'
            ))
            
            returning_text = self.language.get_text('returning_to_store_settings', lang_code)
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=returning_text,
                reply_markup=markup
            )
            response_time = time.time() - response_start
            logger.info(f"🔍 DEBUG: Admin handler success response took {response_time:.3f}s")
        else:
            response_start = time.time()
            try:
                error_text = self.language.get_text('error_updating_content', lang_code)
            except:
                error_text = "❌ Error updating content. Please try again."
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=error_text
            )
            response_time = time.time() - response_start
            logger.info(f"🔍 DEBUG: Admin handler error response took {response_time:.3f}s")
        
        total_time = time.time() - start_time
        logger.info(f"🔍 DEBUG: Admin handler text input COMPLETE in {total_time:.3f}s for user {user_id}")
        return True  # Input was handled
    

    def handle_balance_edit(
        self,
        message
    ):

        admin_id = message.from_user.id

        state = self.db.get_user_state(
            admin_id
        )

        if not state:
            return False

        try:

            amount = float(
                message.text.strip()
            )

        except:

            self.bot.send_message(
                message.chat.id,
                "❌ Sumă invalidă"
            )

            return True

        target_id = int(
            state['data']
        )

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        if state['state'] == 'admin_balance_add':

            cursor.execute(
                """
                UPDATE users
                SET balance = balance + ?
                WHERE user_id = ?
                """,
                (
                    amount,
                    target_id
                )
            )

        elif state['state'] == 'admin_balance_remove':

            cursor.execute(
                """
                UPDATE users
                SET balance =
                CASE
                    WHEN balance - ? < 0
                    THEN 0
                    ELSE balance - ?
                END
                WHERE user_id = ?
                """,
                (
                    amount,
                    amount,
                    target_id
                )
            )

        elif state['state'] == 'admin_balance_set':

            cursor.execute(
                """
                UPDATE users
                SET balance = ?
                WHERE user_id = ?
                """,
                (
                    amount,
                    target_id
                )
            )

        conn.commit()

        cursor.execute(
            """
            SELECT balance
            FROM users
            WHERE user_id = ?
            """,
            (target_id,)
        )

        balance = float(
            cursor.fetchone()[0]
        )

        conn.close()

        action = "actualizat"

        if state['state'] == 'admin_balance_add':
            action = f"adăugat {amount:.2f} RON"

        elif state['state'] == 'admin_balance_remove':
            action = f"retras {amount:.2f} RON"

        elif state['state'] == 'admin_balance_set':
            action = f"setat balanța la {amount:.2f} RON"

        try:

            self.bot.send_message(
                target_id,
                f"💰 <b>Actualizare Balanță</b>\n\n"
                f"Un administrator ti-a {action}.\n\n"
                f"💳 <b>Balanță curentă:</b> {balance:.2f} RON",
                parse_mode='HTML'
            )

        except Exception as e:

            logger.warning(
                f"Could not notify user {target_id}: {e}"
            )

        self.db.clear_user_state(
            admin_id
        )

        self.bot.send_message(
            message.chat.id,
            f"✅ Balanță actualizată.\n\n"
            f"💰 Noua balanță: "
            f"{balance:.2f} RON"
        )

        return True

    def handle_back_to_settings(self, call):
        """Handle back to store settings button"""
        user_id = call.from_user.id
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Show store settings menu
        self.show_store_settings_menu(call, lang_code)
    
    def update_language_json(self, content_type, lang_code, new_text):
        """Update the language.json file with new content"""
        try:
            logger.info(f"Attempting to update {content_type} for {lang_code}")
            
            # Read current language file
            with open('language.json', 'r', encoding='utf-8') as f:
                language_data = json.load(f)
            
            # Check if language exists
            if lang_code not in language_data:
                logger.error(f"Language {lang_code} not found in language data")
                return False
            
            # Update the appropriate content
            if content_type == 'welcome_message':
                language_data[lang_code]['welcome_message'] = new_text
                logger.info(f"Updated welcome_message for {lang_code}")
            elif content_type == 'about':
                if 'button_responses' not in language_data[lang_code]:
                    logger.error(f"button_responses not found for {lang_code}")
                    return False
                if 'about' not in language_data[lang_code]['button_responses']:
                    logger.error(f"about button not found for {lang_code}")
                    return False
                language_data[lang_code]['button_responses']['about']['message'] = new_text
                logger.info(f"Updated about message for {lang_code}")
            elif content_type == 'contact':
                if 'button_responses' not in language_data[lang_code]:
                    logger.error(f"button_responses not found for {lang_code}")
                    return False
                if 'contact' not in language_data[lang_code]['button_responses']:
                    logger.error(f"contact button not found for {lang_code}")
                    return False
                language_data[lang_code]['button_responses']['contact']['message'] = new_text
                logger.info(f"Updated contact message for {lang_code}")
            elif content_type == 'delivery_address_prompt':
                language_data[lang_code]['delivery_address_prompt'] = new_text
                logger.info(f"Updated delivery_address_prompt for {lang_code}")
            else:
                logger.error(f"Unknown content_type: {content_type}")
                return False
            
            # Write back to file
            save_json_safely("language.json", language_data)
            
            logger.info(f"Successfully updated {content_type} for {lang_code}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating language file: {e}")
            logger.error(f"Content type: {content_type}, Lang code: {lang_code}")
            return False
    
    def show_payment_setup(self, call, lang_code):
        """Show payment setup instructions for OxaPay"""
        setup_text = self.language.get_text('payment_setup_message', lang_code)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='payment_setup_back'
        ))
        
        # Set user state for API key input
        self.db.set_user_state(
            user_id=call.from_user.id,
            state='waiting_api_key',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=setup_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_payment_setup_back(self, call):
        """Handle back button from payment setup"""
        user_id = call.from_user.id
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Go back to admin panel
        self.handle_admin_panel(call)
    
    def handle_api_key_input(self, message):
        """Handle API key input from user"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Check if user is in API key waiting state
        if not user_state or user_state['state'] != 'waiting_api_key':
            return False
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        lang_code = user_state['data']
        api_key = message.text.strip()
        
        # Validate API key (basic validation)
        if not api_key or len(api_key) < 10:
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Invalid API key. Please provide a valid OxaPay API key."
            )
            return True
        
        # Update config.json with the API key
        success = self.update_config_api_key(api_key)
        
        if success:
            # Determine if this is new or updated
            current_key = self.config.get('oxapay_api_key', '')
            if current_key:
                success_text = self.language.get_text('api_key_updated', lang_code)
            else:
                success_text = self.language.get_text('api_key_saved', lang_code)
            
            # Update local config
            self.config['oxapay_api_key'] = api_key
            
            # Update payment handler's API key immediately if payment handler exists
            if self.payment_handler:
                self.payment_handler.oxapay_api_key = api_key
            
           
            self.bot.send_message(
                chat_id=message.chat.id,
                text=success_text,
                parse_mode='HTML'
            )
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Show back to admin panel button
            markup = telebot.types.InlineKeyboardMarkup()
            back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_admin_text,
                callback_data='admin_panel'
            ))
            
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text="🔄 Returning to admin panel...",
                reply_markup=markup
            )
        else:
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Error saving API key. Please try again."
            )
        
        return True
    
    def update_config_api_key(self, api_key):
        """Update config.json with new API key"""
        try:
            # Read current config
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Update API key
            config_data['oxapay_api_key'] = api_key
            
            # Write back to file
            save_json_safely("config.json", config_data)
            
            logger.info(f"Successfully updated oxapay_api_key in config.json")
            return True
            
        except Exception as e:
            logger.error(f"Error updating config file: {e}")
            return False
    
    def show_admin_setup(self, call, lang_code):
        """Show admin setup instructions"""
        setup_text = self.language.get_text('setup_admin_message', lang_code)
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_chat_setup_back'
        ))
        
        # Set user state for admin link input
        self.db.set_user_state(
            user_id=call.from_user.id,
            state='waiting_admin_link',
            data=lang_code,
            message_id=call.message.message_id
        )
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=setup_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")
    
    def handle_admin_setup_back(self, call):
        """Handle back button from admin setup - clear ALL states for clean return"""
        user_id = call.from_user.id
        
        # Clear ALL user states to ensure clean slate
        success = self.db.clear_user_state(user_id)
        logger.info(f"Admin setup back: cleared ALL states for user {user_id}, success: {success}")
        
        # Also clear any potential lingering states (double-check)
        try:
            # Force clear any remaining states
            import sqlite3
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"Force cleared all states for user {user_id}")
        except Exception as e:
            logger.error(f"Error force clearing states: {e}")
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Go back to admin panel
        self.handle_admin_panel(call)
        
    def handle_user_search(self, message):

        admin_id = message.from_user.id

        state = self.db.get_user_state(
            admin_id
        )

        if not state:
            return False

        try:

            target_id = int(
                message.text.strip()
            )
            
            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    username,
                    balance,
                    warnings,
                    is_seller,
                    is_banned
                FROM users
                WHERE user_id = ?
                """,
                (target_id,)
            )

            row = cursor.fetchone()

            if not row:

                self.db.clear_user_state(
                    admin_id
                )

                self.bot.send_message(
                    message.chat.id,
                    "❌ Utilizator inexistent. Căutare anulată"
                )

                conn.close()
                return True

            username = row[0]
            balance = float(row[1] or 0)
            warnings = int(row[2] or 0)
            is_seller = int(row[3] or 0)
            is_banned = int(row[4] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM selling_history
                WHERE user_id = ?
                """,
                (target_id,)
            )

            total_orders = int(
                cursor.fetchone()[0]
            )

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM reviews
                WHERE user_id = ?
                """,
                (target_id,)
            )

            total_reviews = int(
                cursor.fetchone()[0]
            )

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM disputes
                WHERE user_id = ?
                """,
                (target_id,)
            )

            total_disputes = int(
                cursor.fetchone()[0]
            )

            conn.close()

            trust_score = self.calculate_trust_score(
                total_orders,
                total_reviews,
                total_disputes,
                warnings
            )

        except:

            self.db.clear_user_state(
                admin_id
            )

            self.bot.send_message(
                message.chat.id,
                "❌ ID invalid. Căutarea a fost anulată"
            )

            return True
            
        role = "Seller" if is_seller else "User"

        text = (
            f"👤 <b>Profil Utilizator</b>\n\n"

            f"🆔 <b>Telegram ID:</b> {target_id}\n"
            f"👤 <b>Username:</b> @{username}\n\n"

            f"💰 <b>Balanță:</b> {balance:.2f} RON\n"

            f"📦 <b>Comenzi:</b> {total_orders}\n"
            f"🎫 <b>Tichete:</b> {total_disputes}\n\n"

            f"📈 <b>Scor de Incredere:</b> {trust_score}%\n"
            f"⚠️ <b>Warn:</b> {warnings}/3\n"

            f"🚫 <b>Ban:</b> "
            f"{'Da' if is_banned else 'Nu'}\n"

            f"🔐 <b>Rol:</b> "
            f"{'Seller' if is_seller else 'User'}"
        )

        markup = telebot.types.InlineKeyboardMarkup()

        markup.row(
            telebot.types.InlineKeyboardButton(
                text="💰 Balanță",
                callback_data=f"admin_user_balance_{target_id}"
            )
        )

        markup.row(
            telebot.types.InlineKeyboardButton(
                text="⚠️ Warning",
                callback_data=f"admin_user_warn_menu_{target_id}"
            ),
            telebot.types.InlineKeyboardButton(
                text="🚫 Ban",
                callback_data=f"admin_user_ban_{target_id}"
            )
        )

        markup.row(
            telebot.types.InlineKeyboardButton(
                text="📦 Comenzi",
                callback_data=f"admin_user_orders_{target_id}"
            ),
            telebot.types.InlineKeyboardButton(
                text="🎫 Tichete",
                callback_data=f"admin_user_tickets_{target_id}"
            )
        )

        self.db.clear_user_state(
            admin_id
        )

        self.bot.send_message(
            message.chat.id,
            text,
            parse_mode='HTML',
            reply_markup=markup
        )

        return True    
        
    def calculate_trust_score(
        self,
        total_orders,
        total_reviews,
        total_disputes,
        warnings
    ):

        score = 0

        score += total_orders * 0.75
        score += total_reviews * 0.75

        score -= total_disputes * 1.0
        score -= warnings * 20

        if score < 0:
            score = 0

        if score > 100:
            score = 100

        return round(score, 1)    
    
    def handle_admin_link_input(self, message):
        """Handle admin link input from user"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        # Check if user is in admin link waiting state
        if not user_state or user_state['state'] != 'waiting_admin_link':
            return False
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        lang_code = user_state['data']
        admin_link = message.text.strip()
        
        # Validate admin link (basic validation)
        if not admin_link or len(admin_link) < 3:
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Invalid admin link. Please provide a valid link or username."
            )
            return True
        
        # Update config.json with the admin link
        success = self.update_config_admin_link(admin_link)
        
        if success:
            # Determine if this is new or updated
            current_link = self.config.get('admin_chat_link', '')
            if current_link:
                success_text = self.language.get_text('admin_link_updated', lang_code)
            else:
                success_text = self.language.get_text('admin_link_saved', lang_code)
            
            # Update local config
            self.config['admin_chat_link'] = admin_link
            
            # Clear user state
            self.db.clear_user_state(user_id)
            
            # Send success message and show admin panel directly
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=f"{success_text} 🔄 Returning to admin panel...",
                parse_mode='HTML'
            )
            
            # Create admin panel message
            welcome_text = self.language.get_text('admin_panel_welcome', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()
            
            # Add admin action buttons
            admin_buttons = self.language.get_admin_buttons(lang_code)
            for button_row in admin_buttons:
                row_buttons = []
                for btn in button_row:
                    button_text = btn['text']
                    callback_data = btn['callback_data']
                    
                    # If it's the currency button, add current currency symbol
                    if callback_data == 'admin_currency_settings':
                        current_currency = self.config.get('currency', {'symbol': '$'})
                        button_text = f"{button_text}: {current_currency['symbol']}"
                    
                    row_buttons.append(telebot.types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=callback_data
                    ))
                markup.row(*row_buttons)
            
            # Add back to main menu button
            back_text = self.language.get_text('back_to_menu', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            # Send admin panel
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=welcome_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        else:
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text="❌ Error saving admin link. Please try again."
            )
        
        return True
    
    def handle_cashout_callbacks(
        self,
        call
    ):

        data = call.data

        if data.startswith("cashout_view_"):

            request_id = int(

                data.replace(
                    "cashout_view_",
                    ""
                )

            )

            self.show_cashout_request(

                call,

                request_id

            )

            return
            
        elif data.startswith("cashout_crypto_view_"):

            request_id = int(
                data.replace(
                    "cashout_crypto_view_",
                    ""
                )
            )

            self.show_crypto_cashout_request(
                call,
                request_id
            )

            return    
    
        elif data.startswith("cashout_photo_"):

            request_id = int(
                data.replace(
                    "cashout_photo_",
                    ""
                )
            )

            self.db.set_user_state(

                user_id=call.from_user.id,

                state="cashout_waiting_photo",

                data={
                    "request_id": request_id
                }

            )

            self.bot.send_message(

                call.message.chat.id,

                f"""
        📷 Trimite fotografia pentru cererea

        <b>#{request_id}</b>

        După ce trimiți fotografia vei putea finaliza retragerea.
        """,

                parse_mode="HTML"

            )

            self.bot.answer_callback_query(call.id)

            return
    
        elif data.startswith("cashout_finish_"):

            request_id = int(
                data.replace(
                    "cashout_finish_",
                    ""
                )
            )

            self.finish_cashout(
                call,
                request_id
            )

            return
    
    def show_cashout_request(
        self,
        call,
        request_id
    ):

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        cursor.execute("""

        SELECT

        seller_id,
        amount,
        fee,
        amount_after_fee,
        status

        FROM cashout_requests

        WHERE id=?

        """,(request_id,))

        row = cursor.fetchone()

        conn.close()

        if not row:

            self.bot.answer_callback_query(

                call.id,

                "Nu există."

            )

            return

        seller = row[0]

        amount = row[1]

        fee = row[2]

        receive = row[3]

        status = row[4]

        text = f"""
    💸 <b>Cerere Retragere #{request_id}</b>

    👤 Seller

    <code>{seller}</code>

    ────────────

    💰 Sumă:

    {amount:.2f} RON

    💸 Taxă:

    {fee:.2f} RON

    📤 Primește:

    {receive:.2f} RON

    📌 Status:

    {status}
    """

        markup = telebot.types.InlineKeyboardMarkup()

        if status == "pending":

            markup.add(

                telebot.types.InlineKeyboardButton(

                    "📷 Încarcă poză",

                    callback_data=f"cashout_photo_{request_id}"

                )

            )

        elif status == "waiting_photo":

            markup.add(

                telebot.types.InlineKeyboardButton(

                    "✅ Finalizează Retragerea",

                    callback_data=f"cashout_finish_{request_id}"

                )

            )

        markup.add(

            telebot.types.InlineKeyboardButton(

                "🔙 Înapoi",

                callback_data="admin_cashout_requests"

            )

        )

        self.bot.edit_message_text(

            text,

            call.message.chat.id,

            call.message.message_id,

            parse_mode="HTML",

            reply_markup=markup

        )

        self.bot.answer_callback_query(call.id)

    def show_crypto_cashout_request(
        self,
        call,
        request_id
    ):

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                seller_id,
                amount,
                fee,
                amount_after_fee,
                wallet_address,
                crypto_amount,
                payout_track_id,
                payout_status,
                status
            FROM cashout_requests
            WHERE id=?
            AND method='crypto'
        """,(request_id,))

        row = cursor.fetchone()

        conn.close()

        if not row:

            self.bot.answer_callback_query(
                call.id,
                "❌ Cererea crypto nu există.",
                show_alert=True
            )

            return

        seller_id = row[0]
        amount = float(row[1])
        fee = float(row[2])
        receive = float(row[3])
        wallet_address = row[4] or "-"
        crypto_amount = float(row[5] or 0)
        payout_track_id = row[6] or "-"
        payout_status = row[7] or "unknown"
        status = row[8] or "unknown"

        text = f"""
    🪙 <b>Retragere Crypto #{request_id}</b>

    👤 <b>Seller:</b>
    <code>{seller_id}</code>

    💰 <b>Sumă:</b>
    {amount:.2f} RON

    💸 <b>Taxă:</b>
    {fee:.2f} RON

    📤 <b>Net:</b>
    {receive:.2f} RON

    🪙 <b>LTC:</b>
    {crypto_amount:.8f}

    🏦 <b>Adresă:</b>
    <code>{wallet_address}</code>

    🆔 <b>Payout ID:</b>
    <code>{payout_track_id}</code>

    📌 <b>Payout status:</b>
    {payout_status}

    📌 <b>Request status:</b>
    {status}
    """

        markup = telebot.types.InlineKeyboardMarkup()

        markup.add(
            telebot.types.InlineKeyboardButton(
                "🔙 Înapoi",
                callback_data="admin_crypto_cashout_requests"
            )
        )

        self.bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup
        )

        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass

    def update_config_admin_link(self, admin_link):
        """Update config.json with new admin link"""
        try:
            # Read current config
            with open('config.json', 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Update admin link
            config_data['admin_chat_link'] = admin_link
            
            # Write back to file
            save_json_safely("config.json", config_data)
            
            logger.info(f"Successfully updated admin_chat_link in config.json")
            return True
            
        except Exception as e:
            logger.error(f"Error updating config file: {e}")
            return False
