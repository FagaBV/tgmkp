import telebot
import logging
import json
import os
import time
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class ProductFileHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.products_dir = 'products'
        self.images_dir = 'images'
        
        self.IMAGE_SIZE_LIMIT = 10 * 1024 * 1024
        self.PRODUCT_SIZE_LIMIT = 50 * 1024 * 1024
        self.MAX_IMAGES = 5
        
        self.IMAGE_TYPES = ['jpg', 'jpeg', 'png', 'gif', 'mp4']
        self.PRODUCT_FILE_TYPES = ['txt', 'png', 'jpg', 'jpeg', 'zip', 'rar', 'pdf']
    
    def handle_file_input(self, message):
        """Handle file/photo/video uploads during product creation"""
        user_id = message.from_user.id
        user_state = self.db.get_user_state(user_id)
        
        if not user_state or not (
            user_state['state'] == 'creating_product_step_5' or
            user_state['state'] == 'creating_product_step_7_downloadable' or
            user_state['state'] == 'creating_product_step_7_line_file' or
            user_state['state'] == 'creating_product_step_7_drop' or
            user_state['state'] == 'uploading_more_lines' or
            user_state['state'] == 'uploading_more_drops'
        ):
            return False
        
        if not self.db.is_admin(user_id, self.config['admin_ids']):
            return False
        
        try:
            state_data = user_state['data'] if isinstance(user_state['data'], dict) else json.loads(user_state['data'])
            lang_code = state_data['lang_code']
            
            if user_state['state'] == 'uploading_more_lines':
                return self.handle_upload_more_lines(message, user_id, lang_code, state_data)
            if user_state['state'] == 'uploading_more_drops':
                return self.handle_upload_more_drops(message, user_id, lang_code, state_data)
            
            product_data = state_data['product_data']
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error parsing state data: {e}")
            return False
        
        if user_state['state'] == 'creating_product_step_5':
            return self.handle_image_upload(message, user_id, lang_code, product_data)
        elif user_state['state'] == 'creating_product_step_7_downloadable':
            return self.handle_product_file_upload(message, user_id, lang_code, product_data)
        elif user_state['state'] == 'creating_product_step_7_line_file':
            return self.handle_line_file_upload(message, user_id, lang_code, product_data)
        elif user_state['state'] == 'creating_product_step_7_drop':
            return self.handle_drop_upload(message, user_id, lang_code, product_data)
        
        return False
    
    def handle_image_upload(self, message, user_id, lang_code, product_data):
        if len(product_data['images']) >= self.MAX_IMAGES:
            quota_text = self.language.get_text('quota_exceeded', lang_code)
            formatted_text = quota_text.format(max_count=self.MAX_IMAGES, max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        file_info = None
        file_name = None
        file_type = None
        
        if message.photo:
            file_info = message.photo[-1]
            file_name = f"image_{len(product_data['images'])}.jpg"
            file_type = 'image'
        elif message.video:
            file_info = message.video
            file_name = f"video_{len(product_data['images'])}.mp4"
            file_type = 'video'
        elif message.document:
            file_info = message.document
            original_name = message.document.file_name or f"file_{len(product_data['images'])}"
            file_name = original_name
            file_ext = original_name.split('.')[-1].lower() if '.' in original_name else ''
            if file_ext in self.IMAGE_TYPES:
                file_type = 'video' if file_ext == 'mp4' else 'image'
            else:
                invalid_text = self.language.get_text('invalid_file_type', lang_code)
                formatted_text = invalid_text.format(supported_types="JPG, PNG, GIF, MP4")
                self.bot.send_message(message.chat.id, formatted_text)
                return True
        
        if not file_info:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="JPG, PNG, GIF, MP4")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        if file_info.file_size > self.IMAGE_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        total_size = sum(img.get('size', 0) for img in product_data['images']) + file_info.file_size
        if total_size > self.IMAGE_SIZE_LIMIT:
            quota_text = self.language.get_text('quota_exceeded', lang_code)
            formatted_text = quota_text.format(max_count=self.MAX_IMAGES, max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        try:
            image_data = {
                'file_id': file_info.file_id,
                'file_unique_id': file_info.file_unique_id,
                'file_name': file_name,
                'size': file_info.file_size,
                'type': file_type,
                'storage_type': 'telegram_file_id',
                'uploaded_at': int(time.time())
            }
            
            if file_type == 'image' and message.photo:
                image_data.update({'width': file_info.width, 'height': file_info.height})
            elif file_type == 'video' and message.video:
                image_data.update({'width': file_info.width, 'height': file_info.height, 'duration': file_info.duration})
            
            product_data['images'].append(image_data)
            
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_step_5',
                data=json.dumps({'lang_code': lang_code, 'product_data': product_data})
            )
            
            self.send_image_upload_status(message, lang_code, product_data)
            
        except Exception as e:
            logger.error(f"Error handling image upload: {e}")
            
            self.bot.send_message(message.chat.id, "❌ Error uploading file. Please try again.")
        
        return True
    
    def send_image_upload_status(self, message, lang_code, product_data):
        total_size = sum(img.get('size', 0) for img in product_data['images'])
        
        step_text = self.language.get_text('product_images_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            product_code=product_data['code'],
            price=product_data['price'],
            upload_count=len(product_data['images']),
            total_size=self.format_file_size(total_size)
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        proceed_text = self.language.get_text('proceed_with_images', lang_code)
        formatted_proceed = proceed_text.format(count=len(product_data['images']))
        markup.add(telebot.types.InlineKeyboardButton(
            text=formatted_proceed,
            callback_data='prod_proceed_step_6'
        ))
        
        if len(product_data['images']) < self.MAX_IMAGES:
            more_text = self.language.get_text('upload_more_images', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=more_text,
                callback_data='prod_upload_more_images'
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
    
    def handle_product_file_upload(self, message, user_id, lang_code, product_data):
        file_info = None
        file_name = None
        
        if message.photo:
            file_info = message.photo[-1]
            file_name = f"image_{len(product_data['files'])}.jpg"
        elif message.video:
            file_info = message.video
            file_name = f"video_{len(product_data['files'])}.mp4"
        elif message.document:
            file_info = message.document
            file_name = file_info.file_name or f"file_{len(product_data['files'])}"
        
        if not file_info:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT, PNG, JPG, JPEG, ZIP, RAR, PDF")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        
        if file_ext not in self.PRODUCT_FILE_TYPES:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT, PNG, JPG, JPEG, ZIP, RAR, PDF")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        if file_info.file_size > self.PRODUCT_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=50)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        total_size = sum(f.get('size', 0) for f in product_data['files']) + file_info.file_size
        if total_size > self.PRODUCT_SIZE_LIMIT:
            quota_text = self.language.get_text('quota_exceeded', lang_code)
            formatted_text = quota_text.format(max_count="unlimited", max_size=50)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        try:
            file_data = {
                'file_id': file_info.file_id,
                'file_unique_id': file_info.file_unique_id,
                'file_name': file_name,
                'size': file_info.file_size,
                'type': file_ext,
                'storage_type': 'telegram_file_id',
                'uploaded_at': int(time.time())
            }
            
            if hasattr(file_info, 'mime_type'):
                file_data['mime_type'] = file_info.mime_type
            
            if message.document and hasattr(file_info, 'file_name'):
                file_data['original_name'] = file_info.file_name
                if hasattr(file_info, 'thumb') and file_info.thumb:
                    file_data['has_thumbnail'] = True
                    file_data['thumb_file_id'] = file_info.thumb.file_id
            
            if message.video:
                if hasattr(file_info, 'duration'):
                    file_data['duration'] = file_info.duration
                if hasattr(file_info, 'width') and hasattr(file_info, 'height'):
                    file_data.update({'width': file_info.width, 'height': file_info.height})
                if hasattr(file_info, 'thumb') and file_info.thumb:
                    file_data['thumb_file_id'] = file_info.thumb.file_id
            
            product_data['files'].append(file_data)
            
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_step_7_downloadable',
                data=json.dumps({'lang_code': lang_code, 'product_data': product_data})
            )
            
            self.send_product_file_status(message, lang_code, product_data)
            
        except Exception as e:
            logger.error(f"Error handling product file upload: {e}")
            self.bot.send_message(message.chat.id, "❌ Error uploading file. Please try again.")
        
        return True
    
    def send_product_file_status(self, message, lang_code, product_data):
        total_size = sum(f.get('size', 0) for f in product_data['files'])
        
        step_text = self.language.get_text('downloadable_files_step', lang_code)
        formatted_text = step_text.format(
            product_name=product_data['name'],
            upload_count=len(product_data['files']),
            total_size=self.format_file_size(total_size)
        )
        
        markup = telebot.types.InlineKeyboardMarkup()
        
        if len(product_data['files']) > 0:
            complete_text = self.language.get_text('upload_complete', lang_code)
            markup.add(telebot.types.InlineKeyboardButton(
                text=complete_text,
                callback_data='prod_files_complete'
            ))
        
        continue_text = self.language.get_text('continue_uploading', lang_code)
        markup.add(telebot.types.InlineKeyboardButton(
            text=continue_text,
            callback_data='prod_continue_uploading'
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
    
    def handle_line_file_upload(self, message, user_id, lang_code, product_data):
        if not message.document:
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        file_info = message.document
        file_name = file_info.file_name or "file.txt"
        
        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        if file_ext != 'txt':
            invalid_text = self.language.get_text('invalid_file_type', lang_code)
            formatted_text = invalid_text.format(supported_types="TXT")
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        if file_info.file_size > self.PRODUCT_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=50)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        try:
            file_path = self.bot.get_file(file_info.file_id)
            downloaded_file = self.bot.download_file(file_path.file_path)
            
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    content = downloaded_file.decode(encoding)
                    break
                except Exception:
                    continue
            
            if content is None:
                content = downloaded_file.decode('utf-8', errors='ignore')
            
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            
            if len(lines) == 0:
                
                self.bot.send_message(message.chat.id, "❌ File is empty or contains no valid lines.")
                return True
            
            product_code = product_data.get('code', 'temp')
            temp_base_dir = os.path.join(self.products_dir, 'temp')
            os.makedirs(temp_base_dir, exist_ok=True)
            
            temp_folder = None
            temp_folder_name = None
            
            if os.path.exists(temp_base_dir):
                for folder_name in os.listdir(temp_base_dir):
                    if folder_name.startswith(f"{product_code}_"):
                        temp_folder_name = folder_name
                        temp_folder = os.path.join(temp_base_dir, folder_name)
                        break
            
            if not temp_folder:
                unix_time = int(time.time())
                temp_folder_name = f"{product_code}_{unix_time}"
                temp_folder = os.path.join(temp_base_dir, temp_folder_name)
                os.makedirs(temp_folder, exist_ok=True)
            
            json_file_name = file_name.replace('.txt', '.json')
            local_path = os.path.join(temp_folder, json_file_name)
            
            json_data = {'total_products': len(lines), 'products': []}
            for i, line in enumerate(lines, 1):
                json_data['products'].append({'id': i, 'content': line, 'status': 'available'})
            
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(json_data, f, ensure_ascii=False, indent=2)
            
            relative_path = os.path.join('products', 'temp', temp_folder_name, json_file_name)
            file_data = {
                'file_id': file_info.file_id,
                'file_name': json_file_name,
                'original_file_name': file_name,
                'local_path': local_path,
                'relative_path': relative_path,
                'size': file_info.file_size,
                'type': 'json',
                'line_count': len(lines)
            }
            product_data['files'] = [file_data]
            product_data['stock'] = len(lines)
            
            self.db.set_user_state(
                user_id=user_id,
                state='creating_product_summary',
                data=json.dumps({'lang_code': lang_code, 'product_data': product_data})
            )
            
            from handlers.product_creation_handler import ProductCreationHandler
            creation_handler = ProductCreationHandler(self.bot, self.db, self.language, self.config)
            creation_handler.proceed_to_review_settings(message, user_id, lang_code, product_data)
            
        except Exception as e:
            import traceback
            logger.error(f"Error handling line file upload: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.bot.send_message(message.chat.id, f"❌ Error processing file: {str(e)}")
        
        return True
    
    def handle_drop_upload(self, message, user_id, lang_code, product_data):
        """Every uploaded photo/video/image-doc becomes one stock item for the drop product."""
        file_info = None
        file_name = None
        file_type = None
        current_count = len(product_data.get('drop_items', []))
        
        if message.photo:
            file_info = message.photo[-1]
            file_name = f"drop_{current_count + 1}.jpg"
            file_type = 'photo'
        elif message.video:
            file_info = message.video
            file_name = f"drop_{current_count + 1}.mp4"
            file_type = 'video'
        elif message.document:
            file_info = message.document
            original_name = message.document.file_name or f"drop_{current_count + 1}"
            ext = original_name.split('.')[-1].lower() if '.' in original_name else ''
            if ext not in self.IMAGE_TYPES:
                self.bot.send_message(message.chat.id, "❌ Send a photo, video, or image document.")
                return True
            file_name = original_name
            file_type = 'video' if ext == 'mp4' else 'photo'
        else:
            self.bot.send_message(message.chat.id, "❌ Send a photo, video, or image document.")
            return True
        
        if getattr(file_info, 'file_size', 0) > self.IMAGE_SIZE_LIMIT:
            large_text = self.language.get_text('file_too_large', lang_code)
            formatted_text = large_text.format(max_size=10)
            self.bot.send_message(message.chat.id, formatted_text)
            return True
        
        drop_item = {
            'file_id': file_info.file_id,
            'file_unique_id': getattr(file_info, 'file_unique_id', None),
            'file_name': file_name,
            'size': getattr(file_info, 'file_size', 0),
            'type': file_type,
            'storage_type': 'telegram_file_id',
            'uploaded_at': int(time.time()),
            'caption': (message.caption or "").strip()
        }
        
        if hasattr(file_info, 'width'):
            drop_item['width'] = getattr(file_info, 'width', None)
        if hasattr(file_info, 'height'):
            drop_item['height'] = getattr(file_info, 'height', None)
        if hasattr(file_info, 'duration'):
            drop_item['duration'] = getattr(file_info, 'duration', None)
        
        product_data.setdefault('drop_items', []).append(drop_item)
        product_data['stock'] = len(product_data['drop_items'])
        
        self.db.set_user_state(
            user_id=user_id,
            state='creating_product_step_7_drop',
            data=json.dumps({'lang_code': lang_code, 'product_data': product_data})
        )
        
        self.send_drop_status(message, lang_code, product_data)
        return True
    
    def send_drop_status(self, message, lang_code, product_data):
        drop_items = product_data.get('drop_items', [])
        all_have_captions = len(drop_items) > 0 and all(
            (item.get('caption') or '').strip() for item in drop_items
        )

        caption_status = "✅ Set" if all_have_captions else "❌ Missing"

        text = (
            f"🖼️ <b>Uploadeaza Drop</b>\n\n"
            f"<b>Produs:</b> {product_data['name']}\n"
            f"<b>Drop uri bagate:</b> {len(drop_items)}\n"
            f"<b>Stock:</b> {len(drop_items)}\n"
            f"<b>Coordonate:</b> {caption_status}\n\n"
            f"Trimite mai multe poze pentru a creste stock-ul.\n"
            f"Fiecare poza trebuie sa aibe coordonatele ei.\n"
            f"Cand esti gata, apasa pe Continua."
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

        self.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            reply_markup=markup,
            parse_mode='HTML'
        )
    def handle_upload_more_lines(self, message, user_id, lang_code, state_data):
        if not message.document:
            self.bot.send_message(message.chat.id, "❌ Please upload a .txt file")
            return True
        
        file_info = message.document
        file_name = file_info.file_name or "file.txt"
        file_ext = file_name.split('.')[-1].lower() if '.' in file_name else ''
        if file_ext != 'txt':
            self.bot.send_message(message.chat.id, "❌ Only .txt files are supported")
            return True
        
        if file_info.file_size > self.PRODUCT_SIZE_LIMIT:
            self.bot.send_message(message.chat.id, "❌ File too large. Maximum size: 50MB")
            return True
        
        try:
            product_id = state_data.get('product_id')
            products_data = self.load_products()
            product = None
            product_index = None
            
            for i, p in enumerate(products_data.get('products', [])):
                if p['id'] == product_id:
                    product = p
                    product_index = i
                    break
            
            if not product:
                self.bot.send_message(message.chat.id, "❌ Product not found")
                self.db.clear_user_state(user_id)
                return True
            
            file_path = self.bot.get_file(file_info.file_id)
            downloaded_file = self.bot.download_file(file_path.file_path)
            
            content = None
            for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
                try:
                    content = downloaded_file.decode(encoding)
                    break
                except Exception:
                    continue
            
            if content is None:
                content = downloaded_file.decode('utf-8', errors='ignore')
            
            new_lines = [line.strip() for line in content.split('\n') if line.strip()]
            if len(new_lines) == 0:
                self.bot.send_message(message.chat.id, "❌ File is empty or contains no valid lines")
                return True
            
            files = product.get('files', [])
            if not files:
                self.bot.send_message(message.chat.id, "❌ Product has no existing data file")
                self.db.clear_user_state(user_id)
                return True
            
            file_data = files[0]
            json_file_path = file_data.get('local_path') or file_data.get('relative_path')
            
            if not json_file_path or not os.path.exists(json_file_path):
                self.bot.send_message(message.chat.id, f"❌ Product data file not found: {json_file_path}")
                self.db.clear_user_state(user_id)
                return True
            
            with open(json_file_path, 'r', encoding='utf-8') as f:
                line_data = json.load(f)
            
            existing_products = line_data.get('products', [])
            max_id = max([p.get('id', 0) for p in existing_products]) if existing_products else 0
            
            for i, line_content in enumerate(new_lines, start=1):
                existing_products.append({'id': max_id + i, 'content': line_content, 'status': 'available'})
            
            line_data['products'] = existing_products
            line_data['total_products'] = len(existing_products)
            
            with open(json_file_path, 'w', encoding='utf-8') as f:
                json.dump(line_data, f, indent=2, ensure_ascii=False)
            
            new_stock = product.get('stock', 0) + len(new_lines)
            products_data['products'][product_index]['stock'] = new_stock
            products_data['products'][product_index]['files'][0]['line_count'] = line_data['total_products']
            save_json_safely('products.json', products_data)
            self.db.clear_user_state(user_id)
            
            success_text = (
                f"✅ <b>Successfully added {len(new_lines)} lines!</b>\n\n"
                f"<b>Product:</b> {product['name']}\n"
                f"<b>Previous Stock:</b> {product.get('stock', 0)} lines\n"
                f"<b>New Stock:</b> {new_stock} lines\n"
                f"<b>Total Lines:</b> {line_data['total_products']}"
            )
            self.bot.send_message(message.chat.id, success_text, parse_mode='HTML')
            
        except Exception as e:
            import traceback
            logger.error(f"Error uploading more lines: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            self.bot.send_message(message.chat.id, f"❌ Error processing file: {str(e)}")
            self.db.clear_user_state(user_id)
        
        return True
    
    def handle_upload_more_drops(self, message, user_id, lang_code, state_data):
        product_id = state_data.get('product_id')
        products_data = self.load_products()
        product = None
        product_index = None

        for i, p in enumerate(products_data.get('products', [])):
            if p.get('id') == product_id:
                product = p
                product_index = i
                break

        if not product:
            self.bot.send_message(message.chat.id, "❌ Product not found")
            self.db.clear_user_state(user_id)
            return True

        # Accept only photo/video/image document
        file_info = None
        file_name = None
        file_type = None

        if message.photo:
            file_info = message.photo[-1]
            file_name = f"drop_{len(product.get('drop_items', [])) + 1}.jpg"
            file_type = 'photo'
        elif message.video:
            file_info = message.video
            file_name = f"drop_{len(product.get('drop_items', [])) + 1}.mp4"
            file_type = 'video'
        elif message.document:
            file_info = message.document
            original_name = message.document.file_name or f"drop_{len(product.get('drop_items', [])) + 1}"
            ext = original_name.split('.')[-1].lower() if '.' in original_name else ''
            if ext not in self.IMAGE_TYPES:
                self.bot.send_message(message.chat.id, "❌ Send a photo, video, or image document.")
                return True
            file_name = original_name
            file_type = 'video' if ext == 'mp4' else 'photo'
        else:
            self.bot.send_message(message.chat.id, "❌ Send a photo with caption.")
            return True

        if getattr(file_info, 'file_size', 0) > self.IMAGE_SIZE_LIMIT:
            self.bot.send_message(message.chat.id, "❌ File too large. Max 10MB.")
            return True

        caption = (message.caption or "").strip()
        if not caption:
            self.bot.send_message(message.chat.id, "❌ Fiecare poză trebuie să aibă caption.")
            return True

        drop_items = product.get('drop_items', [])

        drop_item = {
            'file_id': file_info.file_id,
            'file_unique_id': getattr(file_info, 'file_unique_id', None),
            'file_name': file_name,
            'size': getattr(file_info, 'file_size', 0),
            'type': file_type,
            'storage_type': 'telegram_file_id',
            'uploaded_at': int(time.time()),
            'caption': caption
        }

        if hasattr(file_info, 'width'):
            drop_item['width'] = getattr(file_info, 'width', None)
        if hasattr(file_info, 'height'):
            drop_item['height'] = getattr(file_info, 'height', None)
        if hasattr(file_info, 'duration'):
            drop_item['duration'] = getattr(file_info, 'duration', None)

        drop_items.append(drop_item)

        products_data['products'][product_index]['drop_items'] = drop_items
        products_data['products'][product_index]['stock'] = len(drop_items)

        save_json_safely('products.json', products_data)

        # keep user in upload-more mode
        self.db.set_user_state(
            user_id=user_id,
            state='uploading_more_drops',
            data=json.dumps({
                'lang_code': lang_code,
                'product_id': product_id
            })
        )

        markup = telebot.types.InlineKeyboardMarkup()
        markup.add(telebot.types.InlineKeyboardButton(
            text="🖼️ Upload More",
            callback_data=f'prod_upload_more_{product_id}'
        ))
        markup.add(telebot.types.InlineKeyboardButton(
            text="🔙 Back to Product",
            callback_data=f'prod_view_{product_id}'
        ))

        self.bot.send_message(
            message.chat.id,
            (
                f"✅ <b>Drop adăugat cu succes</b>\n\n"
                f"<b>Produs:</b> {product.get('name', 'Unknown')}\n"
                f"<b>Stock curent:</b> {len(drop_items)}\n\n"
                f"Poți trimite încă o poză sau te poți întoarce la produs."
            ),
            reply_markup=markup,
            parse_mode='HTML'
        )

        return True
    
    def handle_text_input(self, message):
        return False
    
    def load_products(self):
        try:
            with open('products.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading products: {e}")
            return {'products': []}
    
    def format_file_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        elif size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
