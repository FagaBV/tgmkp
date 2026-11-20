import telebot
import logging
import json
import os
import uuid
import re
import shutil
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class ProductCreationHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.products_file = 'products.json'
        self.products_dir = 'products'
        self.images_dir = 'images'
    
    def load_products(self):
        """Load products from JSON file"""
        try:
            if os.path.exists(self.products_file):
                with open(self.products_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"products": []}
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {"products": []}
    
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
    
    def start_product_creation(self, call):
        """Start the product creation process - Step 1: Product Name"""
        user_id = call.from_user.id
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            self.bot.answer_callback_query(call.id, "❌ Access denied! Admin only.")
            return
        
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")
            return
        
        lang_code = user['language_code']
        self.cleanup_pending_products()
        
        parts = call.data.replace('prod_add_', '').split('_')
        category_id = parts[0]
        subcategory_id = parts[1]
        
        step_text = self.language.get_text('product_name_step', lang_code)
        
        markup = telebot.types.InlineKeyboardMarkup()
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        product_data = {
            'step': 1,
            'category_id': category_id,
            'subcategory_id': subcategory_id,
            'name': None,
            'description': None,
            'code': None,
            'price': None,
            'images': [],
            'type': None,
            'files': [],
            'stock': None,
            'drop_items': [],
            'drop_caption': None
        }
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_1',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            }),
            message_id=call.message.message_id
        )
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=step_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_text_input(self, message):
        """Handle text input during product creation process"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or not user_state['state'].startswith('creating_product_step_'):
            return False
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_data = state_data['product_data']
            state_name = user_state['state']
            
            state_parts = state_name.split('_')
            if len(state_parts) >= 3 and state_parts[-1].isdigit():
                current_step = int(state_parts[-1])
            else:
                for part in reversed(state_parts):
                    if part.isdigit():
                        current_step = int(part)
                        break
                else:
                    current_step = None
                    
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Error parsing state data: {e}")
            self.cancel_product_creation(message, user_id)
            return True
        
        user_input = (message.text or "").strip()
        
        if state_name == 'creating_product_step_7_drop':
            if not product_data.get('drop_items'):
                self.bot.send_message(message.chat.id, "❌ Upload at least one photo first.")
                return True

            # optional: allow admin to type 'done'
            if user_input.lower() in ['done', 'gata', 'continue', 'continua']:
                product_data['stock'] = len(product_data.get('drop_items', []))
                self.proceed_to_review_settings(message, user_id, lang_code, product_data)
            else:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Pentru drop-uri si stock in sine, cand incarci o poza, asigura-te ca bagi in caption direct coordonatele! cand ai terminat de adaugat scrie: gata"
                )

            try:
                self.bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass
            return True
        
        if current_step == 1:
            if not user_input or len(user_input) > 100:
                self.bot.send_message(message.chat.id, "❌ Invalid product name. Please enter a name (1-100 characters).")
                return True
            
            product_data['name'] = user_input
            self.proceed_to_step_2(message, user_id, lang_code, product_data)
            
        elif current_step == 2:
            if not user_input or len(user_input) > 1000:
                self.bot.send_message(message.chat.id, "❌ Invalid description. Please enter a description (1-1000 characters).")
                return True
            
            product_data['description'] = user_input
            self.proceed_to_step_3(message, user_id, lang_code, product_data)
            
        elif current_step == 3:
            if not self.validate_product_code(user_input):
                self.bot.send_message(message.chat.id, "❌ Invalid product code. Use only letters, numbers, dashes, and underscores (1-50 characters).")
                return True
            
            if self.product_code_exists(user_input):
                code_taken_text = self.language.get_text('product_code_taken', lang_code)
                formatted_text = code_taken_text.format(code=user_input)
                self.bot.send_message(message.chat.id, formatted_text, parse_mode='HTML')
                return True
            
            product_data['code'] = user_input
            self.proceed_to_step_4(message, user_id, lang_code, product_data)
            
        elif current_step == 4:
            try:
                price = int(user_input)
                if price < 1 or price > 999999:
                    raise ValueError("Price out of range")
                product_data['price'] = price
                self.create_in_progress_product(product_data)
                self.proceed_to_step_5(message, user_id, lang_code, product_data)
            except ValueError:
                self.bot.send_message(message.chat.id, "❌ Invalid price. Please enter a whole number between 1 and 999999.")
                return True
        
        elif current_step == 7 and state_name == 'creating_product_step_7':
            try:
                stock = int(user_input)
                if stock < 0 or stock > 999999:
                    raise ValueError("Stock out of range")
                product_data['stock'] = stock
                self.proceed_to_review_settings(message, user_id, lang_code, product_data)
            except ValueError:
                self.bot.send_message(message.chat.id, "❌ Invalid stock amount. Please enter a number between 0 and 999999.")
                return True
        else:
            return False
        
        try:
            self.bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        
        return True
    
    def validate_product_code(self, code):
        """Validate product code format"""
        if not code or len(code) > 50:
            return False
        return re.match(r'^[a-zA-Z0-9_-]+$', code) is not None
    
    def product_code_exists(self, code):
        """Check if product code already exists"""
        products_data = self.load_products()
        for product in products_data.get('products', []):
            if product.get('code') == code and product.get('status') == 'saved':
                return True
        return False
    
    def cleanup_pending_products(self):
        """Clean up any pending products and their folders"""
        products_data = self.load_products()
        pending_products = [p for p in products_data.get('products', []) if p.get('status') == 'in-progress']
        
        if not pending_products:
            return
        
        logger.info(f"Found {len(pending_products)} pending products, cleaning up...")
        
        for product in pending_products:
            product_code = product.get('code')
            if product_code:
                for root_dir in [self.products_dir, self.images_dir]:
                    temp_dir = os.path.join(root_dir, 'temp')
                    if os.path.exists(temp_dir):
                        for folder_name in os.listdir(temp_dir):
                            if folder_name.startswith(f"{product_code}_"):
                                folder_path = os.path.join(temp_dir, folder_name)
                                if os.path.isdir(folder_path):
                                    shutil.rmtree(folder_path)
                                    logger.info(f"Removed temp folder: {folder_path}")
                
                for folder_path in [
                    os.path.join(self.images_dir, product_code),
                    os.path.join(self.products_dir, product_code)
                ]:
                    if os.path.exists(folder_path):
                        shutil.rmtree(folder_path)
                        logger.info(f"Removed folder: {folder_path}")
        
        products_data['products'] = [p for p in products_data.get('products', []) if p.get('status') != 'in-progress']
        self.save_products(products_data)
        logger.info("Cleaned up pending products from JSON")
    
    def create_in_progress_product(self, product_data):
        """Create an in-progress product entry in JSON"""
        product_id = str(uuid.uuid4())[:8]
        
        in_progress_product = {
            'id': product_id,
            'name': product_data['name'],
            'description': product_data['description'],
            'code': product_data['code'],
            'price': product_data['price'],
            'category_id': product_data['category_id'],
            'subcategory_id': product_data['subcategory_id'],
            'type': product_data['type'],
            'images': [],
            'files': [],
            'stock': 0,
            'drop_items': [],
            'drop_caption': None,
            'reviews_enabled': True,
            'status': 'in-progress',
            'hidden': False,
            'created_at': str(uuid.uuid4())[:8],
            'folder_paths': {
                'image_folder': f"images/{product_data['code']}",
                'product_folder': f"products/{product_data['code']}",
                'temp_image_folder': f"images/temp/{product_data['code']}_*",
                'temp_product_folder': f"products/temp/{product_data['code']}_*"
            }
        }
        
        products_data = self.load_products()
        products_data['products'].append(in_progress_product)
        self.save_products(products_data)
        logger.info(f"Created in-progress product: {product_data['code']}")
        return product_id
    
    def proceed_to_step_2(self, message, user_id, lang_code, product_data):
        step_text = self.language.get_text('product_description_step', lang_code)
        formatted_text = step_text.format(product_name=product_data['name'])
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_2',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def proceed_to_step_3(self, message, user_id, lang_code, product_data):
        step_text = self.language.get_text('product_code_step', lang_code)
        formatted_text = step_text.format(product_name=product_data['name'])
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_3',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def proceed_to_step_4(self, message, user_id, lang_code, product_data):
        step_text = self.language.get_text('product_price_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            product_code=product_data['code']
        )
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_4',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def proceed_to_step_5(self, message, user_id, lang_code, product_data):
        step_text = self.language.get_text('product_images_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            product_code=product_data['code'],
            price=product_data['price'],
            upload_count=len(product_data['images']),
            total_size=self.format_file_size(0)
        )
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_5',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        if len(product_data['images']) == 0:
            proceed_text = self.language.get_text('proceed_with_images', lang_code)
            formatted_proceed = proceed_text.format(count=0)
            markup.add(telebot.types.InlineKeyboardButton(
                text=formatted_proceed,
                callback_data='prod_proceed_step_6'
            ))
        
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def proceed_to_step_6(self, call):
        """Proceed to step 6: Product Type Selection"""
        user_id = call.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state:
            return
        
        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_data = state_data['product_data']
        except (json.JSONDecodeError, KeyError):
            return
        
        step_text = self.language.get_text('product_type_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            image_count=len(product_data['images'])
        )
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_6',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        line_file_text = self.language.get_text('line_in_file_product', lang_code)
        delivered_text = self.language.get_text('delivered_product', lang_code)
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=line_file_text,
            callback_data='prod_type_line_file'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=delivered_text,
            callback_data='prod_type_delivered'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text='🖼️ Drop',
            callback_data='prod_type_drop'
        ))
        
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def handle_product_type_selection(self, call):
        """Handle product type selection"""
        user_id = call.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state:
            return
        
        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_data = state_data['product_data']
        except (json.JSONDecodeError, KeyError):
            return
        
        if call.data == 'prod_type_downloadable':
            product_data['type'] = 'downloadable'
            self.proceed_to_downloadable_step(call, user_id, lang_code, product_data)
        elif call.data == 'prod_type_line_file':
            product_data['type'] = 'line_file'
            self.proceed_to_line_file_step(call, user_id, lang_code, product_data)
        elif call.data == 'prod_type_delivered':
            product_data['type'] = 'delivered'
            self.proceed_to_delivered_step(call, user_id, lang_code, product_data)
        elif call.data == 'prod_type_drop':
            product_data['type'] = 'drop'
            self.proceed_to_drop_step(call, user_id, lang_code, product_data)
    
    def proceed_to_downloadable_step(self, call, user_id, lang_code, product_data):
        step_text = self.language.get_text('downloadable_files_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            upload_count=len(product_data['files']),
            total_size=self.format_file_size(0)
        )
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_7_downloadable',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        if len(product_data['files']) > 0:
            complete_text = self.language.get_text('upload_complete', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=complete_text,
                callback_data='prod_files_complete'
            ))
        
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
    
    def proceed_to_line_file_step(self, call, user_id, lang_code, product_data):
        step_text = self.language.get_text('line_file_step', lang_code)
        formatted_text = step_text.format(product_name=product_data['name'])
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_7_line_file',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
    
    def proceed_to_delivered_step(self, call, user_id, lang_code, product_data):
        step_text = self.language.get_text('delivered_stock_step', lang_code)
        formatted_text = step_text.format(product_name=product_data['name'])
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_7',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=formatted_text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
    
    def proceed_to_drop_step(self, call, user_id, lang_code, product_data):
        drop_items = product_data.get('drop_items', [])
        all_have_captions = len(drop_items) > 0 and all(
            (item.get('caption') or '').strip() for item in drop_items
        )

        text = (
            f"🖼️ <b>Creaza Drop</b>\n\n"
            f"Step 7/7: Incarca Drop\n\n"
            f"Produs: <b>{product_data['name']}</b>\n"
            f"Drop-uri incarcate: <b>{len(drop_items)}</b>\n"
            f"Coordonate: <b>{'set' if all_have_captions else 'missing'}</b>\n\n"
            f"Trimite una sau mai multe poze\n"
            f"Fiecare poza incarcata = 1 drop in stock.\n"
            f"Fiecare poza trebuie sa aiba coordonatele sale atasate."
        )

        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_7_drop',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )

        markup = telebot.types.InlineKeyboardMarkup()
        if len(drop_items) > 0 and all_have_captions:
            markup.add(telebot.types.InlineKeyboardButton(
                text='✅ Continue',
                callback_data='prod_drop_complete'
            ))

        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))

        try:
            self.bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"Error editing drop message: {e}")
            
    def proceed_to_review_settings(self, message, user_id, lang_code, product_data):
        try:
            step_text = self.language.get_text('product_review_settings_step', lang_code)
            formatted_text = step_text.format(product_name=product_data['name'])
            
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_review_settings',
                data=json.dumps({
                    'lang_code': lang_code,
                    'product_data': product_data
                })
            )
        except Exception as e:
            logger.error(f"Error in proceed_to_review_settings: {e}")
            raise
        
        markup = telebot.types.InlineKeyboardMarkup()
        enable_text = self.language.get_text('enable_reviews', lang_code)
        disable_text = self.language.get_text('disable_reviews', lang_code)
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"✅ {enable_text}",
            callback_data='prod_reviews_enable'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=f"❌ {disable_text}",
            callback_data='prod_reviews_disable'
        ))
        
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def handle_reviews_setting(self, call, reviews_enabled):
        user_id = call.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state:
            return
        
        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_data = state_data['product_data']
        except (json.JSONDecodeError, KeyError):
            return
        
        product_data['reviews_enabled'] = reviews_enabled
        self.proceed_to_summary(call.message, user_id, lang_code, product_data)
        
        if hasattr(call, 'id') and call.id is not None:
            self.bot.answer_callback_query(call.id)
    
    def proceed_to_summary(self, message, user_id, lang_code, product_data):
        from handlers.category_handler import CategoryHandler
        category_handler = CategoryHandler(self.bot, self.db, self.language, self.config)
        categories_data = category_handler.load_categories()
        
        category_name = "Unknown"
        subcategory_name = "Unknown"
        
        for cat in categories_data.get('categories', []):
            if cat['id'] == product_data['category_id']:
                category_name = cat['name']
                for subcat in cat.get('subcategories', []):
                    if subcat['id'] == product_data['subcategory_id']:
                        subcategory_name = subcat['name']
                        break
                break
        
        type_display = {
            'downloadable': 'Downloadable Product',
            'line_file': 'Line-based File Product',
            'delivered': 'Delivered Product',
            'drop': 'Drop Product'
        }.get(product_data['type'], product_data['type'])
        
        if product_data['type'] == 'downloadable':
            stock_info = f"{len(product_data.get('files', []))} files"
        elif product_data['type'] == 'line_file':
            stock_info = f"{product_data.get('stock', 0)} lines"
        elif product_data['type'] == 'drop':
            stock_info = f"{len(product_data.get('drop_items', []))} drops"
        else:
            stock_info = f"{product_data.get('stock', 0)} items"
        
        reviews_status = self.language.get_text('enabled', lang_code) if product_data.get('reviews_enabled', True) else self.language.get_text('disabled', lang_code)
        
        step_text = self.language.get_text('product_summary_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            product_code=product_data['code'],
            price=product_data['price'],
            category_name=category_name,
            subcategory_name=subcategory_name,
            image_count=len(product_data['images']),
            product_type=type_display,
            stock_info=stock_info,
            reviews_status=reviews_status
        )
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_summary',
            data=json.dumps({
                'lang_code': lang_code,
                'product_data': product_data
            })
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        save_text = self.language.get_text('save_product', lang_code)
        cancel_text = self.language.get_text('cancel_product_upload', lang_code)
        
        markup.add(telebot.types.InlineKeyboardButton(
            text=save_text,
            callback_data='prod_save_final'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text=cancel_text,
            callback_data='prod_cancel_upload'
        ))
        
        
        self.bot.send_message(
            chat_id=message.chat.id,
            text=formatted_text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    
    def save_final_product(self, call):
        user_id = call.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state:
            return
        
        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            product_data = state_data['product_data']
        except (json.JSONDecodeError, KeyError):
            return
        
        product_id = str(uuid.uuid4())[:8]
        
        product_folder = os.path.join(self.products_dir, product_data['code'])
        image_folder = os.path.join(self.images_dir, product_data['code'])
        
        needs_product_folder = any(
            'local_path' in file and file.get('storage_type') != 'telegram_file_id' 
            for file in product_data.get('files', [])
        )
        needs_image_folder = any(
            'local_path' in img and img.get('storage_type') != 'telegram_file_id' 
            for img in product_data.get('images', [])
        )
        
        if needs_product_folder:
            os.makedirs(product_folder, exist_ok=True)
        if needs_image_folder:
            os.makedirs(image_folder, exist_ok=True)
        
        final_images = []
        for img in product_data['images']:
            if img.get('storage_type') == 'telegram_file_id':
                final_images.append(img.copy())
            elif 'local_path' in img and os.path.exists(img['local_path']):
                final_image_path = os.path.join(image_folder, img['file_name'])
                shutil.move(img['local_path'], final_image_path)
                final_relative_path = os.path.join('images', product_data['code'], img['file_name'])
                final_img = img.copy()
                final_img['local_path'] = final_image_path
                final_img['relative_path'] = final_relative_path
                final_images.append(final_img)
        
        final_files = []
        for file in product_data['files']:
            if file.get('storage_type') == 'telegram_file_id':
                final_files.append(file.copy())
            elif 'local_path' in file and os.path.exists(file['local_path']):
                final_file_path = os.path.join(product_folder, file['file_name'])
                shutil.move(file['local_path'], final_file_path)
                final_relative_path = os.path.join('products', product_data['code'], file['file_name'])
                final_file = file.copy()
                final_file['local_path'] = final_file_path
                final_file['relative_path'] = final_relative_path
                final_files.append(final_file)
        
        if product_data['type'] == 'downloadable':
            stock = len(final_files)
        elif product_data['type'] == 'line_file':
            stock = product_data.get('stock', 0)
        elif product_data['type'] == 'drop':
            stock = len(product_data.get('drop_items', []))
        else:
            stock = product_data.get('stock', 0)
        
        final_product = {
            'id': product_id,
            'name': product_data['name'],
            'description': product_data['description'],
            'code': product_data['code'],
            'price': product_data['price'],
            'category_id': product_data['category_id'],
            'subcategory_id': product_data['subcategory_id'],
            'type': product_data['type'],
            'images': final_images,
            'files': final_files,
            'stock': stock,
            'drop_items': product_data.get('drop_items', []),
            'drop_caption': product_data.get('drop_caption'),
            'reviews_enabled': product_data.get('reviews_enabled', True),
            'status': 'saved',
            'hidden': False,
            'created_at': str(uuid.uuid4())[:8],
            'folder_paths': {
                'image_folder': f"images/{product_data['code']}" if needs_image_folder else None,
                'product_folder': f"products/{product_data['code']}" if needs_product_folder else None,
                'temp_image_folder': f"images/temp/{product_data['code']}_*",
                'temp_product_folder': f"products/temp/{product_data['code']}_*"
            },
            'storage_info': {
                'images_use_file_ids': not needs_image_folder,
                'files_use_file_ids': not needs_product_folder,
                'total_images': len(final_images),
                'total_files': len(final_files),
                'total_drops': len(product_data.get('drop_items', []))
            }
        }
        
        products_data = self.load_products()
        existing_product_index = None
        for i, product in enumerate(products_data.get('products', [])):
            if (product.get('code') == product_data['code'] and product.get('status') == 'in-progress'):
                existing_product_index = i
                break
        
        if existing_product_index is not None:
            products_data['products'][existing_product_index] = final_product
        else:
            products_data['products'].append(final_product)
        
        if self.save_products(products_data):
            product_code = product_data.get('code')
            if product_code:
                for root_dir in [self.products_dir, self.images_dir]:
                    temp_dir = os.path.join(root_dir, 'temp')
                    if os.path.exists(temp_dir):
                        for folder_name in os.listdir(temp_dir):
                            if folder_name.startswith(product_code):
                                folder_path = os.path.join(temp_dir, folder_name)
                                if os.path.isdir(folder_path):
                                    shutil.rmtree(folder_path)
            
            self.db.clear_user_state(user_id)
            success_text = self.language.get_text('product_saved_success', lang_code)
            self.bot.answer_callback_query(call.id, success_text, show_alert=True)
            
            new_call_data = f'prod_subcat_{product_data["category_id"]}_{product_data["subcategory_id"]}'
            call.data = new_call_data
            
            from handlers.product_handler import ProductHandler
            product_handler = ProductHandler(self.bot, self.db, self.language, self.config)
            product_handler.handle_product_subcategory_view(call)
        else:
            self.bot.answer_callback_query(call.id, "❌ Error saving product. Please try again.", show_alert=True)
    
    def cancel_product_creation(self, message_or_call, user_id=None):
        if user_id is None:
            user_id = message_or_call.from_user.id
        
        user_state = self.db.get_user_state(user_id)
        if user_state:
            try:
                state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
                lang_code = state_data['lang_code']
                product_data = state_data.get('product_data', {})
                
                product_code = product_data.get('code')
                if product_code:
                    for root_dir in [self.products_dir, self.images_dir]:
                        temp_dir = os.path.join(root_dir, 'temp')
                        if os.path.exists(temp_dir):
                            for folder_name in os.listdir(temp_dir):
                                if folder_name.startswith(product_code):
                                    folder_path = os.path.join(temp_dir, folder_name)
                                    if os.path.isdir(folder_path):
                                        shutil.rmtree(folder_path)
                
                self.db.clear_user_state(user_id)
                cancel_text = self.language.get_text('product_upload_cancelled', lang_code)
                
                if hasattr(message_or_call, 'message'):
                    self.bot.answer_callback_query(message_or_call.id, cancel_text, show_alert=True)
                    self.bot.edit_message_text(
                        chat_id=message_or_call.message.chat.id,
                        message_id=message_or_call.message.message_id,
                        text="Returning to admin panel...",
                        reply_markup=telebot.types.InlineKeyboardMarkup().add(
                            telebot.types.InlineKeyboardButton(
                                text="🔙 Admin Panel",
                                callback_data='admin_panel'
                            )
                        )
                    )
                else:
                    self.bot.send_message(message_or_call.chat.id, cancel_text)
                
            except (json.JSONDecodeError, KeyError):
                self.db.clear_user_state(user_id)
    
    def format_file_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        elif size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
