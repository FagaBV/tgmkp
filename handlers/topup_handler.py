import telebot
import logging
import json
import requests
import time
import threading
from datetime import datetime
from cache_manager import save_json_safely
from utils import replace_message
from shkeeper_client import SHKeeperClient

logger = logging.getLogger(__name__)

class TopupHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        
        self.shkeeper = SHKeeperClient(config)
        self.testing_mode = config.get('payment_testing_mode', False)  # Use sandbox for topup
        
        # Auto-checker worker
        self.checker_thread = None
        self.checker_running = False
        self.check_interval = 30  # Check every 30 seconds
        
        logger.info(f"💳 TopupHandler Initialized:")
        logger.info(f"   - Sandbox Mode: {self.testing_mode}")
        logger.info("   - SHKeeper configured: Yes")
    
    
    def load_store_images(self):
        try:
            with open('store_images.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
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
    # ==================== TOPUP MENU ====================
    
    def handle_topup_menu(self, call):
        """Handle topup button click - show topup menu or existing invoice"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Check if user has a pending invoice
        pending_invoice = self.db.get_pending_topup_invoice(user_id)
        
        if pending_invoice:
            # Show existing invoice
            self.show_existing_invoice(call, pending_invoice, lang_code)
        else:
            # Show amount selection
            self.show_amount_selection(call, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_amount_selection(self, call, lang_code):
        """Show amount selection buttons"""
        balance = self.db.get_user_balance(call.from_user.id)
        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
        
        text = f"""💰 <b>Alimenteaza Contul</b>

💳 <b>Sold curent:</b> {currency_symbol}{balance:.2f}

<b>Selecteaza o suma:</b>
Alege o suma pre-setata sau incarca personalizat.

💡 <i>Vei putea cumpara produse folosind balanta ta!</i>"""
        
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        
        # Preset amounts
        amounts = [80, 140, 280, 600]
        amount_buttons = []
        for amount in amounts:
            amount_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text=f"💵 {currency_symbol}{amount}",
                    callback_data=f"topup_amount_{amount}"
                )
            )
        
        # Add preset buttons in rows of 2
        for i in range(0, len(amount_buttons), 2):
            if i + 1 < len(amount_buttons):
                markup.row(amount_buttons[i], amount_buttons[i + 1])
            else:
                markup.row(amount_buttons[i])
        
        # Custom amount button
        markup.row(telebot.types.InlineKeyboardButton(
            text="✏️ Alta suma",
            callback_data="topup_custom"
        ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data="main_menu"
        ))
        
        self.send_page_with_image(
            call.message.chat.id,
            'topup_menu',
            text,
            markup
        )
        
        if hasattr(call, 'id') and call.id is not None:
            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
                
    def show_existing_invoice(self, call, invoice, lang_code):
        """Show existing pending invoice"""
        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')

        text = f"""⏳ <b>Balanta in asteptare</b>

        Ai deja o alimentare in asteptare:

        💰 <b>Suma:</b> {currency_symbol}{invoice['amount']:.2f}
        🪙 <b>Valuta:</b> {invoice['pay_amount']} {invoice['pay_currency']}
        📍 <b>Adresa:</b> <code>{invoice['address']}</code>
        📅 <b>Creata:</b> {invoice['created_at']}

        ⏰ <b>Te rog asteapta putin, dureaza c.c.a 120 secunde sa se verifice automat!</b>

        💡 <i>Alege o optiune:</i>"""

        markup = telebot.types.InlineKeyboardMarkup()

        # Copy address button
        markup.row(
            telebot.types.InlineKeyboardButton(
                text="📋 Copiaza adresa",
                callback_data=f"topup_copy_{invoice['track_id']}"
            )
        )

        # Cancel button
        markup.row(
            telebot.types.InlineKeyboardButton(
                text="❌ Anuleaza",
                callback_data=f"topup_cancel_{invoice['id']}"
            )
        )

        # Back button
        markup.row(
            telebot.types.InlineKeyboardButton(
                text="🔙 Inapoi",
                callback_data="main_menu"
            )
        )

        self.send_page_with_image(
            call.message.chat.id,
            'topup_menu',
            text,
            markup
        )

        if hasattr(call, 'id') and call.id is not None:
            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
    
    def handle_amount_selection(self, call):
        """Handle preset amount selection"""
        amount = int(call.data.replace('topup_amount_', ''))
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        # Store amount and show currency selection
        self.db.set_user_state(user_id, 'topup_selecting_currency', {'amount': amount})
        self.show_currency_selection(call, amount, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def handle_custom_amount(self, call):
        """Handle custom amount button - ask user to enter amount"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
        
        text = f"""✏️ <b>Depozitare</b>

Scrie suma pe care vrei sa o depozitezi {self.config.get('currency', {}).get('name', 'RON')}.

<b>Exemple:</b>
• <code>25</code> pentru 25 {currency_symbol}
• <code>50</code> pentru 50 {currency_symbol}
• <code>100</code> pentru 100 {currency_symbol}

💬 <b>Introdu suma:</b>"""
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text="❌ Cancel",
            callback_data="menu_topup"
        ))
        
        # Set user state to expect custom amount
        self.db.set_user_state(user_id, 'topup_custom_amount', {'message_id': call.message.message_id})
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing custom amount input: {e}")
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def handle_text_input(self, message):
        """Handle text input for custom amount"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or user_state['state'] != 'topup_custom_amount':
            return False
        
        text = message.text.strip()
        
        # Validate amount
        try:
            amount = float(text)
            if amount <= 0:
                
                self.bot.send_message(
                    message.chat.id,
                    "❌ Suma trebuie sa fie mai mare de 0."
                )
                return True
            if amount > 10000:
                
                self.bot.send_message(
                    message.chat.id,
                    "❌ Suma maxima este 10.000, te rog adauga o suma mai mica."
                )
                return True
        except ValueError:
            
            self.bot.send_message(
                message.chat.id,
                "❌ Suma invalida."
            )
            return True
        
        # Clear state and show currency selection
        self.db.clear_user_state(user_id)
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        # Store amount in state for currency selection
        self.db.set_user_state(user_id, 'topup_selecting_currency', {'amount': amount})
        
        # Create a fake call object to reuse the currency selection function
        self.show_currency_selection_message(message, amount, lang_code)
        return True
    
    def show_currency_selection_message(self, message, amount, lang_code):
        """Show currency selection for message context"""
        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
        
        text = f"""🪙 <b>Selecteaza valuta</b>

