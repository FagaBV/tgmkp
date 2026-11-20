import telebot
import json
import logging
import time
import sqlite3

from telegram_client_optimized import TelebotOptimizedWrapper
from handlers.start_handler import StartHandler
from handlers.menu_handler import MenuHandler
from handlers.admin_handler import AdminHandler
from handlers.category_handler import CategoryHandler
from handlers.product_handler import ProductHandler
from handlers.cashout_handler import CashoutHandler
from handlers.currency_handler import CurrencyHandler
from handlers.shopping_handler import ShoppingHandler
from handlers.cart_handler import CartHandler
from handlers.payment_handler import PaymentHandler
from handlers.review_handler import ReviewHandler
from handlers.cleanup_handler import CleanupHandler
from handlers.history_handler import HistoryHandler
from handlers.order_management_handler import OrderManagementHandler
from handlers.admin_command_handler import AdminCommandHandler
from handlers.topup_handler import TopupHandler
from handlers.reviews_handler import ReviewsHandler
from handlers.profile_handler import ProfileHandler
from handlers.dispute_handler import DisputeHandler
from handlers.seller_handler import SellerHandler
from handlers.button_editor_handler import ButtonEditorHandler
from heartbeat_handler import HeartbeatHandler
from database import Database
from language import Language
from private_bot_manager import PrivateBotManager
from handlers.private_bot_handler import PrivateBotHandler


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Simple optimization: Set default timeouts for all requests
def setup_request_optimizations():
    """Set up simple request optimizations that work with all versions"""
    logger.info("🚀 Setting up request optimizations...")
    
    # Set default timeout for all requests to prevent hanging
    import socket
    socket.setdefaulttimeout(10)  # 10 second timeout for all socket operations
    
    logger.info("✅ Request timeout set to 10 seconds - no more 15s hangs!")
    return True

