import telebot
import logging
import json
import sqlite3
import os
import shutil
from cache_manager import save_json_safely
from utils import replace_message


logger = logging.getLogger(__name__)

class ProductHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.categories_file = 'categories.json'
        self.products_file = 'products.json'
        self.images_dir = 'images'
        self.products_dir = 'products'
        
        # Initialize product creation handler
        from handlers.product_creation_handler import ProductCreationHandler
        self.creation_handler = ProductCreationHandler(bot, db, language, config)
        
        # Initialize product file handler
        from handlers.product_file_handler import ProductFileHandler
        self.file_handler = ProductFileHandler(bot, db, language, config)
    
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
    
    def get_category_product_count(self, category_id):
        """Get total product count for a category"""
        products_data = self.load_products()
        count = 0
        for product in products_data.get('products', []):
            if (product.get('category_id') == category_id and 
                product.get('status') == 'saved'):
                count += 1
        return count
    
    def get_subcategory_product_count(self, category_id, subcategory_id):
        """Get product count for a subcategory"""
        products_data = self.load_products()
        count = 0
        for product in products_data.get('products', []):
            if (product.get('category_id') == category_id and 
                product.get('subcategory_id') == subcategory_id and 
                product.get('status') == 'saved'):
                count += 1
        return count
    
    def handle_products_management(self, call):
        """Handle main products management screen - show categories"""
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
        
        # Clean up any pending products before showing products management
        self.creation_handler.cleanup_pending_products()
        
        # Load categories
        categories_data = self.load_categories()
        categories = categories_data.get('categories', [])
        
        # Get products management text
        menu_text = self.language.get_text('products_management', lang_code)
        
        # Create categories buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if categories:
            # Add existing categories with product counts
            for category in categories:
                product_count = self.get_category_product_count(category['id'])
                button_text = f"{category['name']} ({product_count})"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f'prod_cat_{category["id"]}'
                ))
        else:
            # No categories message
            no_categories_text = self.language.get_text('no_categories_for_products', lang_code)
            menu_text = no_categories_text
        
        # Add back button
        back_admin_text = self.language.get_text('back_to_admin_panel', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_admin_text,
            callback_data='admin_panel'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_category_view(self, call):
        """Handle viewing subcategories in a category for products"""
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
        
        # Extract category ID
        category_id = call.data.replace('prod_cat_', '')
        
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
        
        # Build category view text
        menu_text = f"<b>📂 {category['name']}</b>\n\nSelect subcategory to manage products:"
        
        subcategories = category.get('subcategories', [])
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if subcategories:
            # Add subcategory buttons with product counts
            for subcat in subcategories:
                product_count = self.get_subcategory_product_count(category_id, subcat['id'])
                button_text = f"{subcat['name']} ({product_count})"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=button_text,
                    callback_data=f'prod_subcat_{category_id}_{subcat["id"]}'
                ))
        else:
            # No subcategories message
            no_subcats_text = self.language.get_text('no_subcategories_for_products', lang_code)
            menu_text = f"<b>📂 {category['name']}</b>\n\n{no_subcats_text}"
        
        # Back button
        back_text = self.language.get_text('back_to_product_categories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data='admin_products'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_subcategory_view(self, call):
        """Handle viewing products in a subcategory"""
        user_id = call.from_user.id
        
        # Clear any input state when navigating back to product list
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
        
        # Extract category and subcategory IDs
        parts = call.data.replace('prod_subcat_', '').split('_')
        category_id = parts[0]
        subcategory_id = parts[1]
        
        # Load categories and find the subcategory
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
        
        # Load products and filter for this subcategory (only saved products)
        products_data = self.load_products()
        products = [p for p in products_data.get('products', []) 
                   if (p.get('category_id') == category_id and 
                       p.get('subcategory_id') == subcategory_id and 
                       p.get('status') == 'saved')]
        
        # Build subcategory view text
        menu_text = f"<b>📁 {subcategory['name']}</b>\n<i>in {category['name']}</i>\n\n"
        
        # Create buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        if products:
            menu_text += f"<b>Products ({len(products)}):</b>\n"
            # Add product buttons with edit options
            for product in products:
                # Product info row
                product_status = "👁️" if product.get('hidden', False) else "✅"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=f"{product_status} {product['name']} - ${product['price']}",
                    callback_data=f'prod_view_{product["id"]}'
                ))
        else:
            # No products message
            no_products_text = self.language.get_text('no_products_found', lang_code)
            menu_text += no_products_text
        
        # Add new product button
        add_new_text = self.language.get_text('add_new_product', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=add_new_text,
            callback_data=f'prod_add_{category_id}_{subcategory_id}'
        ))
        
        # Back button
        back_text = self.language.get_text('back_to_product_subcategories', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'prod_cat_{category_id}'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_view(self, call):
        """Handle viewing and editing a specific product"""
        user_id = call.from_user.id
        
        # Clear any input state when viewing product (back button effect)
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
        
        # Extract product ID
        product_id = call.data.replace('prod_view_', '')
        
        # Load products and find the specific one (only saved products)
        products_data = self.load_products()
        product = None
        for prod in products_data.get('products', []):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product = prod
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Build product view text
        status = "Hidden" if product.get('hidden', False) else "Active"
        reviews_status = "Enabled" if product.get('reviews_enabled', True) else "Disabled"
        menu_text = f"<b>📦 {product['name']}</b>\n\n"
        menu_text += f"💰 <b>Pret:</b> ${product['price']}\n"
        menu_text += f"📋 <b>Tip:</b> {product['type']}\n"
        menu_text += f"📊 <b>Status:</b> {status}\n"
        menu_text += f"📂 <b>Stock:</b> {product.get('stock', 'N/A')}\n"
        menu_text += f"⭐ <b>Review-uri:</b> {reviews_status}\n\n"
        menu_text += f"<b>Descriere:</b>\n{product.get('description', 'No description')}"
        
        # Create edit buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        # Edit options
        edit_name_text = self.language.get_text('edit_product_name', lang_code)
        edit_code_text = self.language.get_text('edit_product_code', lang_code)
        edit_desc_text = self.language.get_text('edit_product_description', lang_code)
        edit_price_text = self.language.get_text('edit_product_price', lang_code)
        edit_quantity_text = self.language.get_text('edit_product_quantity', lang_code)
        hide_text = self.language.get_text('hide_product', lang_code)
        delete_text = self.language.get_text('delete_product', lang_code)
        change_category_text = self.language.get_text('change_product_category', lang_code)
        
        # Row 1: Edit name, code
        markup.row(
            telebot.types.InlineKeyboardButton(text=edit_name_text, callback_data=f'prod_edit_name_{product_id}'),
            telebot.types.InlineKeyboardButton(text=edit_code_text, callback_data=f'prod_edit_code_{product_id}')
        )
        
        # Row 2: Edit description, price
        markup.row(
            telebot.types.InlineKeyboardButton(text=edit_desc_text, callback_data=f'prod_edit_desc_{product_id}'),
            telebot.types.InlineKeyboardButton(text=edit_price_text, callback_data=f'prod_edit_price_{product_id}')
        )
        
        # Row 3: Edit quantity/upload more based on product type, reviews
        hide_show_text = "👁️ Show" if product.get('hidden', False) else "🙈 Hide"
        edit_reviews_text = self.language.get_text('edit_review_settings', lang_code)
        
        # Different button based on product type
        product_type = product.get('type', 'delivered')
        if product_type == 'delivered':
            # Delivered products can edit quantity
            quantity_button_text = edit_quantity_text
            quantity_callback = f'prod_edit_quantity_{product_id}'
        else:
            # Downloadable and line_file products show "Upload More"
            quantity_button_text = "📤 Adauga Stock [DROP]"
            quantity_callback = f'prod_upload_more_{product_id}'
        
        markup.row(
            telebot.types.InlineKeyboardButton(text=quantity_button_text, callback_data=quantity_callback),
            telebot.types.InlineKeyboardButton(text=edit_reviews_text, callback_data=f'prod_edit_reviews_{product_id}')
        )
        if product.get('type') == 'drop':
            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="🛠 Editeaza Drop",
                    callback_data=f'prod_edit_drops_{product_id}'
                )
            )
        markup.row(
            telebot.types.InlineKeyboardButton(text=hide_show_text, callback_data=f'prod_toggle_visibility_{product_id}')
        )
        
        # Row 4: Premium features (show alert)
        markup.row(
            telebot.types.InlineKeyboardButton(text=change_category_text, callback_data=f'prod_premium_alert'),
            telebot.types.InlineKeyboardButton(text=delete_text, callback_data=f'prod_delete_{product_id}')
        )
        
        # Back button
        back_text = self.language.get_text('back_to_products', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data=f'prod_subcat_{product["category_id"]}_{product["subcategory_id"]}'
        ))
        
        # Edit the message
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=menu_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        # Answer callback query
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)

    #[F2] Handler pentru introducere produselor
    def handle_seller_product_input(self, message):
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)

        if not user_state:
            return False

        if user_state.get('state') != 'seller_creating_product':
            return False

        product_name = (message.text or "").strip()
        if not product_name or len(product_name) > 100:
            
            self.bot.send_message(message.chat.id, "❌ Nume invalid.")
            return True

        seller_info = self.db.get_seller_info(user_id)
        if not seller_info:
            
            self.bot.send_message(message.chat.id, "❌ Seller info not found.")
            return True

        ok = self.create_seller_product(
            user_id,
            seller_info['seller_city_id'],
            seller_info['seller_subcategory_id'],
            product_name
        )

        self.db.clear_user_state(user_id)

        if ok:
            
            self.bot.send_message(
                message.chat.id,
                f"✅ Produsul <b>{product_name}</b> a fost creat.",
                parse_mode='HTML'
            )
        else:
            
            self.bot.send_message(message.chat.id, "❌ Nu s-a putut crea produsul.")

        return True
        
    #[F2] Adaugam metodele in clasa pt produselor
    def get_seller_subcategories(self, shop_subcategory_id, owner_user_id):
        """Return seller-owned internal subcategories from a seller shop"""
        categories_data = self.load_categories()

        for category in categories_data.get('categories', []):
            for subcat in category.get('subcategories', []):
                if (
                    subcat.get('id') == shop_subcategory_id and
                    subcat.get('owner_user_id') == owner_user_id and
                    subcat.get('is_seller_shop') is True
                ):
                    return subcat.get('seller_subcategories', [])

        return []

    def get_seller_subcategory_by_id(self, seller_subcategory_id, owner_user_id):
        """Find one internal seller subcategory by id"""
        categories_data = self.load_categories()

        for category in categories_data.get('categories', []):
            for subcat in category.get('subcategories', []):
                if (
                    subcat.get('owner_user_id') == owner_user_id and
                    subcat.get('is_seller_shop') is True
                ):
                    for seller_subcat in subcat.get('seller_subcategories', []):
                        if seller_subcat.get('id') == seller_subcategory_id:
                            return seller_subcat

        return None    

    #[F2] Handler pt prduse
    def get_seller_shop_products(self, owner_user_id, shop_subcategory_id):
        products_data = self.load_products()
        result = []

        for product in products_data.get('products', []):
            if (
                product.get('owner_user_id') == owner_user_id and
                product.get('subcategory_id') == shop_subcategory_id and
                product.get('is_seller_product') is True
            ):
                result.append(product)

        return result

    #[F2] Creare de produse
    def create_seller_product(self, owner_user_id, city_id, shop_subcategory_id, product_name):
        products_data = self.load_products()

        if 'products' not in products_data:
            products_data['products'] = []

        new_id = f"seller_prod_{owner_user_id}_{len(products_data['products']) + 1}"

        new_product = {
            "id": new_id,
            "code": new_id,
            "name": product_name,
            "description": "",
            "price": 0,
            "stock": 0,
            "type": "drop",
            "images": [],
            "files": [],
            "drop_items": [],
            "drop_caption": None,
            "status": "saved",
            "hidden": False,
            "owner_user_id": owner_user_id,
            "category_id": city_id,
            "subcategory_id": shop_subcategory_id,
            "is_seller_product": True,
            "reviews_enabled": True
        }

        products_data['products'].append(new_product)
        return self.save_products(products_data)
    
    #[F2] Modul de stergere produs facut de seller
    def delete_seller_product(self, owner_user_id, product_id):
        products_data = self.load_products()
        products = products_data.get('products', [])

        new_products = []
        deleted = False

        for product in products:
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                deleted = True
                continue
            new_products.append(product)

        if not deleted:
            return False

        products_data['products'] = new_products
        return self.save_products(products_data)
    
    # [F2] Metoda noua pentru poze
    def update_seller_product_image(self, owner_user_id, product_id, file_id, photo_obj=None):
        products_data = self.load_products()

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                image_data = {
                    'file_id': file_id,
                    'file_unique_id': getattr(photo_obj, 'file_unique_id', None) if photo_obj else None,
                    'width': getattr(photo_obj, 'width', None) if photo_obj else None,
                    'height': getattr(photo_obj, 'height', None) if photo_obj else None,
                    'type': 'photo'
                }

                product['images'] = [image_data]
                return self.save_products(products_data)

        return False    
    
    # [F2] Handler pentru produse si metodele de functionare
    def update_seller_product_field(self, owner_user_id, product_id, field_name, value):
        products_data = self.load_products()
        updated = False

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                product[field_name] = value
                updated = True
                break

        if not updated:
            return False

        return self.save_products(products_data)    
   
    #[F2] Logica drop-urilor pentru selleri
    def add_seller_drop(self, owner_user_id, product_id, file_id, caption, stock_type='oras'):
        products_data = self.load_products()

        if stock_type not in ['padure', 'oras']:
            stock_type = 'oras'

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                if 'drop_items' not in product:
                    product['drop_items'] = []

                product['drop_items'].append({
                    'file_id': file_id,
                    'caption': caption or '',
                    'type': 'photo',
                    'stock_type': stock_type
                })

                product['stock'] = len(product['drop_items'])
                return self.save_products(products_data)

        return False


    def replace_seller_drop_image(self, owner_user_id, product_id, index, new_file_id):
        products_data = self.load_products()

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                drop_items = product.get('drop_items', [])
                if 0 <= index < len(drop_items):
                    drop_items[index]['file_id'] = new_file_id
                    return self.save_products(products_data)

        return False

    # [F2] Logica pentru text-ul drop-urilor
    def handle_seller_drop_text_input(self, message):
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)

        if not user_state:
            return False

        state_name = user_state.get('state')
        if state_name != 'seller_editing_drop_caption':
            return False

        state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
        product_id = state_data.get('product_id')
        index = int(state_data.get('index'))

        new_caption = (message.text or '').strip()
        if not new_caption:
            
            self.bot.send_message(message.chat.id, "❌ Coordonate invalide.")
            return True

        ok = self.update_seller_drop_caption(user_id, product_id, index, new_caption)
        self.db.clear_user_state(user_id)

        if ok:
            
            self.bot.send_message(message.chat.id, "✅ Coordonate actualizate.")
        else:
            
            self.bot.send_message(message.chat.id, "❌ Nu s-au putut actualiza coordonatele.")

        return True    
    
    def update_seller_drop_caption(self, owner_user_id, product_id, index, new_caption):
        products_data = self.load_products()

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                drop_items = product.get('drop_items', [])
                if 0 <= index < len(drop_items):
                    drop_items[index]['caption'] = new_caption
                    return self.save_products(products_data)

        return False


    def replace_seller_drop_image(self, owner_user_id, product_id, index, new_file_id):
        products_data = self.load_products()

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                drop_items = product.get('drop_items', [])
                if 0 <= index < len(drop_items):
                    drop_items[index]['file_id'] = new_file_id
                    return self.save_products(products_data)

        return False


    def delete_seller_drop(self, owner_user_id, product_id, index):
        products_data = self.load_products()

        for product in products_data.get('products', []):
            if (
                product.get('id') == product_id and
                product.get('owner_user_id') == owner_user_id and
                product.get('is_seller_product') is True
            ):
                drop_items = product.get('drop_items', [])
                if 0 <= index < len(drop_items):
                    del drop_items[index]
                    product['stock'] = len(drop_items)
                    return self.save_products(products_data)

        return False
    
    def handle_seller_product_edit_input(self, message):
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)

        if not user_state:
            return False

        state_name = user_state.get('state')
        if state_name not in [
            'seller_editing_product_name',
            'seller_editing_product_desc',
            'seller_editing_product_price'
        ]:
            return False

        state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
        product_id = state_data.get('product_id')
        user_input = (message.text or '').strip()

        if state_name == 'seller_editing_product_name':
            if not user_input or len(user_input) > 100:
                
                self.bot.send_message(message.chat.id, "❌ Nume invalid.")
                return True

            ok = self.update_seller_product_field(user_id, product_id, 'name', user_input)

        elif state_name == 'seller_editing_product_desc':
            if len(user_input) > 1000:
                
                self.bot.send_message(message.chat.id, "❌ Descriere prea lungă.")
                return True

            ok = self.update_seller_product_field(user_id, product_id, 'description', user_input)

        elif state_name == 'seller_editing_product_price':
            try:
                price = int(user_input)
                if price < 1 or price > 999999:
                    raise ValueError
            except:
                
                self.bot.send_message(message.chat.id, "❌ Preț invalid.")
                return True

            ok = self.update_seller_product_field(user_id, product_id, 'price', price)

        self.db.clear_user_state(user_id)

        if ok:
            
            self.bot.send_message(message.chat.id, "✅ Produs actualizat.")
        else:
            
            self.bot.send_message(message.chat.id, "❌ Nu s-a putut actualiza produsul.")

        return True    
    
    def handle_edit_drops(self, call):
        """Show all drops for a product so admin can edit one"""
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return

        product_id = call.data.replace('prod_edit_drops_', '')
        products_data = self.load_products()
        product = next((p for p in products_data.get('products', []) if p.get('id') == product_id and p.get('status') == 'saved'), None)

        if not product:
            self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost gasit")
            return

        drop_items = product.get('drop_items', [])
        text = f"🛠 <b>Editeaza Drop</b>\n\n<b>Produs:</b> {product['name']}\n<b>Stock total:</b> {len(drop_items)}\n\nSelecteaza un drop pentru editare."

        markup = telebot.types.InlineKeyboardMarkup()
        if drop_items:
            for i, item in enumerate(drop_items):
                caption_preview = (item.get('caption') or '').strip().replace('\n', ' ')
                if len(caption_preview) > 25:
                    caption_preview = caption_preview[:25] + '...'
                label = f"#{i+1}"
                if caption_preview:
                    label += f" - {caption_preview}"
                markup.add(telebot.types.InlineKeyboardButton(
                    text=label,
                    callback_data=f'prod_edit_drop_item_{product_id}_{i}'
                ))
        else:
            text += "\n\nNu exista drop-uri in stock."

        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data=f'prod_view_{product_id}'
        ))

        try:
            
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing drops list: {e}")

        self.bot.answer_callback_query(call.id)

    def handle_edit_drop_item(self, call):
        """Open actions for a single drop item"""
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return

        parts = call.data.split('_')
        if len(parts) < 6:
            self.bot.answer_callback_query(call.id, "❌ Date invalide")
            return

        product_id = parts[4]
        try:
            index = int(parts[5])
        except ValueError:
            self.bot.answer_callback_query(call.id, "❌ Index invalid")
            return

        products_data = self.load_products()
        product = next((p for p in products_data.get('products', []) if p.get('id') == product_id and p.get('status') == 'saved'), None)

        if not product:
            self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost gasit")
            return

        drop_items = product.get('drop_items', [])
        if not (0 <= index < len(drop_items)):
            self.bot.answer_callback_query(call.id, "❌ Drop-ul nu a fost gasit")
            return

        drop = drop_items[index]
        caption = drop.get('caption', '') or 'Fara caption'

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            text="✏️ Editeaza coordonate",
            callback_data=f'prod_edit_drop_caption_{product_id}_{index}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text="🖼 Inlocuieste poza",
            callback_data=f'prod_replace_drop_{product_id}_{index}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text="🗑 Sterge drop",
            callback_data=f'prod_delete_drop_{product_id}_{index}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data=f'prod_edit_drops_{product_id}'
        ))

        try:
            self.bot.send_photo(
                chat_id=call.message.chat.id,
                photo=drop['file_id'],
                caption=f"🛠 <b>Drop #{index+1}</b>\n\n<b>Coordonate:</b>\n{caption}",
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error sending drop preview: {e}")
            
            
            self.bot.send_message(
                call.message.chat.id,
                f"🛠 <b>Drop #{index+1}</b>\n\n<b>Coordonate:</b>\n{caption}",
                reply_markup=markup,
                parse_mode='HTML'
            )

        self.bot.answer_callback_query(call.id)

    def handle_edit_drop_caption(self, call):
        """Start caption editing flow for one drop"""
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return

        parts = call.data.split('_')
        if len(parts) < 6:
            self.bot.answer_callback_query(call.id, "❌ Date invalide")
            return

        product_id = parts[4]
        index = parts[5]

        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'en'

        self.db.set_user_state(
            user_id=user_id,
            state='editing_drop_caption',
            data=json.dumps({
                'lang_code': lang_code,
                'product_id': product_id,
                'edit_type': 'drop_caption',
                'index': index
            })
        )

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data=f'prod_edit_drop_item_{product_id}_{index}'
        ))
        
        
        self.bot.send_message(
            call.message.chat.id,
            "✏️ Trimite noul caption pentru acest drop.",
            reply_markup=markup
        )
        self.bot.answer_callback_query(call.id)

    def handle_replace_drop(self, call):
        """Start image replacement flow for one drop"""
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return

        parts = call.data.split('_')
        if len(parts) < 5:
            self.bot.answer_callback_query(call.id, "❌ Date invalide")
            return

        product_id = parts[3]
        index = parts[4]

        self.db.set_user_state(
            user_id=user_id,
            state='replacing_drop_image',
            data=json.dumps({
                'product_id': product_id,
                'index': index
            })
        )

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data=f'prod_edit_drop_item_{product_id}_{index}'
        ))
        

        self.bot.send_message(
            call.message.chat.id,
            "📸 Trimite noua poza pentru acest drop. Caption-ul actual va ramane neschimbat.",
            reply_markup=markup
        )
        self.bot.answer_callback_query(call.id)

    def handle_delete_drop(self, call):
        """Delete one drop item from product stock"""
        user_id = call.from_user.id
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return

        parts = call.data.split('_')
        if len(parts) < 5:
            self.bot.answer_callback_query(call.id, "❌ Date invalide")
            return

        product_id = parts[3]
        try:
            index = int(parts[4])
        except ValueError:
            self.bot.answer_callback_query(call.id, "❌ Index invalid")
            return

        products_data = self.load_products()
        deleted = False

        for product in products_data.get('products', []):
            if product.get('id') == product_id and product.get('status') == 'saved':
                drop_items = product.get('drop_items', [])
                if 0 <= index < len(drop_items):
                    drop_items.pop(index)
                    product['stock'] = len(drop_items)
                    deleted = True
                break

        if not deleted:
            self.bot.answer_callback_query(call.id, "❌ Drop-ul nu a fost gasit", show_alert=True)
            return

        if self.save_products(products_data):
            self.bot.answer_callback_query(call.id, "✅ Drop sters")
            call.data = f'prod_edit_drops_{product_id}'
            self.handle_edit_drops(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Eroare la salvare", show_alert=True)
    
    def handle_premium_alert(self, call):
        """Show premium feature alert"""
        user = self.db.get_user(call.from_user.id)
        lang_code = user['language_code'] if user else 'en'
        
        alert_text = self.language.get_text('premium_feature_alert', lang_code)
        self.bot.answer_callback_query(call.id, alert_text, show_alert=True)
    
    def handle_add_new_product(self, call):
        """Handle adding a new product - delegate to creation handler"""
        # Delegate to creation handler
        self.creation_handler.start_product_creation(call)
    
    def handle_text_input(self, message):
        """Handle text input - delegate to appropriate handler"""
        # Check if it's a creation process
        if self.creation_handler.handle_text_input(message):
            return True
        
        # Check if it's a file upload process
        if self.file_handler.handle_text_input(message):
            return True
        
        # Check if it's a product editing process
        if self.handle_product_edit_input(message):
            return True
        
        return False
    
    def handle_file_input(self, message):
        """Handle file/photo input - delegate to file handler or internal drop editor"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)

        # =========================
        # SELLER PRODUCT IMAGE
        # =========================
        if user_state and user_state.get('state') == 'seller_uploading_product_image':
            try:
                state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                product_id = state_data['product_id']
            except Exception:
                self.db.clear_user_state(user_id)
                return False

            if not message.photo:
                
                self.bot.send_message(message.chat.id, "❌ Trimite o poză validă pentru produs.")
                return True

            photo_obj = message.photo[-1]
            file_id = photo_obj.file_id

            ok = self.update_seller_product_image(user_id, product_id, file_id, photo_obj)
            self.db.clear_user_state(user_id)

            if ok:
                
                self.bot.send_message(message.chat.id, "✅ Poza produsului a fost actualizată.")
            else:
                
                self.bot.send_message(message.chat.id, "❌ Nu s-a putut actualiza poza produsului.")

            return True


        # =========================
        # SELLER ADD DROP
        # =========================
        if user_state and user_state.get('state') == 'seller_adding_drop':
            try:
                state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                product_id = state_data['product_id']
            except Exception:
                self.db.clear_user_state(user_id)
                return False

            if not message.photo:
                
                self.bot.send_message(message.chat.id, "❌ Trimite o poză pentru drop.")
                return True

            file_id = message.photo[-1].file_id
            caption = message.caption or ""

            stock_type = state_data.get('stock_type', 'oras')
            ok = self.add_seller_drop(user_id, product_id, file_id, caption, stock_type)
            self.db.clear_user_state(user_id)

            if ok:
                
                self.bot.send_message(message.chat.id, "✅ Drop adăugat.")
            else:
                
                self.bot.send_message(message.chat.id, "❌ Nu s-a putut adăuga drop-ul.")

            return True

        # =========================
        # SELLER REPLACE DROP IMAGE
        # =========================
        if user_state and user_state.get('state') == 'seller_replacing_drop_image':
            try:
                state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                product_id = state_data['product_id']
                index = int(state_data['index'])
            except Exception:
                self.db.clear_user_state(user_id)
                return False

            if not message.photo:
                
                self.bot.send_message(message.chat.id, "❌ Trimite o poză nouă.")
                return True

            file_id = message.photo[-1].file_id

            ok = self.replace_seller_drop_image(user_id, product_id, index, file_id)
            self.db.clear_user_state(user_id)

            if ok:
                
                self.bot.send_message(message.chat.id, "✅ Poza drop-ului a fost actualizată.")
            else:
                
                self.bot.send_message(message.chat.id, "❌ Nu s-a putut actualiza poza.")

            return True
            
                # =========================
        # CASHOUT PHOTO
        # =========================
        if user_state and user_state.get('state') == 'cashout_waiting_photo':

            try:

                state_data = user_state['data'] if isinstance(
                    user_state['data'],
                    dict
                ) else json.loads(
                    user_state['data']
                )

                request_id = state_data['request_id']

            except Exception:

                self.db.clear_user_state(user_id)

                return False

            if not message.photo:

                self.bot.send_message(

                    message.chat.id,

                    "❌ Trimite o fotografie."

                )

                return True

            file_id = message.photo[-1].file_id

            conn = sqlite3.connect(
                self.db.db_path
            )

            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE cashout_requests
                SET
                    pickup_photo_file_id=?,
                    status='waiting_photo'
                WHERE id=?
                """,
                (
                    file_id,
                    request_id
                )
            )

            conn.commit()

            conn.close()

            self.db.clear_user_state(user_id)

            markup = telebot.types.InlineKeyboardMarkup()

            markup.add(

                telebot.types.InlineKeyboardButton(

                    "✅ Finalizează Retragerea",

                    callback_data=f"cashout_finish_{request_id}"

                )

            )

            self.bot.send_message(

                message.chat.id,

                "✅ Fotografia a fost salvată.",

                reply_markup=markup

            )

            return True    

        # =========================
        # ADMIN / EXISTING DROP IMAGE REPLACE
        # =========================
        if user_state and user_state.get('state') == 'replacing_drop_image':
            try:
                state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                product_id = state_data['product_id']
                index = int(state_data['index'])
            except Exception:
                self.db.clear_user_state(user_id)
                return False

            if not message.photo:
                
                self.bot.send_message(message.chat.id, "❌ Trimite o poza noua pentru drop.")
                return True

            file_id = message.photo[-1].file_id
            products_data = self.load_products()
            updated = False

            for product in products_data.get('products', []):
                if product.get('id') == product_id and product.get('status') == 'saved':
                    drop_items = product.get('drop_items', [])
                    if 0 <= index < len(drop_items):
                        drop_items[index]['file_id'] = file_id
                        drop_items[index]['file_unique_id'] = getattr(message.photo[-1], 'file_unique_id', None)
                        drop_items[index]['width'] = getattr(message.photo[-1], 'width', None)
                        drop_items[index]['height'] = getattr(message.photo[-1], 'height', None)
                        updated = True
                    break

            if not updated:
                
                self.bot.send_message(message.chat.id, "❌ Drop-ul nu a fost gasit.")
                self.db.clear_user_state(user_id)
                return True

            if self.save_products(products_data):
                self.db.clear_user_state(user_id)
                
                self.bot.send_message(message.chat.id, "✅ Imaginea drop-ului a fost actualizata.")

                from types import SimpleNamespace
                fake_call = SimpleNamespace()
                fake_call.data = f'prod_edit_drop_{product_id}_{index}'
                fake_call.from_user = message.from_user
                fake_call.message = message
                fake_call.id = None
                self.handle_edit_single_drop(fake_call)
            else:
                
                self.bot.send_message(message.chat.id, "❌ Eroare la salvare.")

            return True

        return self.file_handler.handle_file_input(message)    

    def handle_product_edit_input(self, message):
        """Handle text input during product editing"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)

        if not user_state:
            return False

        state_name = user_state['state']

        # Accept both classic product edit states and drop caption edit state
        if not (
            state_name.startswith('editing_product_') or
            state_name == 'editing_drop_caption'
        ):
            return False

        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False

        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data.get('lang_code', 'ro')
        except (json.JSONDecodeError, KeyError):
            return False

        user_input = (message.text or "").strip()

    # -----------------------------
    # DROP CAPTION EDIT
    # -----------------------------
        if state_name == 'editing_drop_caption':
            product_id = state_data.get('product_id')
            index = int(state_data.get('index', -1))

            if not user_input:
                
                self.bot.send_message(message.chat.id, "❌ Caption-ul nu poate fi gol.")
                return True

            products_data = self.load_products()
            product_index = None

            for i, product in enumerate(products_data.get('products', [])):
                if product['id'] == product_id and product.get('status') == 'saved':
                    product_index = i
                    break

            if product_index is None:
                
                self.bot.send_message(message.chat.id, "❌ Produsul nu a fost gasit.")
                self.db.clear_user_state(user_id)
                return True

            drop_items = products_data['products'][product_index].get('drop_items', [])

            if index < 0 or index >= len(drop_items):
                
                self.bot.send_message(message.chat.id, "❌ Drop-ul nu a fost gasit.")
                self.db.clear_user_state(user_id)
                return True

            products_data['products'][product_index]['drop_items'][index]['caption'] = user_input

            if self.save_products(products_data):
                self.db.clear_user_state(user_id)
                
                self.bot.send_message(message.chat.id, "✅ Coordonatele au fost actualizate.")

                from types import SimpleNamespace
                fake_call = SimpleNamespace()
                fake_call.data = f'prod_edit_drop_{product_id}_{index}'
                fake_call.from_user = message.from_user
                fake_call.message = message
                fake_call.id = None
                self.handle_edit_single_drop(fake_call)
            else:
                
                self.bot.send_message(message.chat.id, "❌ Eroare la salvare.")

            try:
                self.bot.delete_message(message.chat.id, message.message_id)
            except:
                pass

            return True

    # -----------------------------
    # EXISTING NORMAL PRODUCT EDIT FLOW
    # -----------------------------
        try:
            product_id = state_data['product_id']
            edit_type = state_data['edit_type']
        except KeyError:
            return False

        products_data = self.load_products()
        product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if product['id'] == product_id and product.get('status') == 'saved':
                product_index = i
                break

        if product_index is None:
            error_text = "❌ Product not found"
            
            self.bot.send_message(message.chat.id, error_text)
            self.db.clear_user_state(user_id)
            return True

        success = False

        if edit_type == 'name':
            if user_input and len(user_input) <= 100:
                products_data['products'][product_index]['name'] = user_input
                success = True
            else:
                error_text = self.language.get_text('invalid_product_name_error', lang_code)
                
                self.bot.send_message(message.chat.id, error_text)
                return True

        elif edit_type == 'description':
            if user_input and len(user_input) <= 1000:
                products_data['products'][product_index]['description'] = user_input
                success = True
            else:
                error_text = self.language.get_text('invalid_product_description_error', lang_code)
                
                self.bot.send_message(message.chat.id, error_text)
                return True

        elif edit_type == 'code':
            if self.validate_product_code(user_input) and not self.product_code_exists(user_input, exclude_id=product_id):
                old_code = products_data['products'][product_index]['code']
                new_code = user_input

                if self.rename_product_folders(old_code, new_code):
                    products_data['products'][product_index]['code'] = new_code
                    products_data['products'][product_index]['folder_paths'] = {
                        'image_folder': f"images/{new_code}",
                        'product_folder': f"products/{new_code}",
                        'temp_image_folder': f"images/temp/{new_code}_*",
                        'temp_product_folder': f"products/temp/{new_code}_*"
                    }
                    success = True
                else:
                    error_text = self.language.get_text('error_renaming_folders', lang_code)
                    
                    self.bot.send_message(message.chat.id, error_text)
                    return True
            else:
                error_text = self.language.get_text('invalid_product_code_error', lang_code)
                
                self.bot.send_message(message.chat.id, error_text)
                return True

        elif edit_type == 'price':
            try:
                price = int(user_input)
                if 1 <= price <= 999999:
                    products_data['products'][product_index]['price'] = price
                    success = True
                else:
                    raise ValueError()
            except ValueError:
                error_text = self.language.get_text('invalid_product_price_error', lang_code)
                
                self.bot.send_message(message.chat.id, error_text)
                return True

        elif edit_type == 'quantity':
            try:
                quantity = int(user_input)
                if quantity >= 0:
                    products_data['products'][product_index]['stock'] = quantity
                    success = True
                else:
                    raise ValueError()
            except ValueError:
                error_text = self.language.get_text('invalid_product_quantity_error', lang_code)
                
                self.bot.send_message(message.chat.id, error_text)
                return True

        if success:
            if self.save_products(products_data):
                self.db.clear_user_state(user_id)
                success_text = self.language.get_text('product_updated_success', lang_code)
                
                self.bot.send_message(message.chat.id, success_text)

                from types import SimpleNamespace
                fake_call = SimpleNamespace()
                fake_call.data = f'prod_view_{product_id}'
                fake_call.from_user = message.from_user
                fake_call.message = message
                fake_call.id = None
                self.handle_product_view(fake_call)
            else:
                error_text = self.language.get_text('error_saving_changes', lang_code)
                
                self.bot.send_message(message.chat.id, error_text)

        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

        return True
    
    def handle_edit_single_drop(self, call):
        """Show one specific drop item with edit options"""
        try:
            parts = call.data.split('_')
            product_id = parts[3]
            index = int(parts[4])

            products_data = self.load_products()
            product = None
            for p in products_data.get('products', []):
                if p.get('id') == product_id and p.get('status') == 'saved':
                    product = p
                    break

            if not product:
                if getattr(call, 'id', None):
                    self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost gasit")
                else:
                    
                    self.bot.send_message(call.message.chat.id, "❌ Produsul nu a fost gasit")
                return

            drop_items = product.get('drop_items', [])
            if index < 0 or index >= len(drop_items):
                if getattr(call, 'id', None):
                    self.bot.answer_callback_query(call.id, "❌ Drop-ul nu a fost gasit")
                else:
                    
                    self.bot.send_message(call.message.chat.id, "❌ Drop-ul nu a fost gasit")
                return

            drop = drop_items[index]
            caption = drop.get('caption', '')
            text = f"🛠 <b>Drop #{index + 1}</b>\n\n<b>Coordonate:</b>\n<code>{caption or '-'}</code>"

            markup = telebot.types.InlineKeyboardMarkup()
            markup.add(telebot.types.InlineKeyboardButton(
                text="✏️ Editeaza coordonate",
                callback_data=f'prod_edit_drop_caption_{product_id}_{index}'
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="🖼 Inlocuieste poza",
                callback_data=f'prod_replace_drop_{product_id}_{index}'
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="🗑 Sterge drop",
                callback_data=f'prod_delete_drop_{product_id}_{index}'
            ))
            markup.add(telebot.types.InlineKeyboardButton(
                text="🔙 Inapoi",
                callback_data=f'prod_edit_drops_{product_id}'
            ))

            if drop.get('file_id'):
                self.bot.send_photo(
                    chat_id=call.message.chat.id,
                    photo=drop['file_id'],
                    caption=text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            else:
                
                self.bot.send_message(
                    chat_id=call.message.chat.id,
                    text=text,
                    reply_markup=markup,
                    parse_mode='HTML'
                )

            if getattr(call, 'id', None):
                self.bot.answer_callback_query(call.id)

        except Exception as e:
            logger.error(f"Error in handle_edit_single_drop: {e}")
            if getattr(call, 'id', None):
                self.bot.answer_callback_query(call.id, "❌ Eroare")
    
    def validate_product_code(self, code):
        """Validate product code format"""
        if not code or len(code) > 50:
            return False
        import re
        return re.match(r'^[a-zA-Z0-9_-]+$', code) is not None
    
    def product_code_exists(self, code, exclude_id=None):
        """Check if product code already exists"""
        products_data = self.load_products()
        for product in products_data.get('products', []):
            if (product.get('code') == code and 
                product.get('status') == 'saved' and 
                product.get('id') != exclude_id):
                return True
        return False
    
    def save_products(self, data):
        """Save products to JSON file"""
        try:
            with open(self.products_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info("Products saved successfully")
            return True
        except Exception as e:
            logger.error(f"Error saving products: {e}")
            return False
    
    def rename_product_folders(self, old_code, new_code):
        """Rename product folders when code changes"""
        import shutil
        try:
            # Rename image folder
            old_image_path = os.path.join(self.images_dir, old_code)
            new_image_path = os.path.join(self.images_dir, new_code)
            if os.path.exists(old_image_path):
                shutil.move(old_image_path, new_image_path)
            
            # Rename product folder
            old_product_path = os.path.join(self.products_dir, old_code)
            new_product_path = os.path.join(self.products_dir, new_code)
            if os.path.exists(old_product_path):
                shutil.move(old_product_path, new_product_path)
            
            return True
        except Exception as e:
            logger.error(f"Error renaming folders: {e}")
            return False
    
    def handle_product_edit_buttons(self, call):
        """Handle product edit button clicks"""
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
        
        # Extract edit type and product ID
        # Format: prod_edit_name_12345678
        parts = call.data.split('_')
        if len(parts) < 4:
            return
        
        edit_type = parts[2]  # name, code, desc, price, quantity, reviews
        product_id = parts[3]
        
        # Special handling for reviews (uses buttons, not text input)
        if edit_type == 'reviews':
            self.handle_reviews_edit(call, product_id, lang_code)
            return
        
        # Set editing state
        self.db.set_user_state(
            user_id=user_id,
            state=f'editing_product_{edit_type}',
            data=json.dumps({
                'lang_code': lang_code,
                'product_id': product_id,
                'edit_type': edit_type
            })
        )
        
        # Send prompt message based on edit type (language-specific)
        prompts = {
            'name': self.language.get_text('enter_product_name_prompt', lang_code),
            'code': self.language.get_text('enter_product_code_prompt', lang_code),
            'desc': self.language.get_text('enter_product_description_prompt', lang_code),
            'price': self.language.get_text('enter_product_price_prompt', lang_code),
            'quantity': self.language.get_text('enter_product_quantity_prompt', lang_code)
        }
        
        prompt_text = prompts.get(edit_type, self.language.get_text('enter_new_value', lang_code))
        
        # Create back button
        markup = telebot.types.InlineKeyboardMarkup()
        back_text = self.language.get_text('back_button', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"🔙 {back_text}",
            callback_data=f'prod_view_{product_id}'
        ))
        
        
        self.bot.send_message(
            chat_id=call.message.chat.id,
            text=prompt_text,
            reply_markup=markup
        )
        
        self.bot.answer_callback_query(call.id)
    
    def handle_product_visibility_toggle(self, call):
        """Handle product visibility toggle"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract product ID
        product_id = call.data.replace('prod_toggle_visibility_', '')
        
        # Load products
        products_data = self.load_products()
        product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if product['id'] == product_id and product.get('status') == 'saved':
                product_index = i
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Toggle visibility
        current_hidden = products_data['products'][product_index].get('hidden', False)
        products_data['products'][product_index]['hidden'] = not current_hidden
        
        # Save changes
        if self.save_products(products_data):
            status = "hidden" if not current_hidden else "visible"
            self.bot.answer_callback_query(call.id, f"✅ Product is now {status}")
            
            # Refresh product view
            self.handle_product_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error updating product")
    
    def handle_product_delete(self, call):
        """Handle product deletion"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract product ID
        product_id = call.data.replace('prod_delete_', '')
        
        # Load products
        products_data = self.load_products()
        product_index = None
        product = None
        for i, prod in enumerate(products_data.get('products', [])):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product_index = i
                product = prod
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Show confirmation dialog
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("✅ Yes, Delete", callback_data=f'prod_confirm_delete_{product_id}'),
            telebot.types.InlineKeyboardButton("❌ Cancel", callback_data=f'prod_view_{product_id}')
        )
        
        confirmation_text = f"⚠️ <b>Delete Product?</b>\n\n"
        confirmation_text += f"<b>Name:</b> {product['name']}\n"
        confirmation_text += f"<b>Code:</b> {product['code']}\n\n"
        confirmation_text += "This action cannot be undone!"
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=confirmation_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        self.bot.answer_callback_query(call.id)
    
    def handle_product_confirm_delete(self, call):
        """Handle confirmed product deletion"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract product ID
        product_id = call.data.replace('prod_confirm_delete_', '')
        
        # Load products
        products_data = self.load_products()
        product_index = None
        product = None
        for i, prod in enumerate(products_data.get('products', [])):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product_index = i
                product = prod
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Product not found")
            return
        
        # Delete product folders
        product_code = product['code']
        import shutil
        try:
            # Delete image folder
            image_folder = os.path.join(self.images_dir, product_code)
            if os.path.exists(image_folder):
                shutil.rmtree(image_folder)
            
            # Delete product folder
            product_folder = os.path.join(self.products_dir, product_code)
            if os.path.exists(product_folder):
                shutil.rmtree(product_folder)
                
        except Exception as e:
            logger.error(f"Error deleting product folders: {e}")
        
        # Remove from JSON
        del products_data['products'][product_index]
        
        # Save changes
        if self.save_products(products_data):
            self.bot.answer_callback_query(call.id, "✅ Product deleted successfully!")
            
            # Return to subcategory view
            category_id = product['category_id']
            subcategory_id = product['subcategory_id']
            call.data = f'prod_subcat_{category_id}_{subcategory_id}'
            self.handle_product_subcategory_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error deleting product")
    
    def handle_set_reviews(self, call):
        """Handle setting review status for existing products"""
        user_id = call.from_user.id
        
        # Check if user is admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        # Extract setting and product ID from callback data
        # Format: prod_set_reviews_true_12345678 or prod_set_reviews_false_12345678
        parts = call.data.split('_')
        if len(parts) < 5:
            return
        
        reviews_enabled = parts[3] == 'true'
        product_id = parts[4]
        
        # Load products
        products_data = self.load_products()
        product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if product['id'] == product_id and product.get('status') == 'saved':
                product_index = i
                break
        
        if product_index is None:
            self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost gasit")
            return
        
        # Update review setting
        products_data['products'][product_index]['reviews_enabled'] = reviews_enabled
        
        # Save changes
        if self.save_products(products_data):
            status = "enabled" if reviews_enabled else "disabled"
            self.bot.answer_callback_query(call.id, f"✅ Recenzii {status}")
            
            # Refresh product view
            self.handle_product_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error")
    
    def handle_reviews_edit(self, call, product_id, lang_code):
        """Handle review settings edit"""
        # Load product
        products_data = self.load_products()
        product = None
        for prod in products_data.get('products', []):
            if prod['id'] == product_id and prod.get('status') == 'saved':
                product = prod
                break
        
        if not product:
            self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost gasit")
            return
        
        current_reviews = product.get('reviews_enabled', True)
        
        # Create review settings buttons
        markup = telebot.types.InlineKeyboardMarkup()
        
        enable_text = self.language.get_text('enable_reviews', lang_code)
        disable_text = self.language.get_text('disable_reviews', lang_code)
        
        # Show both options with current selection highlighted
        if current_reviews:
            enable_button = f"✅ {enable_text}"
            disable_button = disable_text
        else:
            enable_button = enable_text
            disable_button = f"✅ {disable_text}"
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=enable_button,
            callback_data=f'prod_set_reviews_true_{product_id}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=disable_button,
            callback_data=f'prod_set_reviews_false_{product_id}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Inapoi",
            callback_data=f'prod_view_{product_id}'
        ))
        
        review_settings_text = self.language.get_text('review_settings_title', lang_code)
        product_label = self.language.get_text('product_label', lang_code)
        current_setting_label = self.language.get_text('current_setting_label', lang_code)
        choose_setting_text = self.language.get_text('choose_review_setting', lang_code)
        
        enabled_text = self.language.get_text('enabled', lang_code)
        disabled_text = self.language.get_text('disabled', lang_code)
        
        review_text = f"⭐ <b>{review_settings_text}</b>\n\n"
        review_text += f"<b>{product_label}:</b> {product['name']}\n\n"
        review_text += f"<b>{current_setting_label}:</b> {enabled_text if current_reviews else disabled_text}\n\n"
        review_text += choose_setting_text
        
        try:
            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=review_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        self.bot.answer_callback_query(call.id)
    
    def handle_upload_more(self, call):
        """Handle upload more files for downloadable/line/drop products"""
        user_id = call.from_user.id

        # Check admin
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return

        # Get language
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error.")
            return

        lang_code = user['language_code']

        # Product ID
        product_id = call.data.replace('prod_upload_more_', '')

        products_data = self.load_products()

        product = None
        for p in products_data.get('products', []):
            if p['id'] == product_id:
                product = p
                break

        if not product:
            self.bot.answer_callback_query(call.id, "❌ Produsul nu a fost gasit")
            return

        product_type = product.get('type', 'delivered')

        if product_type == 'line_file':

            self.db.set_user_state(
                user_id=user_id,
                state='uploading_more_lines',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_id': product_id
                })
            )

            message_text = (
                f"📤 <b>Upload More Lines</b>\n\n"
                f"<b>Product:</b> {product['name']}\n"
                f"<b>Current Stock:</b> {product.get('stock', 0)} lines\n\n"
                f"Upload a .txt file with additional lines."
            )

            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=message_text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            self.bot.answer_callback_query(call.id, "📤 Upload your .txt file now")

        elif product_type == 'drop':

            self.db.set_user_state(
                user_id=user_id,
                state='uploading_more_drops',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_id': product_id
                })
            )

            message_text = (
                f"🖼️ <b>Adauga mai multe drop-uri</b>\n\n"
                f"<b>Produs:</b> {product['name']}\n"
                f"<b>Stock:</b> {product.get('stock', 0)} drops\n\n"
                f"Trimite poze pentru a adauga stock [NU UITA SA BAGI SI COORDONATELE DIRECT]."
            )

            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=message_text,
                reply_markup=markup,
                parse_mode='HTML'
            )

            self.bot.answer_callback_query(call.id, "🖼️ Incarca pozele drop-ului")

        else:

            self.bot.answer_callback_query(
                call.id,
                "Upload More not supported for this product type.",
                show_alert=True
            )