💰 <b>Suma:</b> {currency_symbol}{amount:.2f}

<b>Alege cu ce token crypto vrei sa platesti:</b>"""
        
        markup = self.get_currency_markup(amount)
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def show_currency_selection(self, call, amount, lang_code):
        """Show cryptocurrency selection for topup"""
        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
        
        text = f"""🪙 <b>Selecteaza valuta</b>

💰 <b>Suma:</b> {currency_symbol}{amount:.2f}

<b>Alege cu ce token crypto vrei sa platesti:</b>"""
        
        markup = self.get_currency_markup(amount)
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing currency selection: {e}")
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def get_currency_markup(self, amount):
        """Generate currency selection markup"""
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        
        supported_coins = self.config.get('supported_cryptocurrencies', {})
        coin_buttons = []
        
        for coin_code, coin_info in supported_coins.items():
            emoji = coin_info.get('emoji', '🪙')
            name = coin_info.get('name', coin_code)
            coin_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text=f"{emoji} {name}",
                    callback_data=f"topup_coin_{coin_code}_{amount}"
                )
            )
        
        # Add coins in rows of 2
        for i in range(0, len(coin_buttons), 2):
            if i + 1 < len(coin_buttons):
                markup.row(coin_buttons[i], coin_buttons[i + 1])
            else:
                markup.row(coin_buttons[i])
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data="menu_topup"
        ))
        
        return markup
    
    def handle_coin_selection(self, call):
        """Handle cryptocurrency selection and create invoice"""
        user_id = call.from_user.id
        
        # Parse callback data: topup_coin_{coin_code}_{amount}
        parts = call.data.split('_')
        coin_code = parts[2]
        amount = float(parts[3])
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Show processing message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text="⏳ <b>Generam hash-ul...</b>\n\nTe rog asteapta...",
                parse_mode='HTML'
            )
        except:
            pass
        
        # Create SHKeeper invoice
        invoice_data = self.create_shkeeper_invoice(amount, coin_code)
        
        if invoice_data:
            # Save invoice to database
            invoice_id = self.db.create_topup_invoice(
                user_id=user_id,
                amount=amount,
                pay_currency=coin_code,
                pay_amount=invoice_data['pay_amount'],
                track_id=invoice_data['track_id'],
                address=invoice_data['address']
            )
            
            if invoice_id:
                # Show payment details
                self.show_payment_details(call, invoice_data, amount, coin_code, lang_code)
            else:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text="❌ <b>Nu s-a putut salva hash-ul</b>\n\nTe rog incearca din nou.",
                    parse_mode='HTML'
                )
        else:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text="❌ <b>Nu am putut crea plata</b>\n\nTe rog incearca mai tarziu.",
                parse_mode='HTML'
            )
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_payment_details(self, call, invoice_data, amount, coin_code, lang_code):
        """Show payment details to user"""
        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
        supported_coins = self.config.get('supported_cryptocurrencies', {})
        coin_info = supported_coins.get(coin_code, {})
        coin_name = coin_info.get('name', coin_code)
        coin_emoji = coin_info.get('emoji', '🪙')
        
        text = f"""✅ <b>Hash creat!</b>

