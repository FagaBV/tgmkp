import telebot
import logging
import json
import os
import sqlite3
from datetime import datetime, timedelta
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class ShoppingHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.categories_file = 'categories.json'
        self.products_file = 'products.json'
        
        # Import file serving handler for product images
        from handlers.file_serving_handler import FileServingHandler
        self.file_server = FileServingHandler(bot, db, language, config)
        
        # Import currency handler for price formatting
        from handlers.currency_handler import CurrencyHandler
        self.currency_handler = CurrencyHandler(bot, db, language, config)
    
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

    def load_categories(self):
        """Load categories from JSON file with caching"""
        try:
            from json_cache import json_cache
            if os.path.exists(self.categories_file):
                data = json_cache.get(self.categories_file)
                return data if data else {"categories": []}
            return {"categories": []}
        except Exception as e:
            logger.error(f"Error loading categories: {e}")
            return {"categories": []}
    
    def load_products(self):
        """Load products from JSON file with caching"""
        try:
            from json_cache import json_cache
            if os.path.exists(self.products_file):
                data = json_cache.get(self.products_file)
                return data if data else {"products": []}
            return {"products": []}
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {"products": []}
    
    def get_subcategory_product_count(self, category_id, subcategory_id):
        """Get available product count for a subcategory (excluding reserved stock)"""
        products_data = self.load_products()
        count = 0
        for product in products_data.get('products', []):
            if (product.get('category_id') == category_id and 
                product.get('subcategory_id') == subcategory_id and 
                product.get('status') == 'saved' and
                not product.get('hidden', False)):
                # Get available stock (total - reserved)
                available_stock = self.get_available_stock(product.get('id'))
                if available_stock > 0:
                    count += 1
        return count
    
    def get_available_stock(self, product_id):
        """Get available stock for a product (stock is already reduced when reserved)"""
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p.get('id') == product_id:
                product = p
                break
        
        if not product:
            return 0
        
        # Stock is already reduced when items are reserved, so just return current stock
        return max(0, product.get('stock', 0))
    
    def is_new_user(self, user_id):
        """Check if user is new (has never completed an order)"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT COUNT(*) FROM orders 
                    WHERE user_id = ? AND status = 'completed'
                ''', (user_id,))
                completed_orders = cursor.fetchone()[0]
                return completed_orders == 0
        except sqlite3.Error as e:
            logger.error(f"Error checking if user is new: {e}")
            return True  # Default to new user for safety
    
    def get_original_stock(self, product_id):
        """Get original stock amount (current stock + all reserved quantities)"""
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p.get('id') == product_id:
                product = p
                break
        
        if not product:
            return 0
        
        current_stock = product.get('stock', 0)
        reserved_stock_info = product.get('reserved_stock', [])
        
        # Add up all reserved quantities
        total_reserved = sum(r.get('quantity', 0) for r in reserved_stock_info)
        
        return current_stock + total_reserved
    
    def get_max_order_quantity(self, user_id, product_id):
        """Get maximum quantity a user can order for a product"""
        available_stock = self.get_available_stock(product_id)
        
        if available_stock <= 0:
            return 0
        
        if self.is_new_user(user_id):
            # New users can order maximum 10% of ORIGINAL total stock
            original_stock = self.get_original_stock(product_id)
            max_new_user = max(1, int(original_stock * 0.1))  # At least 1, but 10% of original stock
            return min(available_stock, max_new_user)
        else:
            # Existing users can order all available stock
            return available_stock
    
    def get_reserved_stock(self, product_id):
        """Get total reserved stock for a product from products.json reserved_stock field"""
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p.get('id') == product_id:
                product = p
                break
        
        if not product:
            return 0
        
        reserved_stock_info = product.get('reserved_stock', [])
        total_reserved = 0
        
        # Clean up expired reservations and count active ones
        active_reservations = []
        current_time = datetime.now()
        
        for reservation in reserved_stock_info:
            deadline_timestamp = reservation.get('deadline')
            if deadline_timestamp:
                try:
                    # Handle both unix timestamp and datetime string formats
                    if isinstance(deadline_timestamp, (int, float)):
                        deadline = datetime.fromtimestamp(deadline_timestamp)
                    else:
                        deadline = datetime.strptime(deadline_timestamp, '%Y-%m-%d %H:%M:%S')
                    
                    if deadline > current_time:
                        # Reservation is still active
                        active_reservations.append(reservation)
                        total_reserved += reservation.get('quantity', 0)
                except (ValueError, OSError):
                    # Invalid date format, skip this reservation
                    continue
        
        # Update the product with cleaned reservations if needed
        if len(active_reservations) != len(reserved_stock_info):
            self.update_product_reserved_stock(product_id, active_reservations)
        
        return total_reserved
    
    def update_product_reserved_stock(self, product_id, reserved_stock_list):
        """Update the reserved_stock field for a product in products.json"""
        try:
            products_data = self.load_products()
            
            # Find and update the product
            for i, product in enumerate(products_data.get('products', [])):
                if product.get('id') == product_id:
                    products_data['products'][i]['reserved_stock'] = reserved_stock_list
                    break
            
            # Save back to file
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(products_data, f, indent=4, ensure_ascii=False)
            
        except Exception as e:
            logger.error(f"Error updating reserved stock: {e}")
    
    def add_stock_reservation(self, product_id, order_id, quantity, deadline_timestamp):
        """Add a stock reservation for a specific order and reduce actual stock"""
        try:
            products_data = self.load_products()
            
            # Find the product
            for i, product in enumerate(products_data.get('products', [])):
                if product.get('id') == product_id:
                    # Check if we have enough stock
                    current_stock = product.get('stock', 0)
                    if current_stock < quantity:
                        return False
                    
                    # Initialize reserved_stock if it doesn't exist
                    if 'reserved_stock' not in product:
                        products_data['products'][i]['reserved_stock'] = []
                    
                    # Reduce actual stock
                    products_data['products'][i]['stock'] = current_stock - quantity
                    
                    # Add new reservation (for tracking purposes)
                    new_reservation = {
                        'order_id': order_id,
                        'quantity': quantity,
                        'deadline': deadline_timestamp,
                        'reserved_at': int(datetime.now().timestamp())
                    }
                    
                    products_data['products'][i]['reserved_stock'].append(new_reservation)
                    break
            
            # Save back to file
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(products_data, f, indent=4, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding stock reservation: {e}")
            return False
    
    def remove_stock_reservation(self, product_id, order_id):
        """Remove stock reservation for a specific order and restore stock"""
        try:
            products_data = self.load_products()
            
            # Find the product
            for i, product in enumerate(products_data.get('products', [])):
                if product.get('id') == product_id:
                    reserved_stock = product.get('reserved_stock', [])
                    
                    # Calculate total quantity to restore
                    quantity_to_restore = 0
                    for reservation in reserved_stock:
                        if reservation.get('order_id') == order_id:
                            quantity_to_restore += reservation.get('quantity', 0)
                    
                    # Remove reservations for this order
                    updated_reservations = [r for r in reserved_stock if r.get('order_id') != order_id]
                    products_data['products'][i]['reserved_stock'] = updated_reservations
                    
                    # Restore stock
                    current_stock = product.get('stock', 0)
                    products_data['products'][i]['stock'] = current_stock + quantity_to_restore
                    
                    break
            
            # Save back to file
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(products_data, f, indent=4, ensure_ascii=False)
            
            return True
            
        except Exception as e:
            logger.error(f"Error removing stock reservation: {e}")
            return False
    
    
    def get_stock_by_type(self, product, stock_type):
        drop_items = product.get('drop_items', [])
        return len([
            item for item in drop_items
            if item.get('stock_type', 'oras') == stock_type
        ])
        
    def pop_drop_by_stock_type(self, product, stock_type=None):
        drop_items = product.get('drop_items', [])

        if not drop_items:
            return None

        # fallback pentru produse vechi
        if not stock_type:
            return drop_items.pop(0)

        for index, item in enumerate(drop_items):
            item_type = item.get('stock_type', 'oras')

            if item_type == stock_type:
                return drop_items.pop(index)

        return None

    def handle_products_menu(self, call):
        """Handle products menu - show categories"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Load categories
        categories_data = self.load_categories()
        categories = categories_data.get('categories', [])
        
        # Get shopping categories message
        title_text = self.language.get_text('shopping_categories_title', lang_code)
        message_text = "Alege un magazin"
        
        # Create categories buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if categories:
            for category in categories:
                # Count subcategories with available products
                subcat_count = 0
                for subcat in category.get('subcategories', []):
                    if self.get_subcategory_product_count(category['id'], subcat['id']) > 0:
                        subcat_count += 1
                
                if subcat_count > 0:  # Only show categories with products
                    button_text = f"{category['name']} ({subcat_count})"
                    markup.add(telebot.types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=f'shop_cat_{category["id"]}'
                    ))
        
        if not markup.keyboard:  # No categories with products
            no_products_text = self.language.get_text('no_products_in_category', lang_code)
            message_text = no_products_text
        
        # Add back button
        back_text = self.language.get_text('back_to_menu', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='main_menu'
        ))
        
        # Edit the message
        self.send_page_with_image(
            call.message.chat.id,
            'products_menu',
            message_text,
            markup
        )

        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_category_view(self, call):
        """Handle category view - show subcategories"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract category ID
        category_id = call.data.replace('shop_cat_', '')
        
        # Load categories and find the specific one
        categories_data = self.load_categories()
        category = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                category = cat
                break
        
        if not category:
            self.bot.answer_callback_query(call.id, "❌ Category not found")
            return
        
        # Build subcategories message
        message_text = self.language.get_text('shopping_subcategories_message', lang_code)
        formatted_text = f"<b>📂 {category['name']}</b>\n\nAlege un magazin:"
        
        # Create subcategory buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        subcategories = category.get('subcategories', [])
        if subcategories:
            for subcat in subcategories:
                product_count = self.get_subcategory_product_count(category_id, subcat['id'])
                if product_count > 0:  # Only show subcategories with available products
                    button_text = f"{subcat['name']} ({product_count})"
                    markup.add(telebot.types.InlineKeyboardButton(
                        text=button_text,
                        callback_data=f'shop_subcat|{category_id}|{subcat["id"]}'
                    ))
        
        if not markup.keyboard:  # No subcategories with products
            no_subcats_text = self.language.get_text('no_subcategories_available', lang_code)
            formatted_text = f"<b>📂 {category['name']}</b>\n\n{no_subcats_text}"
        
        # Back button
        back_text = self.language.get_text('back_to_categories_shop', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='menu_products'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_subcategory_view(self, call):
        """Handle subcategory view - show products"""
        user_id = call.from_user.id

        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return

        lang_code = user['language_code']

        # Extract category and subcategory IDs safely
        parts = call.data.split('|')
        category_id = parts[1]
        subcategory_id = parts[2]

        categories_data = self.load_categories()
        category = None
        subcategory = None
        for cat in categories_data.get('categories', []):
            if cat['id'] == category_id:
                category = cat
                for subcat in cat.get('subcategories', []):
                    if subcat['id'] == subcategory_id:
                        subcategory = subcat
                        break
                break

        if not category or not subcategory:
            self.bot.answer_callback_query(call.id, "❌ Category/Subcategory not found")
            return

        products_data = self.load_products()
        products = []
        for p in products_data.get('products', []):
            if (p.get('category_id') == category_id and
                p.get('subcategory_id') == subcategory_id and
                p.get('status') == 'saved' and
                not p.get('hidden', False)):
                available_stock = self.get_available_stock(p.get('id'))
                if available_stock > 0:
                    products.append(p)

        message_text = self.language.get_text('shopping_products_message', lang_code)
        formatted_text = f"<b>🛒 Magazinul: {subcategory['name']}</b>\n"
        
        import sqlite3

        owner_id = subcategory.get(
            'owner_user_id'
        )

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        products_data_all = self.load_products()

        seller_product_ids = set()

        for prod in products_data_all.get('products', []):

            if prod.get('owner_user_id') == owner_id:

                seller_product_ids.add(
                    prod.get('id')
                )


        for prod in products_data_all.get('products', []):

            if prod.get('owner_user_id') == owner_id:

                seller_product_ids.add(
                    prod.get('id')
                )

        total_orders = 0

        cursor.execute(
            """
            SELECT products
            FROM selling_history
            """
        )

        order_rows = cursor.fetchall()

        for row in order_rows:

            try:

                order_products = json.loads(row[0])

                for item in order_products:

                    if item.get('product_id') in seller_product_ids:

                        total_orders += int(
                            item.get(
                                'quantity',
                                1
                            )
                        )

            except Exception as e:

                print("JSON ERROR:", e)
                
        total_rating = 0
        total_reviews = 0

        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT product_ids,
                   star_rating
            FROM reviews
            """
        )

        review_rows = cursor.fetchall()

        for row in review_rows:

            try:

                review_product_ids = json.loads(
                    row[0]
                )

                found = False

                for product_id in review_product_ids:

                    if product_id in seller_product_ids:

                        found = True
                        break

                if found:

                    total_rating += int(
                        row[1]
                    )

                    total_reviews += 1

            except:
                pass

        avg_rating = 0

        if total_reviews > 0:

            avg_rating = round(
                total_rating / total_reviews,
                1
            )
        
        shop_description = subcategory.get('description', '')
        shop_image = subcategory.get('shop_image')
        markup = telebot.types.InlineKeyboardMarkup()

        if products:
            for product in products:
                price = self.currency_handler.format_price(product['price'])
                button_text = f"{product['name']}"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f'shop_product_{product["id"]}'
                ))
        else:
            no_products_text = self.language.get_text('no_products_in_category', lang_code)
        
        
        if shop_description:
            formatted_text += f"\n{shop_description}"

        formatted_text += (
            "\n━━━━━━━━━━━━━━\n"
            f"📦 <b>Comenzi Totale:</b> {total_orders}\n"
            f"⭐ <b>Rating Magazin:</b> {avg_rating}/5 ({total_reviews} recenzii)"
        )

        back_text = self.language.get_text('back_to_subcategories_shop', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'shop_cat_{category_id}'
        ))
    
        try:
            if shop_image:
                self.bot.send_photo(
                    chat_id=call.message.chat.id,
                    photo=shop_image,
                    caption=formatted_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            else:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=formatted_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Error sending subcategory/shop view: {e}")
        
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_view(self, call):
        """Handle product view - show product details with images"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extract product ID
        product_id = call.data.replace('shop_product_', '')
        
        # Load products and find the specific one
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p.get('id') == product_id and p.get('status') == 'saved':
                product = p
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Get category and subcategory names
        categories_data = self.load_categories()
        category_name = "Unknown"
        subcategory_name = "Unknown"
        
        for cat in categories_data.get('categories', []):
            if cat['id'] == product['category_id']:
                category_name = cat['name']
                for subcat in cat.get('subcategories', []):
                    if subcat['id'] == product['subcategory_id']:
                        subcategory_name = subcat['name']
                        break
                break
        
        # Get stock information
        available_stock = self.get_available_stock(product_id)
        max_order_quantity = self.get_max_order_quantity(user_id, product_id)
        
        if max_order_quantity <= 0:
            if self.is_new_user(user_id) and available_stock > 0:
                # New user hit their limit
                original_stock = self.get_original_stock(product_id)
                max_allowed = max(1, int(original_stock * 0.1))
                limit_text = self.language.get_text('limit_reached', lang_code)
                self.bot.answer_callback_query(call.id, limit_text.format(max_allowed=max_allowed), show_alert=True)
            else:
                # Out of stock
                out_of_stock_text = self.language.get_text('out_of_stock', lang_code)
                self.bot.answer_callback_query(call.id, out_of_stock_text)
            return
        
        # Format product details
        price = self.currency_handler.format_price(product['price'])
        available_stock = self.get_available_stock(product_id)
        max_order_quantity = self.get_max_order_quantity(user_id, product_id)

        formatted_text = (
            f"{product.get('description', 'Acest magazin nu are o descriere')}"
            f"\n\n📦 <b>ATENTIE: Selecteaza tipul de drop de mai jos pentru a beneficia de un drop preselectat (drop in padure sau drop in oras)</b>\n"
            f"\n\n"

        )

        formatted_text += (
            f"💰 <b>Preț: </b> {price}"
        )

        # Create quantity control buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Row 1: +1, Custom Amount, -1
        plus_text = self.language.get_text('quantity_controls_row1', lang_code)
        custom_text = self.language.get_text('quantity_controls_custom', lang_code)
        minus_text = self.language.get_text('quantity_controls_row1_down', lang_code)
        
        markup.row(
            telebot.types.InlineKeyboardButton(
                "🌲 +1 Pădure",
                callback_data=f"shop_add|{product_id}|padure|1"
            ),
            telebot.types.InlineKeyboardButton(
                "🏙️ +1 Oraș",
                callback_data=f"shop_add|{product_id}|oras|1"
            )
        )
        
        # Row 2: Cart quick view (shows total dynamically when returning to main menu)
        cart_text = self.language.get_text('cart_title', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cart_text,
            callback_data='menu_cart'
        ))
        
        # Row 3: Reviews and Back
        # Reviews button (conditional and with average rating)
        if product.get('reviews_enabled', True):  # Only show if reviews are enabled
            # Get review summary from review handler
            from handlers.review_handler import ReviewHandler
            review_handler = ReviewHandler(self.bot, self.db, self.language, self.config)
            review_summary = review_handler.get_product_review_summary(product_id)
            
            if review_summary:
                # Show average rating
                reviews_text = self.language.get_text('reviews_button_format', lang_code).format(
                    average=review_summary['average_rating']
                )
            else:
                # No reviews yet
                reviews_text = self.language.get_text('review_button', lang_code)
            
            back_text = self.language.get_text('back_to_products_shop', lang_code)
            markup.row(
                telebot.types.InlineKeyboardButton(text=reviews_text, callback_data=f'product_reviews|{product_id}|0'),
                telebot.types.InlineKeyboardButton(text=back_text, callback_data=f'shop_subcat|{product["category_id"]}|{product["subcategory_id"]}')
            )
        else:
            # No reviews button, just back button
            back_text = self.language.get_text('back_to_products_shop', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(text=back_text, callback_data=f'shop_subcat|{product["category_id"]}|{product["subcategory_id"]}'))
        
        # Send product images if available
        if product.get('images') and len(product['images']) > 0:
            # Delete the previous message since we're sending images
            try:
                self.bot.delete_message(call.message.chat.id, call.message.message_id)
            except:
                pass
            
            # Send all images as a gallery
            success = self.file_server.send_product_gallery(
                chat_id=call.message.chat.id,
                product_images=product['images'],  # Send ALL images as gallery
                product_name=product['name']  # Include product name
            )
            
            if success:
                # Send the detailed message separately with buttons
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=formatted_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            else:
                # Fallback: send text message if images fail
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=formatted_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
        else:
            # No images, just edit the message
            try:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=formatted_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_cart_view(self, call):
        """Handle cart view - show user's cart"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Get user's active order
        order = self.get_or_create_order(user_id)
        
        if not order or not order.get('products'):
            # Empty cart
            empty_text = self.language.get_text('cart_empty', lang_code)
            markup = telebot.types.InlineKeyboardMarkup()
            back_text = self.language.get_text('back_to_menu', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            try:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=empty_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
        else:
            # Show cart contents
            cart_items = self.format_cart_items(order['products'], lang_code)
            total_cost = self.currency_handler.format_price(order['total_cost'])
            deadline = order['deadline']
            
            cart_text = self.language.get_text('cart_message', lang_code)
            formatted_text = cart_text.format(
                cart_items=cart_items,
                total_cost=total_cost,
                deadline=deadline
            )
            
            markup = telebot.types.InlineKeyboardMarkup()
            # Add checkout and clear cart buttons here later
            back_text = self.language.get_text('back_to_menu', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=back_text,
                callback_data='main_menu'
            ))
            
            try:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=formatted_text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def get_or_create_order(self, user_id):
        """Get existing order or create new one"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Check for existing pending order that hasn't expired
                current_timestamp = int(datetime.now().timestamp())
                cursor.execute('''
                    SELECT id, user_id, username, products, total_cost, status, deadline, created_at
                    FROM orders 
                    WHERE user_id = ? AND status = 'pending' AND deadline > ?
                    ORDER BY created_at DESC LIMIT 1
                ''', (user_id, current_timestamp))
                
                order = cursor.fetchone()
                
                if order:
                    return {
                        'id': order[0],
                        'user_id': order[1],
                        'username': order[2],
                        'products': json.loads(order[3]) if order[3] else [],
                        'total_cost': order[4],
                        'status': order[5],
                        'deadline': order[6],
                        'created_at': order[7]
                    }
                
                return None
                
        except sqlite3.Error as e:
            logger.error(f"Error getting order: {e}")
            return None
    
    def format_cart_items(self, products, lang_code):
        """Format cart items for display"""
        if not products:
            return ""
        
        items = []
        for item in products:
            name = item.get('name', 'Unknown Product')
            quantity = item.get('quantity', 0)
            price = self.currency_handler.format_price(item.get('unit_price', 0))
            total = self.currency_handler.format_price(item.get('total_price', 0))
            items.append(f"• {name} x{quantity} - {price} each = {total}")
        
        return "\n".join(items)
    
    def handle_add_to_cart(self, call, quantity=1):
        """Handle adding items to cart"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        stock_type = None

        if call.data.startswith('shop_add|'):
            parts = call.data.split('|')

            # format nou: shop_add|product_id|padure|1
            if len(parts) == 4:
                product_id = parts[1]
                stock_type = parts[2]
                quantity = int(parts[3])

            # format vechi: shop_add|1|product_id
            else:
                quantity = int(parts[1])
                product_id = parts[2]

        elif call.data.startswith('shop_sub|'):
            parts = call.data.split('|')

            # format nou: shop_sub|product_id|padure|1
            if len(parts) == 4:
                product_id = parts[1]
                stock_type = parts[2]
                quantity = -int(parts[3])

            # format vechi: shop_sub|1|product_id
            else:
                quantity = -int(parts[1])
                product_id = parts[2]

        else:
            return
        
        # Load product
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p.get('id') == product_id and p.get('status') == 'saved':
                product = p
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
            
        if product.get('type') == 'drop' and stock_type:
            available_for_type = self.get_stock_by_type(product, stock_type)

            if available_for_type <= 0:
                self.bot.answer_callback_query(
                    call.id,
                    "❌ Nu mai există stock pentru categoria selectată.",
                    show_alert=True
                )
                return

            if quantity > available_for_type:
                self.bot.answer_callback_query(
                    call.id,
                    f"❌ Maxim disponibil: {available_for_type}",
                    show_alert=True
                )
                return
        
        # Check maximum order quantity for this user
        max_order_quantity = self.get_max_order_quantity(user_id, product_id)
        
        if quantity > 0 and quantity > max_order_quantity:
            if self.is_new_user(user_id):
                # New user hit their limit
                original_stock = self.get_original_stock(product_id)
                max_allowed = max(1, int(original_stock * 0.1))
                limit_text = self.language.get_text('limit_reached', lang_code)
                self.bot.answer_callback_query(call.id, limit_text.format(max_allowed=max_allowed), show_alert=True)
            else:
                error_text = self.language.get_text('amount_exceeds_stock', lang_code)
                formatted_error = error_text.format(max_stock=max_order_quantity)
                self.bot.answer_callback_query(call.id, formatted_error, show_alert=True)
            return
        
        # Get or create order
        order = self.get_or_create_order(user_id)
        
        if not order:
            # Create new order
            order = self.create_new_order(user_id, user.get('username', ''))
        
        # Validate product type compatibility before adding
        if not self.validate_product_type_compatibility(order, product, lang_code, call):
            return  # Validation failed, user was notified
        
        # Add/update item in cart
        success, message = self.update_cart_item(order, product, quantity, lang_code, stock_type)
        
        if success:
            # Show success message as popup notification with OK button
            self.safe_answer_callback_query(call, message, show_alert=True)
        else:
            # Show error message as popup notification
            self.safe_answer_callback_query(call, message, show_alert=True)
  
        logger.warning(f"DEBUG STOCK TYPE: {stock_type}")
  
    def create_new_order(self, user_id, username):
        """Create a new order for the user"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Calculate deadline as unix timestamp
                expiry_minutes = self.config.get('order_expiry_minutes', 15)
                deadline_dt = datetime.now() + timedelta(minutes=expiry_minutes)
                deadline_timestamp = int(deadline_dt.timestamp())
                
                cursor.execute('''
                    INSERT INTO orders (user_id, username, products, total_cost, status, deadline)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, '[]', 0.0, 'pending', deadline_timestamp))
                
                order_id = cursor.lastrowid
                
                return {
                    'id': order_id,
                    'user_id': user_id,
                    'username': username,
                    'products': [],
                    'total_cost': 0.0,
                    'status': 'pending',
                    'deadline': deadline_timestamp,
                    'created_at': int(datetime.now().timestamp())
                }
                
        except sqlite3.Error as e:
            logger.error(f"Error creating order: {e}")
            return None
    
    def update_cart_item(self, order, product, quantity_change, lang_code, stock_type=None):
        """Update item quantity in cart and manage stock reservations"""
        try:
            products = order['products'].copy() if order['products'] else []
            product_id = product.get('id')
            order_id = order['id']
                
            if not product_id:
                logger.error(f"Product missing id in update_cart_item: {product}")
                return False, "❌ Produs invalid."
            # Find existing item in cart
            existing_item_index = None
            current_reserved_quantity = 0
            for i, item in enumerate(products):
                if item.get('product_id') == product_id and item.get('stock_type') == stock_type:
                    existing_item_index = i
                    current_reserved_quantity = item.get('quantity', 0)
                    break
            
            if existing_item_index is not None:
                # Update existing item
                current_quantity = products[existing_item_index]['quantity']
                new_quantity = current_quantity + quantity_change
                
                if new_quantity <= 0:
                    # Remove item from cart and remove reservation
                    products.pop(existing_item_index)
                    self.remove_stock_reservation(product_id, order_id)
                    message = self.language.get_text('removed_from_cart_alert', lang_code)
                else:
                    # Update quantity and reservation
                    products[existing_item_index]['quantity'] = new_quantity
                    products[existing_item_index]['total_price'] = new_quantity * product['price']
                    
                    # Update stock reservation
                    self.remove_stock_reservation(product_id, order_id)  # Remove old reservation
                    deadline_timestamp = order['deadline']
                    self.add_stock_reservation(product_id, order_id, new_quantity, deadline_timestamp)  # Add new reservation
                    
                    message = self.language.get_text('updated_cart_alert', lang_code)
            else:
                # Add new item (only if quantity is positive)
                if quantity_change > 0:
                    new_item = {
                        'product_id': product_id,
                        'name': product['name'],
                        'code': product.get('code', product.get('id')),
                        'unit_price': product['price'],
                        'quantity': quantity_change,
                        'total_price': quantity_change * product['price'],
                        'type': product.get('type', 'delivered'),
                        'stock_type': stock_type
                    }
                    products.append(new_item)
                    
                    # Add stock reservation
                    deadline_timestamp = order['deadline']
                    self.add_stock_reservation(product_id, order_id, quantity_change, deadline_timestamp)
                    
                    message = self.language.get_text('added_to_cart_alert', lang_code)
                else:
                    return False, "❌ Item not in cart"
            
            # Calculate new total cost
            total_cost = sum(item['total_price'] for item in products)
            
            # Update order in database
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE orders 
                    SET products = ?, total_cost = ?, updated_at = datetime('now')
                    WHERE id = ?
                ''', (json.dumps(products), total_cost, order['id']))
            
            return True, message
            
        except Exception as e:
            logger.error(f"Error updating cart: {e}")
            return False, "❌ Error updating cart"
    
    def handle_custom_amount(self, call):
        """Handle custom amount input"""
        user_id = call.from_user.id
        
        # Get user's language preference
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        
        # Extrag datele [F2]
        if call.data.startswith('shop_custom|'):
            parts = call.data.split('|')
            product_id = parts[1]
        else:
            product_id = call.data.replace('shop_custom_', '')       
        # Load product to get max stock
        products_data = self.load_products()
        product = None
        for p in products_data.get('products', []):
            if p.get('id') == product_id and p.get('status') == 'saved':
                product = p
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        max_order_quantity = self.get_max_order_quantity(user_id, product_id)
        
        # Set user state for custom amount input
        self.db.set_user_state(
            user_id=user_id,
            state='shopping_custom_amount',
            data=json.dumps({
                'lang_code': lang_code,
                'product_id': product_id,
                'max_stock': max_order_quantity
            }),
            message_id=call.message.message_id
        )
        
        # Send custom amount prompt
        prompt_text = self.language.get_text('custom_amount_prompt', lang_code)
        formatted_prompt = prompt_text.format(max_stock=max_order_quantity)
        
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_to_products_shop', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='shopping_back_clear_state'
        ))
        
        
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=formatted_prompt,
            reply_markup=markup,
            parse_mode='HTML'
        )
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_custom_amount_input(self, message):
        """Handle custom amount text input"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or user_state['state'] != 'shopping_custom_amount':
            return False
        
        try:
            # user_state['data'] is already parsed by database.py
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_id = state_data['product_id']
            max_stock = state_data['max_stock']
        except (json.JSONDecodeError, KeyError):
            return False
        
        # Parse user input
        try:
            quantity = int(message.text.strip())
            if quantity < 1 or quantity > max_stock:
                error_text = self.language.get_text('invalid_amount', lang_code)
                formatted_error = error_text.format(max_stock=max_stock)
                self.bot.send_message(message.chat.id, formatted_error)
                return True
        except ValueError:
            error_text = self.language.get_text('invalid_amount', lang_code)
            formatted_error = error_text.format(max_stock=max_stock)
            self.bot.send_message(message.chat.id, formatted_error)
            return True
        
        # Clear user state
        self.db.clear_user_state(user_id)
        
        # Delete user's message and prompt message
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
            self.bot.delete_message(message.chat.id, user_state['message_id'])
        except:
            pass
        
        # Create fake call object for add_to_cart
        from types import SimpleNamespace
        fake_call = SimpleNamespace()
        fake_call.data = f'shop_add|{quantity}_{product_id}'
        fake_call.from_user = message.from_user
        fake_call.message = message
        fake_call.id = None
        
        # Add to cart
        self.handle_add_to_cart(fake_call)
        
        return True
    
    def handle_back_clear_state(self, call):
        """Handle back button that clears user state"""
        user_id = call.from_user.id
        self.db.clear_user_state(user_id)
        
        # Redirect back to main menu
        from handlers.menu_handler import MenuHandler
        menu_handler = MenuHandler(self.bot, self.db, self.language, self.config)
        
        fake_call = call
        fake_call.data = 'main_menu'
        menu_handler.handle_main_menu(fake_call)
    
    def handle_text_input(self, message):
        """Handle text input for shopping states"""
        return self.handle_custom_amount_input(message)
    
    def cleanup_expired_orders(self):
        """Clean up expired orders and their stock reservations"""
        try:
            with sqlite3.connect(self.db.db_path) as conn:
                cursor = conn.cursor()
                
                # Find expired orders
                current_timestamp = int(datetime.now().timestamp())
                cursor.execute('''
                    SELECT id, products FROM orders 
                    WHERE status = 'pending' AND deadline <= ?
                ''', (current_timestamp,))
                expired_orders = cursor.fetchall()
                
                # Remove stock reservations for expired orders
                for order_id, products_json in expired_orders:
                    try:
                        products = json.loads(products_json)
                        for item in products:
                            product_id = item.get('product_id')
                            if product_id:
                                self.remove_stock_reservation(product_id, order_id)
                    except json.JSONDecodeError:
                        continue
                
                # Update order status to expired
                cursor.execute('''
                    UPDATE orders 
                    SET status = 'expired', updated_at = ?
                    WHERE status = 'pending' AND deadline <= ?
                ''', (current_timestamp, current_timestamp))
                
                conn.commit()
                logger.info(f"Cleaned up {len(expired_orders)} expired orders")
                
        except Exception as e:
            logger.error(f"Error cleaning up expired orders: {e}")
    
    def safe_answer_callback_query(self, call, text=None, show_alert=False):
        """Safely answer callback query with error handling"""
        if not hasattr(call, 'id') or call.id is None:
            logger.debug("🚫 Invalid callback query - missing ID")
            return False
        
        # Try to answer the callback query
        success = self.bot.answer_callback_query(call.id, text, show_alert=show_alert)
        
        # If callback query failed but we have important text to show, send as regular message
        if not success and text and show_alert and hasattr(call, 'from_user'):
            try:
                
                self.bot.send_message(call.from_user.id, text)
                logger.debug(f"📱 Sent fallback message to user {call.from_user.id}: {text[:50]}...")
                return True
            except Exception as msg_error:
                logger.error(f"Failed to send fallback message: {msg_error}")
                return False
        
        return success

    def validate_product_type_compatibility(self, order, product, lang_code, call):
        """Validate that the product type is compatible with existing cart items"""
        try:
            # Get current products in the order (already parsed as list)
            current_products = order.get('products', [])
            
            # If cart is empty, any product type is allowed
            if not current_products:
                return True
            
            # Get the new product type
            new_product_type = product.get('type', 'delivered')
            
            # Get existing product types in cart
            existing_types = set()
            for item in current_products:
                existing_types.add(item.get('type', 'delivered'))
            
            # Check if new type is compatible with existing types
            if new_product_type not in existing_types:
                # Different type detected - show error message
                validation_data = self.language.languages.get(lang_code, {}).get('product_type_validation', {})
                
                # Format existing types for display
                type_names = []
                for existing_type in existing_types:
                    type_name = validation_data.get(existing_type, existing_type)
                    type_names.append(type_name)
                
                current_types_text = ', '.join(type_names)
                new_type_text = validation_data.get(new_product_type, new_product_type)
                
                # Get error message template
                error_template = validation_data.get('mixed_types_error', 
                    '⚠️ Cannot mix different product types in one order!')
                
                # Format the error message
                error_message = error_template.format(
                    current_types=current_types_text,
                    new_type=new_type_text
                )
                
                # Show error as alert
                self.safe_answer_callback_query(call, error_message, show_alert=True)
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating product type compatibility: {e}")
            # On error, allow the addition (fail-safe)
            return True
    
    def get_product_type_info(self, product):
        """Get information about how to handle different product types"""
        product_type = product.get('type', 'delivered')
        
        if product_type == 'downloadable':
            return {
                'type': 'downloadable',
                'requires_files': True,
                'has_downloadable_content': bool(product.get('files')),
                'stock_type': 'digital'  # Can be unlimited in theory
            }
        elif product_type == 'line_file':
            return {
                'type': 'one_liner',
                'requires_files': False,
                'has_line_content': bool(product.get('line_content')),
                'stock_type': 'limited'  # Each line is unique
            }
        elif product_type == 'drop':
            drop_items = product.get('drop_items', [])
            drop_caption = product.get('drop_caption', '')

            if not drop_items:
                return {
                    'type': 'drop',
                    'delivered': False,
                    'error': 'Nu mai exista stock pentru acest produs.'
                }

            return {
                'type': 'drop',
                'delivered': True,
                'drop_item': drop_item,
                'drop_caption': drop_caption,
                'remaining_stock': len(drop_items)
            }
        else:  # delivered
            return {
                'type': 'delivered',
                'requires_files': False,
                'has_physical_delivery': True,
                'stock_type': 'limited'  # Physical items are limited
            }
    
    def format_price(self, amount):
        """Format price with currency symbol"""
        try:
            currency_symbol = self.config.get('currency', {}).get('symbol', '$')
            return f"{currency_symbol}{amount:.2f}"
        except:
            return f"${amount:.2f}"
