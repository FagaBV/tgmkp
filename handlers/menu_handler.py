import telebot
import logging
import json
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class MenuHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.cart_handler = None  # Will be set by main.py
        self.topup_handler = None  # Will be set by main.py
        
    def load_store_images(self):
        """Load page images config"""
        try:
            with open('store_images.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def send_page_with_image(self, chat_id, page_key, text, markup=None):
        """Send page with optional image"""
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
    
    def get_welcome_with_balance(self, user_id, lang_code):
        """Get welcome message with user's balance"""
        # Get welcome message
        welcome_text = self.language.get_text('welcome_message', lang_code)
        
        # Get user's balance
        balance = self.db.get_user_balance(user_id)
        currency_symbol = self.config.get('currency', {}).get('symbol', '$')
        
        # Get balance display text
        balance_text = self.language.get_text('balance_display', lang_code)
        balance_text = balance_text.format(balance=f"{balance:.2f}", currency_symbol=currency_symbol)
        
        # Combine welcome message with balance
        return welcome_text + balance_text
    

    def handle_menu_buttons(self, call):
        """Handle main menu button clicks with new ID-based system"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract button ID from callback data
        button_id = call.data.replace('menu_', '')
        
        # Handle special cases that should redirect to other handlers
        if button_id == 'products':
            # This should be handled by shopping handler
            # We'll return False to indicate it wasn't handled here
            return False
        elif button_id == 'cart':
            # This should be handled by shopping handler  
            # We'll return False to indicate it wasn't handled here
            return False
        elif button_id == 'topup':
            # This should be handled by topup handler
            return False
        elif button_id == 'reviews':
            # This should be handled by reviews handler
            return False
        elif button_id == 'profile':
            return False
        elif button_id == 'disputes':
            # This should be handled by dispute handler
            return False
        elif button_id == 'admin_link':
            # Handle admin link - open the link from config
            self.handle_admin_link(call)
            return True
        elif button_id == 'history':
            # This should be handled by history handler
            # We'll return False to indicate it wasn't handled here
            return False
        
        # For other buttons, show generic response
        # Get button response from language system
        response_data = self.language.get_button_response(button_id, None, lang_code)
        response_text = response_data['message']
        
        # Add back to menu button
        markup = telebot.types.InlineKeyboardMarkup()
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
        return True
    
    def send_main_menu_message(self, chat_id, user_id):
        """Send full main menu as a normal message with optional image"""
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.send_message(chat_id, "❌ Database error. Please try again.")
            return

        lang_code = user['language_code']
        welcome_text = self.get_welcome_with_balance(user_id, lang_code)

        markup = telebot.types.InlineKeyboardMarkup()

         # Add main menu action buttons with dynamic cart + dynamic seller button
        main_menu_buttons = self.language.get_main_menu_buttons(lang_code, user_id, self.cart_handler)
        for button_row in main_menu_buttons:
            row_buttons = []

            for btn in button_row:
                btn_text = btn['text']
                btn_callback = btn['callback_data']

                if btn.get('id') == 'seller':
                    if self.db.is_seller(user_id):
                        btn_text = self.language.get_text('seller_edit_button', lang_code)
                        btn_callback = 'menu_edit_seller_shop'
                    else:
                        btn_text = self.language.get_text('seller_buy_button', lang_code)
                        btn_callback = 'menu_become_seller'

                row_buttons.append(
                    telebot.types.InlineKeyboardButton(
                        text=btn_text,
                        callback_data=btn_callback
                    )
                )

            markup.row(*row_buttons)

        self.send_page_with_image(
            chat_id,
            "main_menu",
            welcome_text,
            markup
        )

        # Creare buton seller si legare in baza de date
    def handle_main_menu(self, call):
        """Handle main menu callback"""
        user_id = call.from_user.id
        self.db.clear_user_state(user_id)

        user = self.db.get_or_create_user(user_id)
        if not user:
            if getattr(call, 'id', None):
                self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return

        lang_code = user['language_code']
        welcome_text = self.get_welcome_with_balance(user_id, lang_code)

        markup = telebot.types.InlineKeyboardMarkup()

        # Add main menu action buttons with dynamic cart + dynamic seller button
        main_menu_buttons = self.language.get_main_menu_buttons(lang_code, user_id, self.cart_handler)
        for button_row in main_menu_buttons:
            row_buttons = []

            for btn in button_row:
                btn_text = btn['text']
                btn_callback = btn['callback_data']

                if btn.get('id') == 'seller':
                    if self.db.is_seller(user_id):
                        btn_text = self.language.get_text('seller_edit_button', lang_code)
                        btn_callback = 'menu_edit_seller_shop'
                    else:
                        btn_text = self.language.get_text('seller_buy_button', lang_code)
                        btn_callback = 'menu_become_seller'
                
                row_buttons.append(
                    telebot.types.InlineKeyboardButton(
                        text=btn_text,
                        callback_data=btn_callback
                    )
                )

            markup.row(*row_buttons)

        # Nu mai încercăm edit_message_text pentru pagina cu imagine
        self.send_page_with_image(
            call.message.chat.id,
            "main_menu",
            welcome_text,
            markup
        )

        if getattr(call, 'id', None):
            try:
                self.bot.answer_callback_query(call.id)
            except Exception:
                pass

    def handle_main_menu_keyboard(self, message):
        """Show only bottom quick keyboard buttons"""
        user_id = message.from_user.id

        user = self.db.get_or_create_user(user_id)
        if not user:
            return

        lang_code = user['language_code']

        reply_markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn_main = self.language.get_text('menu_button_main', lang_code)
        btn_admin = self.language.get_text('menu_button_admin', lang_code)

        if self.db.is_admin(user_id, self.config['admin_ids']):
            reply_markup.row(btn_main, btn_admin)
        else:
            reply_markup.row(btn_main)

        self.bot.send_message(
            message.chat.id,
            "Initiere...",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        
    def handle_admin_link(self, call):
        """Handle admin link button - open admin chat link"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get admin chat link from config
        admin_link = self.config.get('admin_chat_link', '')
        
        if not admin_link:
            # No admin link configured
            self.bot.answer_callback_query(
                call.id, 
                "❌ Admin contact not configured. Please contact the shop owner.",
                show_alert=True
            )
            return
        
        # Format the admin link message
        admin_text = f"👤 <b>Contact Admin</b>\n\n🔗 Click the link below to contact our admin:\n\n{admin_link}\n\n💬 You can also copy the link and paste it in your browser or Telegram."
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Add URL button if it's a proper URL
        if admin_link.startswith(('http://', 'https://', 't.me/')):
            if not admin_link.startswith('https://') and admin_link.startswith('t.me/'):
                full_link = f"https://{admin_link}"
            else:
                full_link = admin_link
            
            markup.add(telebot.types.InlineKeyboardButton(
                text="🔗 Open Admin Chat",
                url=full_link
            ))
        
        # Back to menu button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=admin_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=admin_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        
        # Answer callback query with error handling
        try:
            self.bot.answer_callback_query(call.id)
        except Exception as e:
            logger.debug(f"Failed to answer callback query: {e}")