💰 <b>Suma:</b> {currency_symbol}{amount:.2f}

{coin_emoji} <b>Plateste:</b> <code>{invoice_data['pay_amount']}</code> {coin_code}
📍 <b>Adresa:</b>
<code>{invoice_data['address']}</code>

⏰ <b>Te rog asteapta putin, normal dureaza c.c.a 120 secunde sa se actualizeze automat!</b>

📋 <i>Apasa pe adresa pentru a o copia</i>

🔄 <b>Status:</b> Asteptand plata...

💡 <i>Dupa ce plata va fi acceptata, balanta se va actualiza automat!</i>"""
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Copy address button
        markup.row(telebot.types.InlineKeyboardButton(
            text="📋 Copiaza adresa",
            callback_data=f"topup_copy_{invoice_data['track_id']}"
        ))
        
        # Back to menu
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data="main_menu"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing payment details: {e}")
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
    
    def handle_copy_address(self, call):
        """Handle copy address button"""
        track_id = call.data.replace('topup_copy_', '')
        invoice = self.db.get_topup_invoice_by_track_id(track_id)
        
        if invoice:
            self.bot.answer_callback_query(
                call.id,
                f"📋 Addresa copiata!\n{invoice['address']}",
                show_alert=True
            )
        else:
            self.bot.answer_callback_query(call.id, "❌ Hash-ul e de negasit")
    
    def handle_cancel_invoice(self, call):
        """Handle cancel invoice button"""
        user_id = call.from_user.id
        invoice_id = int(call.data.replace('topup_cancel_', ''))
        
        if self.db.cancel_topup_invoice(invoice_id, user_id):
            self.bot.answer_callback_query(call.id, "✅ Hash oprit!", show_alert=True)
            
            # Show topup menu again
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'en'
            self.show_amount_selection(call, lang_code)
        else:
            self.bot.answer_callback_query(call.id, "❌ Am intampinat o eroare incercand sa opresc hash-ul", show_alert=True)
    
    # ==================== SHKEEPER API ====================
    
    def create_shkeeper_invoice(self, amount, coin_code):
        """Create a SHKeeper invoice while keeping the old handler return shape."""
        try:
            amount_ron = float(amount)
            usd_to_ron = float(self.config.get("usd_to_ron", 4.55))
            if usd_to_ron <= 0:
                raise ValueError("usd_to_ron must be > 0")

            amount_usd = round(amount_ron / usd_to_ron, 2)
            external_id = f"topup_{int(time.time() * 1000)}"

            if self.testing_mode:
                return {
                    "track_id": external_id,
                    "address": "SHKEEPER_TEST_ADDRESS",
                    "pay_amount": amount_usd,
                    "pay_currency": coin_code,
                    "network": coin_code,
                    "expired_at": None,
                }

            result = self.shkeeper.create_invoice(
                local_crypto=coin_code,
                external_id=external_id,
                amount_usd=amount_usd,
            )
            coin_cfg = (self.config.get("supported_crypto") or {}).get(coin_code, {})
            network = str(coin_cfg.get("network", coin_code)).replace("-", " ")
            result["network"] = network
            result["expired_at"] = result.get("recalculate_after")
            logger.info("SHKeeper topup invoice created: %s", external_id)
            return result
        except Exception as e:
            logger.exception("SHKeeper topup invoice creation failed: %s", e)
            return None

    def check_shkeeper_payment(self, track_id):
        """Return paid/pending/expired/failed/refunded for the existing checker."""
        try:
            if self.testing_mode:
                return "paid"
            result = self.shkeeper.get_invoice(str(track_id))
            return result.get("status", "pending")
        except Exception as e:
            logger.error("SHKeeper topup status check failed for %s: %s", track_id, e)
            return "pending"

    def start_invoice_checker(self):
        """Start the auto-checker worker thread"""
        if self.checker_running:
            logger.warning("Invoice checker already running")
            return
        
        self.checker_running = True
        self.checker_thread = threading.Thread(target=self._invoice_checker_loop, daemon=True)
        self.checker_thread.start()
        logger.info("🔄 Topup invoice checker started - checking every 30 seconds")
    
    def stop_invoice_checker(self):
        """Stop the auto-checker worker thread"""
        self.checker_running = False
        logger.info("🛑 Topup invoice checker stopped")
    
    def _invoice_checker_loop(self):
        """Main loop for checking pending invoices"""
        while self.checker_running:
            try:
                self._check_pending_invoices()
            except Exception as e:
                logger.error(f"Error in invoice checker loop: {e}")
            
            # Sleep for check_interval seconds
            time.sleep(self.check_interval)
    
    def _check_pending_invoices(self):
        """Check all pending invoices and process paid ones"""
        pending_invoices = self.db.get_all_pending_topup_invoices()
        
        if not pending_invoices:
            return
        
        logger.info(f"🔍 Checking {len(pending_invoices)} pending topup invoices...")
        
        for invoice in pending_invoices:
            try:
                track_id = invoice['track_id']
                
                # SANDBOX MODE: Auto-complete invoices after 60 seconds
                if self.testing_mode:
                    from datetime import datetime, timedelta
                    created_at = datetime.strptime(invoice['created_at'], '%Y-%m-%d %H:%M:%S')
                    age_seconds = (datetime.now() - created_at).total_seconds()
                    
                    logger.info(f"   🧪 SANDBOX Invoice {track_id}: age={age_seconds:.0f}s")
                    
                    if age_seconds >= 60:
                        logger.info(f"   ✅ SANDBOX: Auto-completing invoice {track_id}")
                        status = 'paid'
                    else:
                        logger.info(f"   ⏳ SANDBOX: Waiting {60-age_seconds:.0f}s more...")
                        continue
                else:
                    # PRODUCTION MODE: Check actual payment status
                    status = self.check_shkeeper_payment(track_id)
                    logger.debug(f"   Invoice {track_id}: {status}")
                
                if status == 'paid':
                    self._process_paid_invoice(invoice)
                elif status in ['expired', 'failed', 'refunded']:
                    # Mark as cancelled/failed
                    self.db.cancel_topup_invoice(invoice['id'], invoice['user_id'])
                    logger.info(f"Invoice {track_id} marked as {status}")
                    
            except Exception as e:
                logger.error(f"Error checking invoice {invoice['track_id']}: {e}")
    
    def _notify_admin_topup(self, user_id, amount, new_balance, track_id):
        """Notify admin(s) about a successful topup"""
        try:
            # Get user info
            user = self.db.get_or_create_user(user_id)
            username = user.get('username', 'N/A')
            full_name = user.get('full_name', 'Unknown')
            
            currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
            
            # Build admin notification
            admin_notification = f"""💰 <b>Am primit o noua plata!</b>