class ShopBot:
    def __init__(self, bot_token_override=None, private_owner_id=None, enable_private_bot_manager=True):
        # Load configuration
        with open('config.json', 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.private_owner_id = private_owner_id
        self.is_private_instance = bot_token_override is not None
        self.config['_private_instance'] = self.is_private_instance
        self.config['_private_owner_id'] = private_owner_id
        runtime_bot_token = bot_token_override or self.config['bot_token']
        logger.info(f"ADMINS: {self.config['admin_ids']}")
        
        # Set up request optimizations (prevents 15s hangs)
        setup_request_optimizations()
        
        # Initialize bot with our optimized HTTP client for MUCH faster API calls
        logger.info("🚀 Initializing bot with OptimizedTelegramClient...")
        self.bot = TelebotOptimizedWrapper(
            runtime_bot_token,
            threaded=True,  # Enable threading for better performance
            num_threads=4,  # Increase thread pool for handling multiple requests
            skip_pending=False  # Keep pending updates to preserve commands after restart
        )
        logger.info("✅ OptimizedTelegramClient initialized - API calls should be MUCH faster now!")
        
        # Pre-warm the API connection to prevent cold start delays
        logger.info("🔥 Pre-warming API connection...")
        if self.bot.warm_connection():
            logger.info("✅ API connection pre-warmed successfully!")
        else:
            logger.warning("⚠️ API pre-warming failed, but bot will continue")
        
        # Initialize database
        self.db = Database()
        
        # Initialize language system
        self.language = Language()
        
        # Preload JSON files for performance
        from json_cache import preload_common_files
        preload_common_files()
        
        # Initialize handlers
        self.start_handler = StartHandler(self.bot, self.db, self.language, self.config)
        self.menu_handler = MenuHandler(self.bot, self.db, self.language, self.config)
        self.admin_handler = AdminHandler(self.bot, self.db, self.language, self.config)
        self.start_handler.menu_handler = self.menu_handler
        self.cashout_handler = CashoutHandler(self.bot, self.db, self.language, self.config)
        self.category_handler = CategoryHandler(self.bot, self.db, self.language, self.config)
        self.product_handler = ProductHandler(self.bot, self.db, self.language, self.config)
        self.seller_handler = SellerHandler(self.bot, self.db, self.language, self.config)
        self.currency_handler = CurrencyHandler(self.bot, self.db, self.language, self.config)
        self.shopping_handler = ShoppingHandler(self.bot, self.db, self.language, self.config)
        self.cart_handler = CartHandler(self.bot, self.db, self.language, self.config)
        self.payment_handler = PaymentHandler(self.bot, self.db, self.language, self.config)
        self.review_handler = ReviewHandler(self.bot, self.db, self.language, self.config)
        self.cleanup_handler = CleanupHandler(self.bot, self.db, self.language, self.config)
        self.history_handler = HistoryHandler(self.bot, self.db, self.language, self.config)
        self.order_management_handler = OrderManagementHandler(self.bot, self.db, self.language, self.config)
        self.admin_command_handler = AdminCommandHandler(self.bot, self.db, self.language, self.config)
        self.topup_handler = TopupHandler(self.bot, self.db, self.language, self.config)
        self.reviews_handler = ReviewsHandler(self.bot, self.db, self.language, self.config)
        self.dispute_handler = DisputeHandler(self.bot, self.db, self.language, self.config)
        self.button_editor_handler = ButtonEditorHandler(self.bot, self.db, self.language, self.config)
        
        
        # Initialize high-frequency heartbeat to prevent cold sleep and keep API warm
        self.heartbeat_handler = HeartbeatHandler(self.db, self.bot, interval=10)  # Every 10 seconds - more aggressive
        
        # Set cross-references between handlers
        self.admin_handler.category_handler = self.category_handler
        self.admin_handler.product_handler = self.product_handler
        self.admin_handler.currency_handler = self.currency_handler
        self.admin_handler.payment_handler = self.payment_handler
        self.admin_handler.order_management_handler = self.order_management_handler
        self.admin_handler.dispute_handler = self.dispute_handler
        self.admin_handler.button_editor_handler = self.button_editor_handler
        self.menu_handler.cart_handler = self.cart_handler
        self.profile_handler = ProfileHandler(
            self.bot,
            self.db,
            self.config,
            self.language
        )        
        self.private_bot_manager = None
        if enable_private_bot_manager and not self.is_private_instance and self.config.get('private_bots', {}).get('enabled', True):
            self.private_bot_manager = PrivateBotManager(
                self.db, self.config, app_factory=self._create_private_bot_app
            )

        self.private_bot_handler = PrivateBotHandler(
            self.bot, self.db, self.language, self.config,
            manager=self.private_bot_manager,
            is_private_instance=self.is_private_instance,
        )

        # Register handlers
        self.register_handlers()
        if self.private_bot_manager is not None:
            self.private_bot_manager.start_existing_async()
    
    def _create_private_bot_app(self, token, owner_user_id):
        return ShopBot(
            bot_token_override=token,
            private_owner_id=owner_user_id,
            enable_private_bot_manager=False,
        )

    def register_handlers(self):
        # PRIVATE BOT OWNER GUARD
        if self.is_private_instance and self.private_owner_id and self.config.get('private_bots', {}).get('owner_only', True):
            @self.bot.message_handler(func=lambda message: bool(getattr(message, 'from_user', None)) and message.from_user.id != self.private_owner_id)
            def deny_non_owner_message(message):
                self.bot.send_message(message.chat.id, "🔒 Acest bot personal este disponibil doar proprietarului său.")

            @self.bot.callback_query_handler(func=lambda call: bool(getattr(call, 'from_user', None)) and call.from_user.id != self.private_owner_id)
            def deny_non_owner_callback(call):
                self.bot.answer_callback_query(call.id, "🔒 Bot personal privat.", show_alert=True)

        """Register all bot handlers"""
        # Admin Start Command
        @self.bot.message_handler(commands=['amenu'])
        def handle_admin_menu_command(message):

            user_id = message.from_user.id

            if not self.db.is_admin(
                user_id,
                self.config.get('admin_ids', [])
            ):
                self.bot.send_message(
                    message.chat.id,
                    "❌ Acces interzis. Această comandă este disponibilă doar administratorilor."
                )
                return

            self.admin_handler.handle_admin_panel_from_message(
                message
            )
        # Start command
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            self.start_handler.handle_start(message)
            self.menu_handler.handle_main_menu_keyboard(message)

            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT is_banned
                FROM users
                WHERE user_id = ?
                """,
                (message.from_user.id,)
            )

            row = cursor.fetchone()

            conn.close()

            if row and int(row[0]) == 1:

                self.bot.send_message(
                    message.chat.id,
                    "🚫 Accesul tău la bot a fost restricționat."
                )

                return

            try:
                self.menu_handler.handle_main_menu_keyboard(message)
            except Exception as e:
                logger.error(f"Refresh la /start: {e}")
        
        # Admin commands for order management
        @self.bot.message_handler(commands=['delivered'])
        def handle_delivered_command(message):
            self.admin_command_handler.handle_delivered_command(message)
        
        
        @self.bot.message_handler(commands=['completed'])
        def handle_completed_command(message):
            self.admin_command_handler.handle_completed_command(message)
        
        @self.bot.message_handler(commands=['cancelled'])
        def handle_cancelled_command(message):
            self.admin_command_handler.handle_cancelled_command(message)
        
        # Health check command (admin only)
        @self.bot.message_handler(commands=['health'])
        def handle_health_check(message):
            user_id = message.from_user.id
            if self.db.is_admin(user_id, self.config.get('admin_ids', [])):
                health = self.heartbeat_handler.get_health_status()
                status_emoji = {
                    'HEALTHY': '💚',
                    'WARNING': '⚠️', 
                    'CRITICAL': '🚨',
                    'STOPPED': '💤'
                }.get(health['status'], '❓')
                
                # Get performance stats from optimized client
                perf_stats = self.bot.get_performance_stats()
                
                health_text = f"""
                {status_emoji} **Bot Health Status**

                **Status:** {health['status']}
                **Heartbeat:** {'✅ Alive' if health['is_alive'] else '❌ Dead'}
                **Pulse Count:** {health['pulse_count']}
                **Failed Pulses:** {health['failed_pulses']}
                **Success Rate:** {health['success_rate']:.1f}%
                **Last Pulse:** {health['seconds_since_last']:.1f}s ago
                **Interval:** {health['interval']}s

                **🚀 API Performance (OptimizedClient):**
                **Total Requests:** {perf_stats['total_requests']}
                **Average Response:** {perf_stats['average_time']}s
                **Requests/Second:** {perf_stats['requests_per_second']}
                **Total API Time:** {perf_stats['total_time']}s

                **Database Pool:**
                {self.db.pool.get_stats()}
                                """.strip()               
                self.bot.send_message(message.chat.id, health_text, parse_mode='Markdown')
        
        # Performance stats command (admin only)
        @self.bot.message_handler(commands=['perf', 'performance'])
        def handle_performance_check(message):
            user_id = message.from_user.id
            if self.db.is_admin(user_id, self.config.get('admin_ids', [])):
                perf_stats = self.bot.get_performance_stats()
                
                # Calculate performance rating
                avg_time = perf_stats['average_time']
                if avg_time < 1.0:
                    rating = "🚀 EXCELLENT"
                elif avg_time < 2.0:
                    rating = "✅ GOOD"
                elif avg_time < 5.0:
                    rating = "⚠️ SLOW"
                else:
                    rating = "🚨 VERY SLOW"
                
                perf_text = f"""
                    ⚡ **API Performance Report**

                    **Performance Rating:** {rating}
                    **Average Response Time:** {avg_time:.3f}s
                    **Total API Requests:** {perf_stats['total_requests']}
                    **Total API Time:** {perf_stats['total_time']:.3f}s
                    **Throughput:** {perf_stats['requests_per_second']} req/s

                    **🎯 Performance Targets:**
                    • Excellent: < 1.0s avg
                    • Good: < 2.0s avg  
                    • Acceptable: < 5.0s avg

                    **Before optimization:** ~15s per request 😱
                    **After optimization:** ~{avg_time:.3f}s per request 🚀
                                                                """.strip()
                
                self.bot.send_message(message.chat.id, perf_text, parse_mode='Markdown')
        
        # File/photo/video handlers for product uploads + tab images
        @self.bot.message_handler(content_types=['photo', 'video', 'document'])
        def handle_file_uploads(message):
            user_id = message.from_user.id
            user = self.db.get_user(user_id)

            if not user:
                return

            # Broadcast photo upload (admin only)
            user_state = self.db.get_user_state(user_id)
            if user_state and user_state.get('state') == 'admin_broadcast_waiting_photo':
                if self.admin_handler.handle_broadcast_photo_input(message):
                    return

            # 1. Tab image upload (admin only)
            if user_state and user_state.get('state') == 'uploading_tab_image':
                try:
                    state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                    page_key = state_data['page_key']
                    page_name = state_data['page_name']
                except Exception:
                    self.db.clear_user_state(user_id)
                    self.bot.send_message(message.chat.id, "❌ Sesiunea a expirat. Încearcă din nou.")
                    return

                if not self.db.is_admin(user_id, self.config['admin_ids']):
                    self.db.clear_user_state(user_id)
                    self.bot.send_message(message.chat.id, "❌ Doar adminii pot seta poze pentru tab-uri.")
                    return

                if not message.photo:
                    self.bot.send_message(message.chat.id, "❌ Trimite o poză validă pentru acest tab.")
                    return

                file_id = message.photo[-1].file_id

                try:
                    self.admin_handler.save_tab_image(page_key, file_id)
                    self.db.clear_user_state(user_id)

                    self.bot.send_message(
                        message.chat.id,
                        f"✅ Poza pentru <b>{page_name}</b> a fost salvată.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    logger.error(f"Error saving tab image: {e}")
                    self.bot.send_message(message.chat.id, "❌ Eroare la salvarea pozei.")
                return

            # 1.5 Imaginea pentru magazinul seller-ului 
            if user_state and user_state.get('state') == 'seller_uploading_shop_image':
                if not message.photo:
                    self.bot.send_message(message.chat.id, "❌ Trimite o poză validă pentru magazin.")
                    return

                file_id = message.photo[-1].file_id
                ok = self.category_handler.update_seller_shop_image(user_id, file_id)
                self.db.clear_user_state(user_id)

                if ok:
                    self.bot.send_message(message.chat.id, "✅ Poza magazinului a fost salvată.")
                else:
                    self.bot.send_message(message.chat.id, "❌ Nu s-a putut salva poza magazinului.")
                return
           
            # 2. Product/drop upload logic
            if self.product_handler.handle_file_input(message):
                return  # File was handled by product handler
        
        # Text message handlers for keyboard buttons and input states
        @self.bot.message_handler(func=lambda message: True)
        def handle_text_messages(message):
            start_time = time.time()
            user_id = message.from_user.id
            user_data = message.from_user
            
            logger.info(f"🔍 DEBUG: Text message received from user {user_id} at {start_time:.3f}")
            logger.info(f"🔍 DEBUG: Message text: '{message.text[:50]}...' (truncated)")
            
            # Always ensure user exists atomically
            db_start = time.time()
            user = self.db.get_or_create_user(
                user_id, 
                user_data.username, 
                user_data.first_name, 
                user_data.last_name, 
                'ro'
            )
            db_time = time.time() - db_start
            logger.info(f"🔍 DEBUG: Database get_or_create_user took {db_time:.3f}s")
            
            if not user:
                # Database error
                logger.error(f"🔍 DEBUG: Database error for user {user_id}")
                self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")
                return
            
            if user['is_new']:
                # New user, redirect to start
                logger.info(f"🔍 DEBUG: New user {user_id} auto-created, redirecting to /start")
                self.start_handler.handle_start(message)
                return
            
            # Check handlers in order of specificity
            logger.info(f"🔍 DEBUG: Starting handler checks for user {user_id}")
           
            # Handler pentru categorii
            if self.category_handler.handle_seller_shop_description_input(message):
                return
            
            # 1. Product creation/editing (most specific)
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting product handler check for user {user_id} at {handler_start:.3f}")
            if self.product_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Product handler processed message in {handler_time:.3f}s")
                return
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Product handler check took {handler_time:.3f}s (not handled)")
            
            # [F2] Input pentru modificare/adaugare produse\
            if self.product_handler.handle_seller_product_input(message):
                return
            # [F2] Input pentru modificarea numelui magazinului
            if self.category_handler.handle_seller_shop_rename_input(message):
                return
            # [F2] Input produse
            if self.product_handler.handle_seller_product_edit_input(message):
                return
                
            # [F2] Routing-ul pentru seller drops
            if self.product_handler.handle_seller_drop_text_input(message):
                return
            
            # 2. Shopping custom amount input
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting shopping handler check for user {user_id} at {handler_start:.3f}")
            if self.shopping_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Shopping handler processed message in {handler_time:.3f}s")
                return  # Input was handled by shopping handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Shopping handler check took {handler_time:.3f}s (not handled)")
            
            # 3. Cart delivery address input
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting cart handler check for user {user_id} at {handler_start:.3f}")
            if self.cart_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Cart handler processed message in {handler_time:.3f}s")
                return  # Input was handled by cart handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Cart handler check took {handler_time:.3f}s (not handled)")
            
            # 3.4. Categorii seller si handlere
            if self.category_handler.handle_seller_category_input(message):
                return
            # 3.5. Button editor text input (admin editing buttons)
            handler_start = time.time()
            if self.button_editor_handler.handle_button_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Button editor handler processed message in {handler_time:.3f}s")
                return
            
            # 3.6. Topup custom amount input
            handler_start = time.time()
            if self.topup_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Topup handler processed message in {handler_time:.3f}s")
                return  # Input was handled by topup handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Topup handler check took {handler_time:.3f}s (not handled)")
            
            # 3.6. Dispute message input (user)
            if self.dispute_handler.handle_text_input(message):
                return  # Input was handled by dispute handler
                
            # 3.6.5 Seller cashout input
            if self.seller_handler.handle_text_input(message):
                return
            
            # 3.7. Admin dispute response input
            if self.dispute_handler.handle_admin_text_input(message):
                return  # Input was handled by admin dispute handler
            
            # 4. Review text input
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting review handler check for user {user_id} at {handler_start:.3f}")
            self.review_handler.handle_review_text_input(message)
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Review handler check took {handler_time:.3f}s")
            
            # 5. Category editing
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting category handler check for user {user_id} at {handler_start:.3f}")
            if self.category_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Category handler processed message in {handler_time:.3f}s")
                return  # Input was handled by category handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Category handler check took {handler_time:.3f}s (not handled)")
            
            # 6. Store settings editing (admin handler - least specific)
            handler_start = time.time()
            logger.info(f"🔍 DEBUG: Starting admin handler check for user {user_id} at {handler_start:.3f}")
            if self.admin_handler.handle_text_input(message):
                handler_time = time.time() - handler_start
                logger.info(f"🔍 DEBUG: Admin handler processed message in {handler_time:.3f}s")
                return  # Input was handled by admin handler
            handler_time = time.time() - handler_start
            logger.info(f"🔍 DEBUG: Admin handler check took {handler_time:.3f}s (not handled)")
            
            lang_code = user['language_code']
            text = message.text
            
            # Check for main menu button
            menu_check_start = time.time()
            logger.info(f"🔍 DEBUG: Starting language text lookup for user {user_id} with lang_code '{lang_code}' at {menu_check_start:.3f}")
            
            lang_start = time.time()
            main_menu_text = self.language.get_text('menu_button_main', lang_code)
            lang_time1 = time.time() - lang_start
            logger.info(f"🔍 DEBUG: Language get_text('menu_button_main') took {lang_time1:.3f}s, result: '{main_menu_text}'")
            
            lang_start = time.time()
            admin_panel_text = self.language.get_text('menu_button_admin', lang_code)
            lang_time2 = time.time() - lang_start
            logger.info(f"🔍 DEBUG: Language get_text('menu_button_admin') took {lang_time2:.3f}s, result: '{admin_panel_text}'")
            
            if text in [main_menu_text, '📋 Meniu', '📋 Meniu Principal']:
                self.db.clear_user_state(user_id)
                menu_time = time.time() - menu_check_start
                logger.info(f"🔍 DEBUG: Main menu button detected, processing in {menu_time:.3f}s")

                menu_handler_start = time.time()

            # 2. send full inline main menu
                self.menu_handler.send_main_menu_message(message.chat.id, user_id)

                menu_handler_time = time.time() - menu_handler_start
                logger.info(f"🔍 DEBUG: Menu handler execution took {menu_handler_time:.3f}s")
                return
                
            elif text in [admin_panel_text, '⚙️ Panou Admin', '⚙️  Panou Admin']:
                self.db.clear_user_state(user_id)
                menu_time = time.time() - menu_check_start
                logger.info(f"🔍 DEBUG: Admin panel button detected, processing in {menu_time:.3f}s")
                
                admin_handler_start = time.time()
                self.admin_handler.handle_admin_panel_keyboard(message)
                admin_handler_time = time.time() - admin_handler_start
                logger.info(f"🔍 DEBUG: Admin panel handler execution took {admin_handler_time:.3f}s")
                return
            else:
                menu_time = time.time() - menu_check_start
                logger.info(f"🔍 DEBUG: No menu button match, check took {menu_time:.3f}s")
                return
                
            total_time = time.time() - start_time
            logger.info(f"🔍 DEBUG: Total text message processing took {total_time:.3f}s for user {user_id}")
        
        # [F2] Vizualizare produse

        
        # Callback query handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
        def handle_language_selection(call):
            self.start_handler.handle_language_selection(call)
                
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('warn_user_'))
        def handle_warn_user(call):
            self.dispute_handler.handle_warn_user(call)        
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'main_menu')
        def handle_main_menu(call):
            self.menu_handler.handle_main_menu(call)
            
        def handle_admin_panel_from_message(self, message):
            """Open admin panel directly from /amenu command."""
            
            user_id = message.from_user.id

            self.db.clear_user_state(user_id)

            if not self.db.is_admin(
                user_id,
                self.config['admin_ids']
            ):
                self.bot.send_message(
                    message.chat.id,
                    "❌ Access denied! Admin only."
                )
                return

            user = self.db.get_or_create_user(user_id)

            if not user:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Database error. Please try again."
                )
                return

            lang_code = user['language_code']

            welcome_text = self.language.get_text(
                'admin_panel_welcome',
                lang_code
            )

            markup = telebot.types.InlineKeyboardMarkup()

            admin_buttons = self.language.get_admin_buttons(
                lang_code
            )

            for button_row in admin_buttons:

                row_buttons = []

                for btn in button_row:

                    button_text = btn['text']
                    callback_data = btn['callback_data']

                    if callback_data == 'admin_currency_settings':

                        current_currency = self.config.get(
                            'currency',
                            {'symbol': 'RON'}
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

            self.bot.send_message(
                message.chat.id,
                welcome_text,
                parse_mode='HTML',
                reply_markup=markup
            )    
            
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_panel')
        def handle_admin_panel(call):
            self.admin_handler.handle_admin_panel(call)
            
        #Callback-uri seller
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_add_drop_type|'))
        def handle_seller_add_drop_type(call):
            _, product_id, stock_type = call.data.split('|')

            self.db.set_user_state(
                call.from_user.id,
                'seller_adding_drop',
                {
                    'product_id': product_id,
                    'stock_type': stock_type
                }
            )

            label = "Pădure" if stock_type == "padure" else "Oraș"

            self.bot.send_message(
                call.message.chat.id,
                f"📸 Trimite poza pentru stock <b>{label}</b>. Caption-ul pozei va fi folosit ca text.",
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
                
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_drops_type|'))
        def handle_seller_drops_type(call):
            user_id = call.from_user.id
            _, product_id, stock_type = call.data.split('|')

            products_data = self.product_handler.load_products()
            product = None

            for p in products_data.get('products', []):
                if (
                    p.get('id') == product_id and
                    p.get('owner_user_id') == user_id and
                    p.get('is_seller_product') is True
                ):
                    product = p
                    break

            if not product:
                self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost găsit.", show_alert=True)
                return

            label = "🌲 Pădure" if stock_type == "padure" else "🏙️ Oraș"
            text = f"{label} <b>Stock pentru {product['name']}</b>\n\n"

            markup = telebot.types.InlineKeyboardMarkup()

            found = False
            for idx, item in enumerate(product.get('drop_items', [])):
                item_type = item.get('stock_type', 'oras')
                if item_type != stock_type:
                    continue

                found = True
                caption = item.get('caption', '(fără text)')
                short_caption = caption[:25] + "..." if len(caption) > 25 else caption

                markup.row(
                    telebot.types.InlineKeyboardButton(
                        text=f"#{idx + 1} - {short_caption}",
                        callback_data=f"seller_open_drop_{product_id}_{idx}"
                    )
                )

            if not found:
                text += "Nu există stock în categoria asta.\n\n"

            markup.row(
                telebot.types.InlineKeyboardButton(
                    f"➕ Adaugă {label}",
                    callback_data=f"seller_add_drop_type|{product_id}|{stock_type}"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔙 Înapoi",
                    callback_data=f"seller_edit_drops_{product_id}"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
     
         # Accesare meniu seller si cumpararea butonului
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'menu_become_seller')
        def handle_become_seller(call):
            user = self.db.get_or_create_user(call.from_user.id)
            lang_code = user['language_code'] if user else 'ro'

            if self.db.is_seller(call.from_user.id):
                self.bot.answer_callback_query(call.id, self.language.get_text('seller_already_active', lang_code), show_alert=True)
                return

            title = self.language.get_text('seller_role_title', lang_code)
            body = self.language.get_text('seller_role_text', lang_code)
            text = f"{title}\n\n{body}"

            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                text=self.language.get_text('seller_buy_button', lang_code),
                callback_data='seller_buy_confirm'
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text=self.language.get_text('back_to_menu', lang_code),
                callback_data='main_menu'
            ))

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        
        # Confirmarea cumpararii rolului de vanzator
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_buy_confirm')
        def handle_seller_buy_confirm(call):
            user_id = call.from_user.id
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'ro'

            if self.db.is_seller(user_id):
                self.bot.answer_callback_query(call.id, self.language.get_text('seller_already_active', lang_code), show_alert=True)
                return

            balance = self.db.get_user_balance(user_id)
            seller_price = 1500

            if balance < seller_price:
                self.bot.answer_callback_query(
                    call.id,
                    self.language.get_text('seller_not_enough_balance', lang_code),
                    show_alert=True
                )
                return

            categories = self.category_handler.get_all_city_categories()
            if not categories:
                self.bot.answer_callback_query(
                    call.id,
                    self.language.get_text('seller_no_cities_available', lang_code),
                    show_alert=True
                )
                return

            text = self.language.get_text('seller_choose_city', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()

            for city in categories:
                markup.add(telebot.types.InlineKeyboardButton(
                    text=city['name'],
                    callback_data=f"seller_choose_city_{city['id']}"
                ))

            markup.add(telebot.types.InlineKeyboardButton(
                text=self.language.get_text('back_to_menu', lang_code),
                callback_data='main_menu'
            ))

            # Debitul nu se face încă aici, ci după alegerea orașului
            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        
        # Alegerea orasului si activarea rolului de vanzator
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_choose_city_'))
        def handle_seller_choose_city(call):
            user_id = call.from_user.id
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'ro'

            if self.db.is_seller(user_id):
                self.bot.answer_callback_query(call.id, self.language.get_text('seller_already_active', lang_code), show_alert=True)
                return

            seller_price = 1500
            balance = self.db.get_user_balance(user_id)

            if balance < seller_price:
                self.bot.answer_callback_query(
                    call.id,
                    self.language.get_text('seller_not_enough_balance', lang_code),
                    show_alert=True
                )
                return

            city_id = call.data.replace('seller_choose_city_', '')
            shop_name = self.language.get_text('seller_shop_name_default', lang_code).format(user_id=user_id)

            subcategory_id = self.category_handler.create_seller_shop_subcategory(city_id, user_id, shop_name)
            if not subcategory_id:
                self.bot.answer_callback_query(call.id, "❌ Nu s-a putut crea magazinul.", show_alert=True)
                return

            # Scade banii
            if not self.db.add_to_balance(user_id, -seller_price):
                self.bot.answer_callback_query(call.id, "❌ Nu s-a putut debita balanța.", show_alert=True)
                return

            # Activează sellerul
            if not self.db.activate_seller_role(user_id, city_id, subcategory_id, shop_name):
                self.bot.answer_callback_query(call.id, "❌ Nu s-a putut activa rolul seller.", show_alert=True)
                return

            success_text = (
                f"{self.language.get_text('seller_role_activated', lang_code)}\n\n"
                f"{self.language.get_text('seller_shop_created', lang_code)}"
            )

            self.bot.send_message(
                call.message.chat.id,
                success_text,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass     

        # [F2] Callback pentru editarea descrierii magazinului
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_edit_shop_description')
        def handle_seller_edit_shop_description(call):
            self.db.set_user_state(
                call.from_user.id,
                'seller_editing_shop_description',
                {}
            )

            self.bot.send_message(
                call.message.chat.id,
                "📝 Trimite noua descriere a magazinului:"
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        # [F2] Callback pentru editarea pozei magazinului
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_edit_shop_image')
        def handle_seller_edit_shop_image(call):
            self.db.set_user_state(
                call.from_user.id,
                'seller_uploading_shop_image',
                {}
            )

            self.bot.send_message(
                call.message.chat.id,
                "🖼️ Trimite poza nouă pentru magazin."
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        
        # Editarea magazinului (F2)
        @self.bot.callback_query_handler(func=lambda call: call.data == 'menu_edit_seller_shop')
        def handle_edit_seller_shop(call):
            user_id = call.from_user.id
            user = self.db.get_or_create_user(user_id)
            lang_code = user['language_code'] if user else 'ro'

            seller_info = self.db.get_seller_info(user_id)
            if not seller_info or not seller_info.get('is_seller'):
                self.bot.answer_callback_query(call.id, "❌ Nu ai rol de seller.", show_alert=True)
                return

            products = self.product_handler.get_seller_shop_products(
                user_id,
                seller_info['seller_subcategory_id']
            )

            text = (
                f"🏪 <b>Magazinul tău</b>\n\n"
                f"📝 <b>Nume:</b> {seller_info.get('seller_shop_name')}\n"
                f"📍 <b>Oraș ID:</b> <code>{seller_info.get('seller_city_id')}</code>\n"
                f"📦 <b>Produse:</b> {len(products)}\n\n"
                f"Alege o opțiune:"
            )

            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "📦 Produse",
                    callback_data="seller_products"
                ),
                telebot.types.InlineKeyboardButton(
                    "📈 Statistici",
                    callback_data="seller_statistics"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    "💸 Retragere",
                    callback_data="seller_cashout"
                )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "✏️ Redenumește magazin",
                    callback_data="seller_rename_shop"
                )
            )
            
            markup.row(
                telebot.types.InlineKeyboardButton(
                "🖼 Poza",
                callback_data="seller_edit_shop_image"
                ),
                telebot.types.InlineKeyboardButton(
                "✏ Descriere️",
                callback_data="seller_edit_shop_description"
                )
            )
            
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔙 Înapoi",
                    callback_data="main_menu"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass


        @self.bot.callback_query_handler(func=lambda call: call.data == "seller_cashout_confirm")
        def handle_seller_cashout_confirm(call):
            self.seller_handler.confirm_cashout(call)
            
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('menu_'))
        def handle_menu_buttons(call):
            if call.data == 'menu_become_seller':
                handle_become_seller(call)
                return
            elif call.data == 'menu_edit_seller_shop':
                handle_edit_seller_shop(call)
                return
            elif call.data == "seller_statistics":

                self.bot.answer_callback_query(call.id)

                self.bot.send_message(
                    call.message.chat.id,
                    "📈 Statistici în curând."
                )

            elif call.data == "seller_cashout":

                balance = self.db.get_user_balance(
                    call.from_user.id
                )

                minimum = self.config["fees"]["cashout_minimum"]

                if balance < minimum:

                    self.bot.answer_callback_query(
                        call.id,
                        f"Minimum {minimum} RON",
                        show_alert=True
                    )

                    return

                markup = telebot.types.InlineKeyboardMarkup()

                markup.row(
                    telebot.types.InlineKeyboardButton(
                        "Ł LTC",
                        callback_data="seller_cashout_crypto"
                    ),
                    telebot.types.InlineKeyboardButton(
                        "₮ USDT",
                        callback_data="seller_cashout_crypto"
                    )
                )

                markup.row(
                    telebot.types.InlineKeyboardButton(
                        "🔙 Înapoi",
                        callback_data="menu_edit_seller_shop"
                    )
                )

                self.bot.send_message(
                    call.message.chat.id,
                    f"💸 <b>Retragere</b>\n\n"
                    f"💰 Sold disponibil: {balance:.2f} RON\n\n"
                    f"Alege moneda:",
                    parse_mode="HTML",
                    reply_markup=markup
                )

                self.bot.answer_callback_query(call.id)

            # Try menu handler first
            handled = self.menu_handler.handle_menu_buttons(call)
            if not handled:
                if call.data == 'menu_products':
                    self.shopping_handler.handle_products_menu(call)
                elif call.data == 'menu_cart':
                    self.cart_handler.handle_cart_view(call)
                elif call.data == 'menu_history':
                    self.history_handler.handle_history_menu(call)
                elif call.data == 'menu_topup':
                    self.topup_handler.handle_topup_menu(call)
                elif call.data == 'menu_profile':
                    self.profile_handler.show_profile(call)
                elif call.data == 'menu_disputes':
                    self.dispute_handler.handle_disputes_menu(call)
            
        #[F2] Categorii seller
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_categories')
        def handle_seller_categories(call):
            user_id = call.from_user.id

            seller_info = self.db.get_seller_info(user_id)
            if not seller_info:
                return

            text = (
                "📂 <b>Subcategoriile magazinului</b>\n\n"
                "Aici vei putea crea categorii pentru produsele tale."
            )

            markup = telebot.types.InlineKeyboardMarkup()

            markup.row(
                telebot.types.InlineKeyboardButton(
                    "➕ Adaugă subcategorie",
                    callback_data="seller_add_category"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔙 Înapoi",
                    callback_data="menu_edit_seller_shop"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        
        #[F2] Creare categorii pentru seller
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_add_category')
        def handle_seller_add_category(call):
            self.db.set_user_state(
                call.from_user.id,
                "seller_creating_category",
                {}
            )

            self.bot.send_message(
                call.message.chat.id,
                "✏️ Trimite numele noii subcategorii:"
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        #[F2] Handler pentru produse subcategorii
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_open_subcat_'))
        def handle_seller_open_subcat(call):
            user_id = call.from_user.id
            seller_subcat_id = call.data.replace('seller_open_subcat_', '')

            seller_subcat = self.category_handler.get_seller_subcategory_by_id(
                seller_subcat_id,
                user_id
            )

            if not seller_subcat:
                self.bot.answer_callback_query(call.id, "❌ Subcategoria nu a fost găsită.", show_alert=True)
                return

            products = self.product_handler.get_seller_products(user_id, seller_subcat_id)

            text = f" <b>{seller_subcat['name']}</b>\n\n"

            markup = telebot.types.InlineKeyboardMarkup()

            if products:
                for product in products:
                    markup.row(
                        telebot.types.InlineKeyboardButton(
                            text=f" {product['name']}",
                            callback_data=f"seller_view_product_{product['id']}"
                        )
                    )
            else:
                text += "Nu ai produse în această subcategorie.\n\n"

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="➕ Adaugă produs",
                    callback_data=f"seller_add_product_{seller_subcat_id}"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="🔙 Înapoi",
                    callback_data="seller_categories"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
      
        #[F2] Handler pt produse
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_add_product')
        def handle_seller_add_product(call):
            self.db.set_user_state(
                call.from_user.id,
                'seller_creating_product',
                {}
            )

            self.bot.send_message(
                call.message.chat.id,
                "✏️ Trimite numele produsului:"
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        
        # Adaugare handler pentru vizionare produselor [F2]
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_view_product_'))
        def handle_seller_view_product(call):
            user_id = call.from_user.id
            product_id = call.data.replace('seller_view_product_', '')

            products_data = self.product_handler.load_products()
            product = None

            for p in products_data.get('products', []):
                if (
                    p.get('id') == product_id and
                    p.get('owner_user_id') == user_id and
                    p.get('is_seller_product') is True
                ):
                    product = p
                    break

            if not product:
                self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost găsit.", show_alert=True)
                return

            text = (
                f"📦 <b>{product['name']}</b>\n\n"
                f"📝 <b>Descriere:</b> {product.get('description', '-') or '-'}\n"
                f"💰 <b>Preț:</b> {product.get('price', 0)} RON\n"
                f"📊 <b>Stock:</b> {len(product.get('drop_items', []))}\n"
                f"📋 <b>Tip:</b> drop\n"
            )

            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "✏️ Editează nume",
                    callback_data=f"seller_edit_name_{product_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    "📝 Editează descriere",
                    callback_data=f"seller_edit_desc_{product_id}"
                ),
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "💰 Editează preț",
                    callback_data=f"seller_edit_price_{product_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    "🖼 Editează poza",
                    callback_data=f"seller_edit_product_image_{product_id}"
                    )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🖼️ Editează Drop-uri",
                    callback_data=f"seller_edit_drops_{product_id}"
                ),
                telebot.types.InlineKeyboardButton(
                    "🗑️ Șterge produs",
                    callback_data=f"seller_delete_product_{product_id}"
                )
            )
            
     
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔙 Înapoi",
                    callback_data="seller_products"
                )
            )

            product_images = product.get('images', [])

            if product_images:
                first_image = product_images[0]

                if isinstance(first_image, dict):
                    photo_file_id = first_image.get('file_id')
                else:
                    photo_file_id = first_image

                if photo_file_id:
                    self.bot.send_photo(
                        call.message.chat.id,
                        photo_file_id,
                        caption=text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                else:
                    self.bot.send_message(
                        call.message.chat.id,
                        text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
            else:
                self.bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass        
        # Produse seller [F2] hAnDlEr
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_products')
        def handle_seller_products(call):
            user_id = call.from_user.id

            seller_info = self.db.get_seller_info(user_id)
            if not seller_info:
                self.bot.answer_callback_query(call.id, "❌ Seller info not found.", show_alert=True)
                return

            products = self.product_handler.get_seller_shop_products(
                user_id,
                seller_info['seller_subcategory_id']
            )

            text = "📦 <b>Produsele magazinului</b>\n\n"

            markup = telebot.types.InlineKeyboardMarkup()

            if products:
                for product in products:
                    markup.row(
                        telebot.types.InlineKeyboardButton(
                            text=f"📦 {product['name']}",
                            callback_data=f"seller_view_product_{product['id']}"
                        )
                    )
            else:
                text += "Nu ai produse încă.\n\n"

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="➕ Adaugă produs",
                    callback_data="seller_add_product"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="🔙 Înapoi",
                    callback_data="menu_edit_seller_shop"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        # [F2] Renumeste magazinul seller-ului
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_rename_shop')
        def handle_seller_rename_shop(call):
            self.db.set_user_state(
                call.from_user.id,
                'seller_renaming_shop',
                {}
            )

            self.bot.send_message(
                call.message.chat.id,
                "✏️ Trimite noul nume al magazinului:"
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        
        # [F2] Modificare poza produs
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_edit_product_image_'))
        def handle_seller_edit_product_image(call):
            product_id = call.data.replace('seller_edit_product_image_', '')

            self.db.set_user_state(
                call.from_user.id,
                'seller_uploading_product_image',
                {'product_id': product_id}
            )

            self.bot.send_message(
                call.message.chat.id,
                "🖼️ Trimite poza produsului."
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass        
        
        # [F2] Modificare nume produse
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_edit_name_'))
        def handle_seller_edit_name(call):
            product_id = call.data.replace('seller_edit_name_', '')
            self.db.set_user_state(
                call.from_user.id,
                'seller_editing_product_name',
                {'product_id': product_id}
            )
            self.bot.send_message(call.message.chat.id, "✏️ Trimite noul nume al produsului:")
            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass


        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_edit_desc_'))
        def handle_seller_edit_desc(call):
            product_id = call.data.replace('seller_edit_desc_', '')
            self.db.set_user_state(
                call.from_user.id,
                'seller_editing_product_desc',
                {'product_id': product_id}
            )
            self.bot.send_message(call.message.chat.id, "📝 Trimite noua descriere:")
            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass


        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_edit_price_'))
        def handle_seller_edit_price(call):
            product_id = call.data.replace('seller_edit_price_', '')
            self.db.set_user_state(
                call.from_user.id,
                'seller_editing_product_price',
                {'product_id': product_id}
            )
            self.bot.send_message(call.message.chat.id, "💰 Trimite noul preț în RON:")
            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass        
        
        #[F2] Handler pentru editarea drop-urilor selleriilor
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_edit_drops_'))
        def handle_seller_edit_drops(call):
            user_id = call.from_user.id
            product_id = call.data.replace('seller_edit_drops_', '')

            products_data = self.product_handler.load_products()
            product = None

            for p in products_data.get('products', []):
                if (
                    p.get('id') == product_id and
                    p.get('owner_user_id') == user_id and
                    p.get('is_seller_product') is True
                ):
                    product = p
                    break

            if not product:
                self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost găsit.", show_alert=True)
                return

            drop_items = product.get('drop_items', [])

            padure_count = len([d for d in drop_items if d.get('stock_type', 'oras') == 'padure'])
            oras_count = len([d for d in drop_items if d.get('stock_type', 'oras') == 'oras'])

            text = (
                f"🖼️ <b>Drop-uri pentru {product['name']}</b>\n\n"
                f"🌲 <b>Pădure:</b> {padure_count}\n"
                f"🏙️ <b>Oraș:</b> {oras_count}\n\n"
                f"Alege categoria de stock:"
            )

            markup = telebot.types.InlineKeyboardMarkup()

            markup.row(
                telebot.types.InlineKeyboardButton(
                    f"🌲 Pădure ({padure_count})",
                    callback_data=f"seller_drops_type|{product_id}|padure"
                ),
                telebot.types.InlineKeyboardButton(
                    f"🏙️ Oraș ({oras_count})",
                    callback_data=f"seller_drops_type|{product_id}|oras"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    "➕ Adaugă Pădure",
                    callback_data=f"seller_add_drop_type|{product_id}|padure"
                ),
                telebot.types.InlineKeyboardButton(
                    "➕ Adaugă Oraș",
                    callback_data=f"seller_add_drop_type|{product_id}|oras"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔙 Înapoi",
                    callback_data=f"seller_view_product_{product_id}"
                )
            )

            self.bot.send_message(
                call.message.chat.id,
                text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass        
        # [F2] Handler pentru deschiderea drop-ului
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_open_drop_'))
        def handle_seller_open_drop(call):
            user_id = call.from_user.id
            data = call.data.replace('seller_open_drop_', '')
            product_id, index_str = data.rsplit('_', 1)
            index = int(index_str)

            products_data = self.product_handler.load_products()
            product = None

            for p in products_data.get('products', []):
                if (
                    p.get('id') == product_id and
                    p.get('owner_user_id') == user_id and
                    p.get('is_seller_product') is True
                ):
                    product = p
                    break

            if not product:
                self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost găsit.", show_alert=True)
                return

            drop_items = product.get('drop_items', [])
            if index < 0 or index >= len(drop_items):
                self.bot.answer_callback_query(call.id, "❌ Drop invalid.", show_alert=True)
                return

            item = drop_items[index]
            caption = item.get('caption', '-')

            text = (
                f"🛠️ <b>Drop #{index+1}</b>\n\n"
                f"📍 <b>Coordonate:</b>\n{caption}"
            )

            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "✏️ Editează coordonate",
                    callback_data=f"seller_edit_drop_caption_{product_id}_{index}"
                )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🖼️ Înlocuiește poza",
                    callback_data=f"seller_replace_drop_image_{product_id}_{index}"
                )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🗑️ Șterge drop",
                    callback_data=f"seller_delete_drop_{product_id}_{index}"
                )
            )
            markup.row(
                telebot.types.InlineKeyboardButton(
                    "🔙 Înapoi",
                    callback_data=f"seller_edit_drops_{product_id}"
                )
            )

            file_id = item.get('file_id')

            try:
                if file_id:
                    self.bot.send_photo(
                        call.message.chat.id,
                        photo=file_id,
                        caption=text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
                else:
                    self.bot.send_message(
                        call.message.chat.id,
                        text,
                        reply_markup=markup,
                        parse_mode='HTML'
                    )
            except Exception as e:
                logger.error(f"Error showing seller drop preview: {e}")
                self.bot.send_message(
                    call.message.chat.id,
                    text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass
        #[F2] Adaugarea drop-ului [poza si caption]
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_add_drop_'))
        def handle_seller_add_drop(call):
            product_id = call.data.replace('seller_add_drop_', '')

            self.db.set_user_state(
                call.from_user.id,
                'seller_adding_drop',
                {'product_id': product_id}
            )

            self.bot.send_message(
                call.message.chat.id,
                "📸 Trimite poza pentru drop. Caption-ul pozei va fi folosit drept coordonate."
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        #[F2] Handler pentru editare
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_edit_drop_caption_'))
        def handle_seller_edit_drop_caption(call):
            data = call.data.replace('seller_edit_drop_caption_', '')
            product_id, index_str = data.rsplit('_', 1)

            self.db.set_user_state(
                call.from_user.id,
                'seller_editing_drop_caption',
                {'product_id': product_id, 'index': int(index_str)}
            )

            self.bot.send_message(
                call.message.chat.id,
                "✏️ Trimite noile coordonate:"
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_replace_drop_image_'))
        def handle_seller_replace_drop_image(call):
            data = call.data.replace('seller_replace_drop_image_', '')
            product_id, index_str = data.rsplit('_', 1)

            self.db.set_user_state(
                call.from_user.id,
                'seller_replacing_drop_image',
                {'product_id': product_id, 'index': int(index_str)}
            )

            self.bot.send_message(
                call.message.chat.id,
                "🖼️ Trimite poza nouă pentru acest drop."
            )

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        #[F2] Handler pentru stergerea produsului
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_delete_product_'))
        def handle_seller_delete_product(call):
            user_id = call.from_user.id
            product_id = call.data.replace('seller_delete_product_', '')

            ok = self.product_handler.delete_seller_product(user_id, product_id)

            if ok:
                self.bot.send_message(call.message.chat.id, "✅ Produs șters.")
            else:
                self.bot.send_message(call.message.chat.id, "❌ Nu s-a putut șterge produsul.")

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('seller_delete_drop_'))
        def handle_seller_delete_drop(call):
            user_id = call.from_user.id
            data = call.data.replace('seller_delete_drop_', '')
            product_id, index_str = data.rsplit('_', 1)
            index = int(index_str)

            ok = self.product_handler.delete_seller_drop(user_id, product_id, index)

            if ok:
                self.bot.send_message(call.message.chat.id, "✅ Drop șters.")
            else:
                self.bot.send_message(call.message.chat.id, "❌ Nu s-a putut șterge drop-ul.")

            try:
                self.bot.answer_callback_query(call.id)
            except:
                pass

        # Specific admin handlers MUST come before general admin_ handler
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_chat_setup_back')
        def handle_admin_chat_setup_back(call):
            self.admin_handler.handle_admin_setup_back(call)
            
        @self.bot.callback_query_handler(func=lambda call: call.data == 'payment_setup_back')
        def handle_payment_setup_back(call):
            self.admin_handler.handle_payment_setup_back(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'store_back_to_settings')
        def handle_back_to_store_settings(call):
            self.admin_handler.handle_back_to_settings(call)
        
        # Fix pentru pagina de tichete
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_dispute_view')
        def handle_admin_dispute_view_menu(call):
            self.dispute_handler.show_admin_disputes(call)        
            
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_disputes')
        def handle_admin_disputes(call):
            self.dispute_handler.show_admin_disputes(call)
                    
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('refund_'))
        def handle_refund_callbacks(call):
            self.dispute_handler.handle_refund_callback(call)
            
                
        # General admin handler - MUST be after specific handlers
        @self.bot.callback_query_handler(
            func=lambda call: call.data.startswith('admin_')
            and call.data != 'admin_disputes'
            and call.data != 'admin_dispute_view'
            and not call.data.startswith('admin_dispute_view_')
            and not call.data.startswith('admin_dispute_resolve_')
        )
        def handle_admin_buttons(call):
            self.admin_handler.handle_admin_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('store_edit_'))
        def handle_store_edit_buttons(call):
            self.admin_handler.handle_store_edit_buttons(call)
            
            
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'store_tab_images')
        def handle_store_tab_images(call):
            user = self.db.get_or_create_user(call.from_user.id)
            lang_code = user['language_code'] if user else 'ro'
            self.admin_handler.show_tab_images_menu(call, lang_code)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('tabimg_'))
        def handle_tab_image_select(call):
            mapping = {
                'tabimg_main_menu': ('main_menu', 'Meniu Principal'),
                'tabimg_admin_panel': ('admin_panel', 'Panou Admin'),
                'tabimg_products_menu': ('products_menu', 'Instant Drop'),
                'tabimg_cart_menu': ('cart_menu', 'Coș'),
                'tabimg_topup_menu': ('topup_menu', 'Depozit'),
                'tabimg_reviews_menu': ('reviews_menu', 'Recenzii'),
                'tabimg_disputes_menu': ('disputes_menu', 'Probleme'),
                'tabimg_history_menu': ('history_menu', 'Comenzi Precedente'),
            }

            if call.data in mapping:
                page_key, page_name = mapping[call.data]
                self.admin_handler.prompt_tab_image_upload(call, page_key, page_name)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'coming_soon_feature')
        def handle_coming_soon_feature(call):
            # Just answer the callback query to dismiss the loading state
            self.bot.answer_callback_query(call.id)
        
        # Category management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_categories')
        def handle_categories_management(call):
            self.category_handler.handle_categories_management(call)
                
        @self.bot.callback_query_handler(
            func=lambda call:
            call.data.startswith('back:')
        )
        def handle_global_back(call):

            try:

                self.bot.delete_message(
                    call.message.chat.id,
                    call.message.message_id
                )

            except:
                pass

            target = call.data.split(
                ':',
                1
            )[1]

            # fake callback redirect
            call.data = target

            # MAIN MENU
            if target == 'main_menu':

                self.menu_handler.handle_main_menu_keyboard(
                    call.message
                )

            # MENU CALLBACKS
            elif target.startswith('menu_'):

                handle_menu_buttons(call)

            # DISPUTES
            elif target.startswith('dispute_'):

                self.dispute_handler.handle_disputes_callbacks(
                    call
                )

            # ADMIN
            elif target.startswith('admin_'):

                self.admin_handler.handle_admin_panel(
                    call
                )        

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_view_'))
        def handle_category_view(call):
            self.category_handler.handle_category_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'cat_add_new')
        def handle_add_new_category(call):
            self.category_handler.handle_add_new_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_add_'))
        def handle_add_new_subcategory(call):
            self.category_handler.handle_add_new_subcategory(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_edit_'))
        def handle_edit_category(call):
            self.category_handler.handle_edit_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_delete_'))
        def handle_delete_category(call):
            self.category_handler.handle_delete_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_confirm_delete_'))
        def handle_confirm_delete_category(call):
            self.category_handler.handle_confirm_delete_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cat_back_'))
        def handle_category_back_buttons(call):
            self.category_handler.handle_back_buttons(call)
        
        # Subcategory management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_edit_'))
        def handle_edit_subcategory(call):
            self.category_handler.handle_edit_subcategory(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_delete_'))
        def handle_delete_subcategory(call):
            self.category_handler.handle_delete_subcategory(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('subcat_confirm_delete_'))
        def handle_confirm_delete_subcategory(call):
            self.category_handler.handle_confirm_delete_subcategory(call)
        
        # Product management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_products')
        def handle_products_management(call):
            self.product_handler.handle_products_management(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_cat_'))
        def handle_product_category_view(call):
            self.product_handler.handle_product_category_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_subcat_'))
        def handle_product_subcategory_view(call):
            self.product_handler.handle_product_subcategory_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_view_'))
        def handle_product_view(call):
            self.product_handler.handle_product_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_add_'))
        def handle_add_new_product(call):
            self.product_handler.handle_add_new_product(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_premium_alert')
        def handle_premium_alert(call):
            self.product_handler.handle_premium_alert(call)
        
        # Product creation flow handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_proceed_step_6')
        def handle_proceed_step_6(call):
            self.product_handler.creation_handler.proceed_to_step_6(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_type_'))
        def handle_product_type_selection(call):
            self.product_handler.creation_handler.handle_product_type_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_files_complete')
        def handle_files_complete(call):
            try:
                # Answer callback query first to remove loading state
                self.bot.answer_callback_query(call.id)
                
                # Proceed to review settings for downloadable products
                user_state = self.db.get_user_state(call.from_user.id)
                if not user_state:
                    logger.error(f"No user state found for upload complete - user {call.from_user.id}")
                    self.bot.send_message(call.message.chat.id, "❌ Session expired. Please start over.")
                    return
                
                import json
                try:
                    # Handle both dict and string data formats
                    if isinstance(user_state['data'], dict):
                        state_data = user_state['data']
                    else:
                        state_data = json.loads(user_state['data'])
                    
                    lang_code = state_data['lang_code']
                    product_data = state_data['product_data']
                    
                    # Validate we have files uploaded
                    if 'files' not in product_data or len(product_data['files']) == 0:
                        logger.warning(f"Upload complete clicked but no files found - user {call.from_user.id}")
                        self.bot.send_message(call.message.chat.id, "❌ No files uploaded. Please upload files first.")
                        return
                    
                    logger.info(f"Processing upload complete for user {call.from_user.id} - {len(product_data['files'])} files")
                    self.product_handler.creation_handler.proceed_to_review_settings(call.message, call.from_user.id, lang_code, product_data)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in upload complete: {e}")
                    self.bot.send_message(call.message.chat.id, "❌ Session data corrupted. Please start over.")
                except Exception as e:
                    logger.error(f"Error in upload complete handler: {e}")
                    self.bot.send_message(call.message.chat.id, "❌ Error processing upload. Please try again.")
                    
            except Exception as e:
                logger.error(f"Critical error in handle_files_complete: {e}")
                try:
                    self.bot.answer_callback_query(call.id, "❌ Error occurred")
                except:
                    pass
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_save_final')
        def handle_save_final_product(call):
            self.product_handler.creation_handler.save_final_product(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith("cashout_"))
        def handle_cashout_callbacks(call):
            self.admin_handler.handle_cashout_callbacks(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_cancel_upload')
        def handle_cancel_product_upload(call):
            self.product_handler.creation_handler.cancel_product_creation(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_drop_complete')
        def handle_prod_drop_complete(call):
            user_id = call.from_user.id
            user_state = self.db.get_user_state(user_id)

            if not user_state:
                self.bot.answer_callback_query(call.id, "❌ Session expired.", show_alert=True)
                return

            try:
                state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                lang_code = state_data['lang_code']
                product_data = state_data['product_data']
            except Exception:
                self.bot.answer_callback_query(call.id, "❌ Invalid session data.", show_alert=True)
                return

            if product_data.get('type') != 'drop':
                self.bot.answer_callback_query(call.id, "❌ Invalid product type.", show_alert=True)
                return

            drop_items = product_data.get('drop_items', [])

            if not drop_items:
                self.bot.answer_callback_query(call.id, "❌ Upload at least one photo first.", show_alert=True)
                return

            all_have_captions = all((item.get('caption') or '').strip() for item in drop_items)

            if not all_have_captions:
                self.bot.answer_callback_query(call.id, "❌ Each photo must have its own caption.", show_alert=True)
                return

            product_data['stock'] = len(drop_items)

            self.product_handler.creation_handler.proceed_to_review_settings(
                call.message,
                user_id,
                lang_code,
                product_data
            )

            self.bot.answer_callback_query(call.id)
    
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_edit_drops_'))
        def handle_edit_drops(call):
            self.product_handler.handle_edit_drops(call)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_edit_drop_item_'))
        def handle_edit_drop_item(call):
            self.product_handler.handle_edit_drop_item(call)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_edit_drop_caption_'))
        def handle_edit_drop_caption(call):
            self.product_handler.handle_edit_drop_caption(call)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_replace_drop_'))
        def handle_replace_drop(call):
            self.product_handler.handle_replace_drop(call)

        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_delete_drop_'))
        def handle_delete_drop(call):
            self.product_handler.handle_delete_drop(call)

        # Product editing handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_edit_'))
        def handle_product_edit_buttons(call):
            self.product_handler.handle_product_edit_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_toggle_visibility_'))
        def handle_product_visibility_toggle(call):
            self.product_handler.handle_product_visibility_toggle(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_delete_'))
        def handle_product_delete(call):
            self.product_handler.handle_product_delete(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_confirm_delete_'))
        def handle_product_confirm_delete(call):
            self.product_handler.handle_product_confirm_delete(call)
        
        # Review settings handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_reviews_enable')
        def handle_reviews_enable(call):
            self.product_handler.creation_handler.handle_reviews_setting(call, True)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'prod_reviews_disable')
        def handle_reviews_disable(call):
            self.product_handler.creation_handler.handle_reviews_setting(call, False)
         
        # Review edit handlers for existing products
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_set_reviews_'))
        def handle_set_reviews(call):
            self.product_handler.handle_set_reviews(call)
        
        # Upload more handler for downloadable/line products
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('prod_upload_more_'))
        def handle_upload_more(call):
            self.product_handler.handle_upload_more(call)
        
        # Currency management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_currency_settings')
        def handle_currency_settings(call):
            self.currency_handler.handle_currency_settings(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'currency_popular')
        def handle_popular_currencies(call):
            self.currency_handler.handle_popular_currencies(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'currency_all')
        def handle_all_currencies(call):
            self.currency_handler.handle_all_currencies(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('currency_page_'))
        def handle_currency_page(call):
            self.currency_handler.handle_currency_page(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('currency_select_'))
        def handle_currency_selection(call):
            self.currency_handler.handle_currency_selection(call)
        
        # Shopping handlers (keep the specific shopping actions)
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_cat_'))
        def handle_shop_category_view(call):
            self.shopping_handler.handle_category_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_subcat'))
        def handle_shop_subcategory_view(call):
            self.shopping_handler.handle_subcategory_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_product'))
        def handle_shop_product_view(call):
            self.shopping_handler.handle_product_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_add') or call.data.startswith('shop_sub'))
        def handle_add_to_cart(call):
            self.shopping_handler.handle_add_to_cart(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('shop_custom'))
        def handle_custom_amount(call):
            self.shopping_handler.handle_custom_amount(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'shopping_back_clear_state')
        def handle_shopping_back_clear_state(call):
            self.shopping_handler.handle_back_clear_state(call)
        
        # Cart handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_address_'))
        def handle_cart_address(call):
            self.cart_handler.handle_delivery_address_input(call)
        
        # Empty cart handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_empty_confirm_'))
        def handle_empty_cart_execute(call):
            self.cart_handler.handle_empty_cart_execute(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_view_'))
        def handle_cart_view_return(call):
            self.cart_handler.handle_cart_view(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_empty_'))
        def handle_empty_cart_confirmation(call):
            self.cart_handler.handle_empty_cart_confirmation(call)
        
        # DELIVERABLE PRODUCTS - SEPARATE HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_deliverable_pay_'))
        def handle_deliverable_pay(call):
            self.payment_handler.handle_deliverable_pay_now(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_deliverable_place_'))
        def handle_deliverable_place(call):
            self.payment_handler.handle_deliverable_place_order(call)
        
        # DIGITAL PRODUCTS - SEPARATE HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_digital_pay_'))
        def handle_digital_pay(call):
            self.payment_handler.handle_digital_pay_now(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('cart_digital_check_'))
        def handle_digital_check(call):
            self.payment_handler.handle_digital_check_payment(call)
        
        # PAYMENT COIN SELECTION HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('payment_balance_'))
        def handle_payment_balance(call):
            self.payment_handler.handle_balance_payment(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('payment_coin_'))
        def handle_payment_coin_selection(call):
            self.payment_handler.handle_coin_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('copy_address_'))
        def handle_copy_address(call):
            self.payment_handler.handle_copy_address(call)
        
        # TOPUP HANDLERS
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_amount_'))
        def handle_topup_amount(call):
            self.topup_handler.handle_amount_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'topup_custom')
        def handle_topup_custom(call):
            self.topup_handler.handle_custom_amount(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_coin_'))
        def handle_topup_coin(call):
            self.topup_handler.handle_coin_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_copy_'))
        def handle_topup_copy(call):
            self.topup_handler.handle_copy_address(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('topup_cancel_'))
        def handle_topup_cancel(call):
            self.topup_handler.handle_cancel_invoice(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'cart_back_clear_state')
        def handle_cart_back_clear_state(call):
            self.cart_handler.handle_back_clear_state(call)
        
        # Review handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('review_order_'))
        def handle_review_order(call):
            self.review_handler.handle_review_order(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('review_rating:'))
        def handle_review_rating(call):
            self.review_handler.handle_rating_selection(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'review_back_clear_state')
        def handle_review_back_clear_state(call):
            self.review_handler.handle_back_clear_state(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('product_reviews'))
        def handle_product_reviews(call):
            self.review_handler.handle_product_reviews(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('back_to_product_'))
        def handle_back_to_product(call):
            self.review_handler.handle_back_to_product(call)
        
        # History handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('history_completed_'))
        def handle_history_completed(call):
            self.history_handler.handle_completed_orders(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('history_queue_'))
        def handle_history_queue(call):
            self.history_handler.handle_queue_orders(call)
        
        # Order management handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('order_download_'))
        def handle_order_download(call):
            self.order_management_handler.handle_order_download(call)
        
        # Reviews handlers (public reviews page)
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('reviews_'))
        def handle_reviews_callbacks(call):
            self.reviews_handler.handle_reviews_callbacks(call)
            
        # CASHOUT Handlers
                
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_statistics')
        def handle_seller_statistics(call):
            self.seller_handler.show_statistics(call)


        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_cashout')
        def handle_seller_cashout(call):
            self.seller_handler.show_cashout(call)
            
        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_cashout_crypto')
        def handle_seller_cashout_crypto(call):
            self.seller_handler.start_crypto_cashout(call)


        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_cashout_cash')
        def handle_seller_cashout_cash(call):
            self.seller_handler.start_cash_cashout(call)


        @self.bot.callback_query_handler(func=lambda call: call.data == 'seller_cashout_crypto_confirm')
        def handle_seller_cashout_crypto_confirm(call):
            self.seller_handler.confirm_crypto_cashout(call)

        # Dispute handlers
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('dispute_'))
        def handle_dispute_callbacks(call):
            self.dispute_handler.handle_disputes_callbacks(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('admin_dispute_'))
        def handle_admin_dispute_actions(call):
            self.dispute_handler.handle_disputes_callbacks(call)
                            
        @self.bot.callback_query_handler(func=lambda call: call.data == 'menu_profile')
        def handle_profile_menu(call):
            self.profile_handler.show_profile(call)
                    
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('refund_'))
        def handle_refund_callback(call):
            self.dispute_handler.handle_refund_callback(call)
        
        # Button editor handlers
        @self.bot.callback_query_handler(func=lambda call: call.data == 'admin_edit_buttons')
        def handle_export_buttons(call):
            self.button_editor_handler.handle_export_buttons(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data.startswith('button_edit_'))
        def handle_button_category(call):
            self.button_editor_handler.handle_button_category(call)
        
        @self.bot.callback_query_handler(func=lambda call: call.data == 'button_edit_cancel')
        def handle_cancel_button_edit(call):
            self.button_editor_handler.handle_cancel_edit(call)
        
        # Fallback handler for unhandled callback queries (prevents hanging buttons)
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_unhandled_callbacks(call):
            logger.warning(f"⚠️ Unhandled callback query: {call.data} from user {call.from_user.id}")
            self.safe_answer_callback_query(call, "⚠️ Action not recognized. Please try again.", show_alert=True)
    
    def safe_answer_callback_query(self, call, text=None, show_alert=False):
        """Safely answer callback query with fallback to regular message for important alerts"""
        if not hasattr(call, 'id') or call.id is None:
            logger.debug("🚫 Invalid callback query - missing ID")
            return False
        
        # Try to answer the callback query
        success = self.bot.answer_callback_query(call.id, text, show_alert=show_alert)
        
        # If callback query failed but we have important text to show, send as regular message
        if not success and text and show_alert and hasattr(call, 'from_user'):
            try:
                self.bot.send_message(call.from_user.id, f"⚠️ {text}")
                logger.debug(f"📱 Sent fallback message to user {call.from_user.id}: {text[:50]}...")
                return True
            except Exception as msg_error:
                logger.error(f"Failed to send fallback message: {msg_error}")
                return False
        
        return success
    
    def run(self):
        """Start the bot"""
        logger.info("🚀 Bot started successfully!")
        
        # Start high-frequency heartbeat to prevent cold sleep
        self.heartbeat_handler.start_heartbeat()
        
        # Start automatic cleanup service
        self.cleanup_handler.start_cleanup_service()
        
        # Start topup invoice checker (checks every 30 seconds)
        self.topup_handler.start_invoice_checker()
        
        try:
            # Use optimized infinity polling for faster response times
            self.bot.infinity_polling(
                timeout=10,  # Shorter timeout to detect connection issues faster
                long_polling_timeout=10,  # Reduce long polling timeout
                allowed_updates=None  # Process all update types
            )
        except KeyboardInterrupt:
            logger.info("🛑 Bot shutdown requested by user")
        except Exception as e:
            logger.error(f"💥 Bot polling error: {e}")
        finally:
            # Clean shutdown
            logger.info("🔄 Shutting down services...")
            self.heartbeat_handler.stop_heartbeat()
            self.cleanup_handler.stop_cleanup_service()
            logger.info("✅ Bot stopped gracefully")

if __name__ == "__main__":
    bot = ShopBot()
    bot.run()
