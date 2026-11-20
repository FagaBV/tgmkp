import telebot
import logging
import html
import sqlite3
import json
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class DisputeHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
    

    # ==================== TRUST SCORE & AVERTISMENTE ====================
        
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
          
    def handle_warn_user(self, call):

        try:

            if not self.db.is_admin(
                call.from_user.id,
                self.config['admin_ids']
            ):
                return

            dispute_id = int(
                call.data.replace(
                    'warn_user_',
                    ''
                )
            )

            dispute = self.db.get_dispute_by_id(
                dispute_id
            )

            if not dispute:
                return

            import sqlite3

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE users
                SET warnings =
                COALESCE(warnings, 0) + 1
                WHERE user_id = ?
                """,
                (dispute['user_id'],)
            )

            conn.commit()

            cursor.execute(
                """
                SELECT warnings
                FROM users
                WHERE user_id = ?
                """,
                (dispute['user_id'],)
            )

            row = cursor.fetchone()

            warnings = int(row[0])

            # AUTO BAN
            if warnings >= 3:

                cursor.execute(
                    """
                    UPDATE users
                    SET banned = 1
                    WHERE user_id = ?
                    """,
                    (dispute['user_id'],)
                )

                conn.commit()

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                f"⚠️ Avertisment acordat ({warnings}/3)"
            )

            try:

                self.bot.send_message(
                    dispute['user_id'],
                    f"⚠️ Ai primit un avertisment.\n\n"
                    f"Avertismente: {warnings}/3"
                )

                if warnings >= 3:

                    self.bot.send_message(
                        dispute['user_id'],
                        "⛔ Ai fost blocat "
                        "de la folosirea botului."
                    )

            except:
                pass

        except Exception as e:

            logger.error(
                f"Warn user error: {e}"
            )      
    
    # ==================== USER DISPUTE FLOW ====================
    
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
    
    def handle_disputes_menu(self, call):
        """Handle disputes button click - show dispute menu"""
        user_id = call.from_user.id

        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error")
            return

        lang_code = user['language_code']
        texts = self.language.get_text('disputes', lang_code)

        text = f"{texts.get('title', '⚠️ Centru Tichete')}\n\n"
        text += "Alege o optiune:"

        markup = telebot.types.InlineKeyboardMarkup()

        # New dispute button
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=texts.get('new_dispute', '➕ Nou'),
                callback_data="dispute_new"
            )
        )

        # View my disputes button
        markup.row(
            telebot.types.InlineKeyboardButton(
                text=texts.get('view_my_disputes', '📋 Tichete'),
                callback_data="dispute_my_list"
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
            'disputes_menu',
            text,
            markup
        )

        if hasattr(call, 'id') and call.id is not None:
            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
    
    def show_order_selection(self, call):
        """Show user's orders to select for dispute"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('disputes', lang_code)
        
        # Get user's recent orders from delivery_queue
        orders = self._get_user_orders(user_id)
        
        text = f"{texts.get('title', '⚠️ Centru Tichete')}\n\n"
        text += f"{texts.get('select_order', 'Selecteaza o comanda pentru initiere tichet:')}\n"
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        if not orders:
            text += f"\n{texts.get('no_orders', '📭 Nu ai comenzi pentru a deschide tichet.')}"
        else:
            for order in orders:
                order_id = order['id']
                order_type = order['type']
                status = order['status']
                total = order['total']
                
                currency_symbol = self.config.get('currency', {}).get('symbol', '$')
                
                # Check if order already has dispute
                has_dispute = self.db.get_open_dispute_for_order(user_id, order_id, order_type)
                
                if has_dispute:
                    btn_text = f"⚠️ #{order_id} - {currency_symbol}{total:.2f} (TICHET)"
                    callback = "ignore"
                else:
                    btn_text = f"📦 #{order_id} - {currency_symbol}{total:.2f} ({status})"
                    callback = f"dispute_order_{order_type}_{order_id}"
                
                markup.row(telebot.types.InlineKeyboardButton(
                    text=btn_text,
                    callback_data=callback
                ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text=texts.get('back_to_disputes', '🔙 Inapoi'),
            callback_data="menu_disputes"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing order selection: {e}")
    
    def show_dispute_type_selection(self, call, order_type, order_id):
        """Show dispute type selection"""
        user_id = call.from_user.id
                
        # ================= TRUST SCORE  =================

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
            (user_id,)
        )

        row = cursor.fetchone()

        warnings = 0

        if row:
            warnings = int(row[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM selling_history
            WHERE user_id = ?
            """,
            (user_id,)
        )

        orders = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM reviews
            WHERE user_id = ?
            """,
            (user_id,)
        )

        reviews = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM disputes
            WHERE user_id = ?
            """,
            (user_id,)
        )

        disputes_count = int(
            cursor.fetchone()[0]
        )

        trust_score = self.calculate_trust_score(
            orders,
            reviews,
            disputes_count,
            warnings
        )

        if trust_score < 15:

            conn.close()

            self.bot.answer_callback_query(
                call.id,
                "❌ Ai nevoie de minim 15% Trust Score pentru a deschide tichete."
            )

            return       
               
        # ================= LIMITA TIMP TICHET =================

        from datetime import datetime

        cursor.execute(
            """
            SELECT completed_date
            FROM selling_history
            WHERE id = ?
            """,
            (order_id,)
        )

        order_row = cursor.fetchone()

        conn.close()

        if order_row and order_row[0]:

            try:

                order_time = datetime.strptime(
                    order_row[0],
                    "%Y-%m-%d %H:%M:%S"
                )

                now = datetime.now()

                seconds_passed = (
                    now - order_time
                ).total_seconds()

                if seconds_passed > 7200:

                    self.bot.answer_callback_query(
                        call.id,
                        "❌ Nu mai poti deschide tichet dupa 2 ore de la comanda."
                    )

                    return

            except Exception as e:

                logger.error(
                    f"Time check error: {e}"
                )       
       
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('disputes', lang_code)
        dispute_types = texts.get('dispute_types', {})
        
        text = f"{texts.get('title', '⚠️ Centru Tichete')}\n\n"
        text += f"📦 <b>Comanda:</b> #{order_id}\n\n"
        text += texts.get('select_type', 'Selecteaza tipul tichetului:')
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        types = [
            ('refund', dispute_types.get('refund', '💰 Cere un refund')),
            ('other', dispute_types.get('other', '❓ Alta problema')),
            ('cancel', dispute_types.get('cancel', '❌ Anuleaza Comanda')),
        ]
        
        for type_id, type_text in types:
            markup.row(telebot.types.InlineKeyboardButton(
                text=type_text,
                callback_data=f"dispute_type_{order_type}_{order_id}_{type_id}"
            ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data="dispute_new"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing dispute type selection: {e}")

    def prompt_dispute_message(self, call, order_type, order_id, dispute_type):
        """Prompt user to enter dispute message"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('disputes', lang_code)
        
        text = texts.get('enter_message', '📝 Descrie Problema [O DATA TRIMIS, CHAT-UL NU SE MAI POATE MODIFICA]:')
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text="❌ Cancel",
            callback_data="menu_disputes"
        ))
        
        # Set user state to expect dispute message
        self.db.set_user_state(user_id, 'dispute_message', {
            'order_type': order_type,
            'order_id': order_id,
            'dispute_type': dispute_type,
            'message_id': call.message.message_id
        })
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error prompting dispute message: {e}")
    
    def handle_text_input(self, message):
        """Handle text input for dispute message"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or user_state['state'] != 'dispute_message':
            return False
        
        data = user_state.get('data', {})
        order_type = data.get('order_type')
        order_id = data.get('order_id')
        dispute_type = data.get('dispute_type')
        
        dispute_message = message.text.strip()
        
        if len(dispute_message) < 10:
            
            self.bot.send_message(
                message.chat.id,
                "❌ Te rog scrie motivul pentru care ai deschis tichetul (minim 10 caractere)."
            )
            return True
        
        # Clear state
        self.db.clear_user_state(user_id)
        
        # Create dispute
        dispute_id = self.db.create_dispute(
            user_id=user_id,
            order_id=order_id,
            order_type=order_type,
            dispute_type=dispute_type,
            message=dispute_message
        )
        
        if dispute_id:
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'en'
            texts = self.language.get_text('disputes', lang_code)
            
            # Send confirmation to user
            confirm_text = texts.get('dispute_created', '✅ Tichet creat!')
            confirm_text = confirm_text.format(id=dispute_id)
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(telebot.types.InlineKeyboardButton(
                text="🔙 Inapoi",
                callback_data="main_menu"
            ))
            
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=confirm_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            
            # Notify admins
            self._notify_admins_new_dispute(dispute_id, user_id, order_id, order_type, dispute_type, dispute_message)
        else:
            
            self.bot.send_message(
                message.chat.id,
                "❌ Error creating dispute. Please try again."
            )
        
        return True
            
    def show_my_disputes(self, call):
        """Show user's disputes"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('disputes', lang_code)
        
        disputes = self.db.get_user_disputes(user_id)
        
        text = f"{texts.get('my_disputes', '📋 Tichete')}\n\n"
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        if not disputes:
            text += texts.get('no_disputes', '✅ Fara tichete.')
        else:
            for dispute in disputes:
                status_emoji = "🟢" if dispute['status'] == 'resolved' else "🟡"
                dispute_types = texts.get('dispute_types', {})
                type_name = dispute_types.get(dispute['dispute_type'], dispute['dispute_type'])
                
                item_text = texts.get('dispute_item', '🎫 #{id} - {type}')
                text += item_text.format(
                    id=dispute['id'],
                    type=type_name,
                    order_id=dispute['order_id'],
                    date=dispute['created_at'][:10] if dispute['created_at'] else 'Unknown',
                    status=f"{status_emoji} {dispute['status'].capitalize()}"
                ) + "\n\n"
                
                markup.row(telebot.types.InlineKeyboardButton(
                    text=f"🎫 #{dispute['id']} - {texts.get('view_dispute', 'View')}",
                    callback_data=f"dispute_view_{dispute['id']}"
                ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text=texts.get('back_to_disputes', '🔙 Inapoi'),
            callback_data="menu_disputes"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing my disputes: {e}")
    
    def show_dispute_details(self, call, dispute_id):
        """Show dispute details to user"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('disputes', lang_code)
        
        dispute = self.db.get_dispute_by_id(dispute_id)
                
        import sqlite3

        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT warnings
            FROM users
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        user_row = cursor.fetchone()

        warnings = 0

        if user_row:
            warnings = int(user_row[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM selling_history
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        orders = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM reviews
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        reviews = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM disputes
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        disputes_count = int(cursor.fetchone()[0])

        conn.close()

        trust_score = self.calculate_trust_score(
            orders,
            reviews,
            disputes_count,
            warnings
        )        
        
        if not dispute or dispute['user_id'] != user_id:
            self.bot.answer_callback_query(call.id, "❌ Dispute not found")
            return
        
        dispute_types = texts.get('dispute_types', {})
        type_name = dispute_types.get(dispute['dispute_type'], dispute['dispute_type'])
        
        status_emoji = "✅" if dispute['status'] == 'resolved' else "⏳"
        trust_emoji = "🟢"
        
        if trust_score < 70:
            trust_emoji = "🟡"
            
        if trust_score < 40:
            trust_emoji = "🔴"
        
        text = f"🎫 <b>Tichet #{dispute['id']}</b>\n\n"
        text += f"📦 <b>Comanda:</b> #{dispute['order_id']} ({dispute['order_type']})\n"
        text += f"⚠️ <b>Tip:</b> {type_name}\n"
        text += f"📅 <b>Creat:</b> {dispute['created_at'][:10] if dispute['created_at'] else 'Unknown'}\n"
        text += f"📊 <b>Status:</b> {status_emoji} {dispute['status'].capitalize()}\n\n"
        text += f"📈 <b>Trust Score:</b> {trust_emoji}{trust_score}%\n"
        text += f"⚠️ <b>Avertismente:</b> {warnings}/3\n"
        text += f"💬 <b>Mesaj :</b>\n{dispute['message']}\n\n"        
        
        if dispute['status'] == 'resolved' and dispute['admin_response']:
            text += f"\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            text += f"✅ <b>Raspuns Admin:</b>\n{dispute['admin_response']}\n"
            text += f"📅 <b>Rezolvat:</b> {dispute['resolved_at'][:10] if dispute['resolved_at'] else 'Unknown'}"
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text=texts.get('back_to_disputes', '🔙 Inapoi'),
            callback_data="dispute_my_list"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing dispute details: {e}")
    
    # ==================== ADMIN DISPUTE MANAGEMENT ====================
    
    def show_admin_disputes(self, call):
        """Show all open disputes for admin"""
        user_id = call.from_user.id
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('admin_disputes', lang_code)
        
        disputes = self.db.get_all_open_disputes()
        
        text = f"{texts.get('title', '🎫 Manager Tichete')}\n\n"
        
        if not disputes:
            text += texts.get('no_disputes', '✅ Nu exista tichete deschise.')
        else:
            count_text = texts.get('dispute_count', '{count} tichete')
            text += count_text.format(count=len(disputes)) + "\n\n"
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        for dispute in disputes:
            username = dispute['username'] or 'Unknown'
            dispute_types = self.language.get_text('disputes', lang_code).get('dispute_types', {})
            type_name = dispute_types.get(dispute['dispute_type'], dispute['dispute_type'])
            
            btn_text = f"🎫 #{dispute['id']} - @{username} - {type_name[:15]}"
            markup.row(telebot.types.InlineKeyboardButton(
                text=btn_text,
                callback_data=f"admin_dispute_view_{dispute['id']}"
            ))
        
        # Back button
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data="admin_panel"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing admin disputes: {e}")
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    def show_admin_dispute_full(self, call, dispute_id):
        """Show full dispute details to admin"""
        user_id = call.from_user.id
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('admin_disputes', lang_code)
        dispute_texts = self.language.get_text('disputes', lang_code)
        
        dispute = self.db.get_dispute_by_id(dispute_id)

        import sqlite3 
        
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT warnings
            FROM users
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        user_row = cursor.fetchone()

        warnings = 0

        if user_row:
            warnings = int(user_row[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM selling_history
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        orders = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM reviews
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        reviews = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM disputes
            WHERE user_id = ?
            """,
            (dispute['user_id'],)
        )

        disputes_count = int(cursor.fetchone()[0])

        conn.close()

        trust_score = self.calculate_trust_score(
            orders,
            reviews,
            disputes_count,
            warnings
        )        
        
        if not dispute:
            self.bot.answer_callback_query(call.id, "❌ Ticket de ne gasit")
            return

        
        dispute_types = dispute_texts.get('dispute_types', {})
        type_name = dispute_types.get(dispute['dispute_type'], dispute['dispute_type'])
        username = dispute['username'] or 'Unknown'
        
        safe_message = html.escape(
            str(dispute['message'])
        )

        safe_username = html.escape(
            str(username)
        )        
        
        full_text = texts.get(
            'full_dispute',
            '🎫 Problema #{id}'
        )

        text = full_text.format(
            id=dispute['id'],
            username=safe_username,
            user_id=dispute['user_id'],
            order_id=dispute['order_id'],
            order_type=dispute['order_type'],
            type=type_name,
            date=dispute['created_at'][:19]
                if dispute['created_at']
                else 'Unknown',
            trust_score=trust_score,
            warnings=warnings,
            message=safe_message
        )       
        markup = telebot.types.InlineKeyboardMarkup()
        
        if dispute['status'] == 'open':
            markup.row(telebot.types.InlineKeyboardButton(
                text=texts.get('resolve_button', '✅ Rezolva'),
                callback_data=f"admin_dispute_resolve_{dispute_id}"
            ))
            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="⚠️ Avertisment",
                    callback_data=f"warn_user_{dispute['id']}"
                )
            )            
        
        if dispute['dispute_type'].lower() == 'refund':

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="🧾 10% Refund",
                    callback_data=f"refund_10_{dispute_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    text="💳 25% Refund",
                    callback_data=f"refund_25_{dispute_id}"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="💸 50% Refund",
                    callback_data=f"refund_50_{dispute_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    text="💰 100% Refund",
                    callback_data=f"refund_100_{dispute_id}"
                )
            )
       
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data="admin_disputes"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error showing admin dispute full: {e}")
    
    def prompt_admin_response(self, call, dispute_id):
        """Prompt admin to enter resolution response"""
        user_id = call.from_user.id
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied")
            return
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('admin_disputes', lang_code)
        
        text = texts.get('enter_response', '📝 Adauga raspuns:')
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text="❌ Cancel",
            callback_data=f"admin_dispute_view_{dispute_id}"
        ))
        
        # Set admin state
        self.db.set_user_state(user_id, 'admin_dispute_response', {
            'dispute_id': dispute_id,
            'message_id': call.message.message_id
        })
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error prompting admin response: {e}")
        
    def handle_refund_callback(self, call):

        try:

            user_id = call.from_user.id

            if not self.db.is_admin(
                user_id,
                self.config['admin_ids']
            ):
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Access denied"
                )
                return

            parts = call.data.split("_")

            percent = int(parts[1])
            dispute_id = int(parts[2])

            dispute = self.db.get_dispute_by_id(
                dispute_id
            )

            if not dispute:

                self.bot.answer_callback_query(
                    call.id,
                    "❌ Tichet inexistent"
                )

                return

            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            cursor.execute(
                "SELECT total_cost FROM selling_history WHERE id = ?",
                (dispute['order_id'],)
            )

            row = cursor.fetchone()

            conn.close()

            if not row:

                self.bot.answer_callback_query(
                    call.id,
                    "❌ Order not found"
                )

                return

            order_total = float(row[0])            
            
            refund_amount = (
                order_total * (percent / 100)
            )

            target_user = int(
                dispute['user_id']
            )

            self.db.add_to_balance(
                target_user,
                refund_amount
            )

            self.db.set_user_state(
                user_id,
                'admin_dispute_response',
                {
                    'dispute_id': dispute_id,
                    'refund_percent': percent,
                    'refund_amount': refund_amount
                }
            )

            self.bot.answer_callback_query(
                call.id,
                f"✅ Refund {percent}% trimis"
            )

            
            self.bot.send_message(
                target_user,
                f"💰 Ai primit refund "
                f"{percent}% "
                f"({refund_amount:.2f} RON)"
            )

        except Exception as e:

            logger.error(
                f"Refund error: {e}"
            )

            self.bot.answer_callback_query(
                call.id,
                "❌ Refund failed"
            )    
    
    def handle_admin_text_input(self, message):
        """Handle admin text input for dispute resolution"""
        user_id = message.from_user.id
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or user_state['state'] != 'admin_dispute_response':
            return False
        
        data = user_state.get('data', {})
        dispute_id = data.get('dispute_id')
        
        admin_response = message.text.strip()
        refund_percent = data.get('refund_percent')
        refund_amount = data.get('refund_amount')

        if refund_amount:

            admin_response = (
                f"Refund acordat: "
                f"{refund_percent}% "
                f"({refund_amount:.2f} RON)\n\n"
                f"{admin_response}"
            )
        
        # Clear state
        self.db.clear_user_state(user_id)
        
        # Resolve dispute
        if self.db.resolve_dispute(dispute_id, user_id, admin_response):
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'en'
            texts = self.language.get_text('admin_disputes', lang_code)
            
            success_text = texts.get('resolved_success', '✅ Tichet rezolvat!')
            success_text = success_text.format(id=dispute_id)
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(telebot.types.InlineKeyboardButton(
                text="🔙 Back to Disputes",
                callback_data="admin_disputes"
            ))
            
            
            self.bot.send_message(
                chat_id=message.chat.id,
                text=success_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
            
            # Notify user
            self._notify_user_dispute_resolved(dispute_id, admin_response)
        else:
            
            self.bot.send_message(
                message.chat.id,
                "❌ Error resolving dispute. Please try again."
            )
        
        return True
    
    # ==================== CALLBACKS ====================
    
    def handle_disputes_callbacks(self, call):
        """Handle dispute-related callbacks"""
        data = call.data
        
        if data == 'dispute_new':
            self.show_order_selection(call)
        elif data == 'dispute_my_list':
            self.show_my_disputes(call)
        elif data.startswith('dispute_order_'):
            # dispute_order_{order_type}_{order_id}
            parts = data.split('_')
            order_type = parts[2]
            order_id = int(parts[3])
            self.show_dispute_type_selection(call, order_type, order_id)
        elif data.startswith('dispute_type_'):
            # dispute_type_{order_type}_{order_id}_{dispute_type}
            parts = data.split('_')
            order_type = parts[2]
            order_id = int(parts[3])
            dispute_type = parts[4]
            self.prompt_dispute_message(call, order_type, order_id, dispute_type)
        elif data.startswith('dispute_view_'):
            dispute_id = int(data.replace('dispute_view_', ''))
            self.show_dispute_details(call, dispute_id)
        elif data == 'admin_disputes':
            self.show_admin_disputes(call)
        elif data.startswith('admin_dispute_view_'):
            dispute_id = int(data.replace('admin_dispute_view_', ''))
            self.show_admin_dispute_full(call, dispute_id)
        elif data.startswith('admin_dispute_resolve_'):
            dispute_id = int(data.replace('admin_dispute_resolve_', ''))
            self.prompt_admin_response(call, dispute_id)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
    
    # ==================== HELPERS ====================
    
    def _get_user_orders(self, user_id):
        """Get user's orders that can be disputed"""
        orders = []
        
        try:
            with self.db.pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get from delivery_queue (pending/delivered orders)
                cursor.execute('''
                    SELECT id, 'deliverable' as type, status, total_cost
                    FROM delivery_queue
                    WHERE user_id = ? AND status IN ('pending', 'delivered', 'paid')
                    ORDER BY order_date DESC
                    LIMIT 10
                ''', (user_id,))
                
                for row in cursor.fetchall():
                    orders.append({
                        'id': row[0],
                        'type': row[1],
                        'status': row[2],
                        'total': row[3]
                    })
                
                # Get from selling_history (completed orders - for refund requests)
                cursor.execute('''
                    SELECT id, 'digital' as type, 'completed' as status, total_cost
                    FROM selling_history
                    WHERE user_id = ?
                    ORDER BY completed_date DESC
                    LIMIT 5
                ''', (user_id,))
                
                for row in cursor.fetchall():
                    orders.append({
                        'id': row[0],
                        'type': row[1],
                        'status': row[2],
                        'total': row[3]
                    })
                
        except Exception as e:
            logger.error(f"Error getting user orders: {e}")
        
        return orders
    
    def _notify_admins_new_dispute(self, dispute_id, user_id, order_id, order_type, dispute_type, message):
        """Notify admins about new dispute"""
        admin_ids = self.config.get('admin_ids', [])
        
        # Get user info
        user = self.db.get_or_create_user(user_id)
        username = user.get('username', 'Unknown') if user else 'Unknown'
        
        import sqlite3

        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT warnings
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        )

        user_row = cursor.fetchone()

        warnings = 0

        if user_row:
            warnings = int(user_row[0] or 0)

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM selling_history
            WHERE user_id = ?
            """,
            (user_id,)
        )

        orders = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM reviews
            WHERE user_id = ?
            """,
            (user_id,)
        )

        reviews = int(cursor.fetchone()[0])

        cursor.execute(
            """
            SELECT COUNT(*)
            FROM disputes
            WHERE user_id = ?
            """,
            (user_id,)
        )

        disputes_count = int(cursor.fetchone()[0])

        conn.close()

        trust_score = self.calculate_trust_score(
            orders,
            reviews,
            disputes_count,
            warnings
        )        
        
        
        text = f"""🚨 <b>Tichet Nou!</b>

🎫 <b>ID:</b> #{dispute_id}
👤 <b>Utilizator:</b> @{username} (ID: {user_id})
📦 <b>Comanda:</b> #{order_id} ({order_type})
⚠️ <b>Tip:</b> {dispute_type.upper()}

📈 <b>Trust Score:</b> {trust_score}
⚠️ <b>Avertismente:</b> {warnings}

💬 <b>Mesaj:</b>

{message}

Apasa mai jos pentru a rezolva tichetul."""
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text="🎫 Tichete",
            callback_data="admin_disputes"
        ))
        
        for admin_id in admin_ids:
            try:
                
                self.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error notifying admin {admin_id}: {e}")
    
    def _notify_user_dispute_resolved(self, dispute_id, admin_response):
        """Notify user that their dispute was resolved"""
        dispute = self.db.get_dispute_by_id(dispute_id)
        
        if not dispute:
            return
        
        user_id = dispute['user_id']
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'
        texts = self.language.get_text('disputes', lang_code)
        
        resolved_text = texts.get('dispute_resolved', '✅ Dispute Resolved!')
        resolved_text = resolved_text.format(id=dispute_id, response=admin_response)
        
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(telebot.types.InlineKeyboardButton(
            text="🔙 Back to Menu",
            callback_data="main_menu"
        ))
        
        try:
            
            self.bot.send_message(
                chat_id=user_id,
                text=resolved_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error notifying user {user_id}: {e}")