👤 <b>User:</b> {full_name}
🆔 <b>User ID:</b> <code>{user_id}</code>
📱 <b>Username:</b> @{username if username != 'N/A' else 'No username'}

💵 <b>Suma:</b> {currency_symbol}{amount:.2f}
💳 <b>Balanta:</b> {currency_symbol}{new_balance:.2f}

🔖 <b>Hash ID:</b> <code>{track_id}</code>

✅ Plata a fost confirmata si banii au fost virati."""
            
            # Send to all admins
            for admin_id in self.config.get('admin_ids', []):
                try:
                    
                    self.bot.send_message(
                        chat_id=admin_id,
                        text=admin_notification,
                        parse_mode='HTML'
                    )
                    logger.info(f"📨 Admin {admin_id} notified of topup from user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to notify admin {admin_id}: {e}")
                    
        except Exception as e:
            logger.error(f"Error building admin topup notification: {e}")
    
    def _process_paid_invoice(self, invoice):
        """Credit a confirmed topup exactly once and apply the configured deposit fee."""
        user_id = invoice['user_id']
        amount = float(invoice['amount'])
        track_id = invoice['track_id']
        pay_currency = invoice.get('pay_currency', 'CRYPTO')

        fee_percent = float((self.config.get('fees') or {}).get('deposit', 0))
        platform_fee = round(amount * fee_percent / 100.0, 2)
        credited_amount = round(amount - platform_fee, 2)
        if credited_amount <= 0:
            logger.error("Invalid credited amount for topup %s", track_id)
            return

        # database.py is patched so this UPDATE succeeds only while status='pending'.
        if not self.db.mark_topup_invoice_paid(track_id):
            logger.info("Topup %s was already processed or is no longer pending", track_id)
            return

        balance_before = self.db.get_user_balance(user_id)
        if not self.db.add_user_balance(user_id, credited_amount):
            logger.critical("Invoice %s marked paid but balance credit failed", track_id)
            return

        new_balance = self.db.get_user_balance(user_id)
        self.db.add_wallet_transaction(
            user_id=user_id,
            transaction_type="DEPOSIT",
            amount=credited_amount,
            balance_before=balance_before,
            balance_after=new_balance,
            description=f"Crypto topup ({pay_currency})",
            reference_id=track_id
        )
        if platform_fee:
            self.db.add_platform_fee("deposit", platform_fee)

        currency_symbol = self.config.get('currency', {}).get('symbol', 'RON')
        notification_text = f"""🎉 <b>Au intrat banii!</b>
✅ Plata ta a fost confirmată.

💰 <b>Depozitat:</b> {currency_symbol}{amount:.2f}
💸 <b>Taxă:</b> {currency_symbol}{platform_fee:.2f}
➕ <b>Creditat:</b> {currency_symbol}{credited_amount:.2f}
💳 <b>Balanță nouă:</b> {currency_symbol}{new_balance:.2f}"""
        try:
            self.bot.send_message(chat_id=user_id, text=notification_text, parse_mode='HTML')
            self._notify_admin_topup(user_id, credited_amount, new_balance, track_id)
        except Exception as e:
            logger.error("Error notifying user %s: %s", user_id, e)

