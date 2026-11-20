import telebot
import logging
import math
from cache_manager import save_json_safely
from utils import replace_message

logger = logging.getLogger(__name__)

class ReviewsHandler:
    def __init__(self, bot, db, language, config):
        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.per_page = 3  # Reviews per page
    
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
    
    def handle_reviews_menu(self, call):
        """Handle reviews button click - show all reviews with pagination"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        if not user:
            self.bot.answer_callback_query(call.id, "❌ Database error")
            return
        
        lang_code = user['language_code']
        
        # Show first page
        self.show_reviews_page(call, 1, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
            
    def clean_review_products(self, products):
        """Return a clean readable product name/string for reviews"""
        if not products:
            return "Unknown Product"

        # Dacă vine deja listă
        if isinstance(products, list):
            cleaned = []
            for item in products:
                if isinstance(item, dict):
                    name = item.get('name') or item.get('product_name') or item.get('product')
                    if name:
                        cleaned.append(str(name))
                elif isinstance(item, str):
                    item = item.strip()
                    if item:
                        # dacă e JSON string
                        if item.startswith('{'):
                            try:
                                parsed = json.loads(item)
                                if isinstance(parsed, dict):
                                    name = parsed.get('name') or parsed.get('product_name')
                                    if name:
                                        cleaned.append(str(name))
                                        continue
                            except Exception:
                                pass
                        cleaned.append(item)

            return ", ".join(cleaned) if cleaned else "Unknown Product"

        # Dacă vine dict direct
        if isinstance(products, dict):
            return (
                products.get('name')
                or products.get('product_name')
                or products.get('product')
                or "Unknown Product"
            )

        # Dacă vine string
        if isinstance(products, str):
            products = products.strip()

            # JSON string
            if products.startswith('{'):
                try:
                    parsed = json.loads(products)
                    if isinstance(parsed, dict):
                        return (
                            parsed.get('name')
                            or parsed.get('product_name')
                            or parsed.get('product')
                            or "Unknown Product"
                        )
                except Exception:
                    pass

            # listă JSON string
            if products.startswith('['):
                try:
                    parsed = json.loads(products)
                    return self.clean_review_products(parsed)
                except Exception:
                    pass

            return products or "Unknown Product"

        return str(products)
    
    def show_reviews_page(self, call, page, lang_code):
        """Show reviews page with pagination"""
        # Get average rating
        rating_data = self.db.get_average_rating()
        avg_rating = rating_data['average']
        total_count = rating_data['count']
        
        # Get reviews for this page
        reviews = self.db.get_all_reviews(page=page, per_page=self.per_page)
        
        # Calculate total pages
        total_pages = max(1, math.ceil(total_count / self.per_page))
        
        # Build message
        texts = self.language.get_text('reviews', lang_code)
        
        text = f"{texts.get('title', '⭐ Recenzii')}\n\n"
        
        # Show average rating
        avg_text = texts.get('average_rating', '📊 Medie Recenzii: {rating}/5 ⭐ ({count} reviews)')
        text += avg_text.format(rating=avg_rating, count=total_count) + "\n\n"
        
        if not reviews:
            text += texts.get('no_reviews', '📝 Nu exista recenzii.')
        else:
            # Add separator
            text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for review in reviews:
                # Convert star rating to stars
                stars = "⭐" * review['star_rating'] + "☆" * (5 - review['star_rating'])
               
                
                # Truncate review text if too long
                review_text = review['review_text'] or "Fara comentarii"
                if len(review_text) > 150:
                    review_text = review_text[:147] + "..."
                
                # Format date
                date = review['review_date'][:10] if review['review_date'] else "Unknown"
                
                # Parser pentru a lua produsele chit ca sunt json

                # Products
                products = review['products'][:50] + "..." if len(review['products']) > 50 else review['products']
                
                clean_products = self.clean_review_products(products)
                review_template = texts.get('review_item', '⭐ {stars}\n 💬 {text}\n📅 {date}')
                text += review_template.format(
                    stars=stars,
                    products="",
                    text=review_text,
                    date=date
                ) + "\n\n━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            # Page info
            page_info = texts.get('page_info', '📄 Pagina {current} din {total}')
            text += page_info.format(current=page, total=total_pages)
        
        # Build markup with pagination
        markup = telebot.types.InlineKeyboardMarkup(row_width=3)
        
        # Pagination buttons
        pagination_buttons = []
        
        if page > 1:
            pagination_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text="⬅️ Inapoi",
                    callback_data=f"reviews_page_{page - 1}"
                )
            )
        
        if total_count > 0:
            pagination_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text=f"{page}/{total_pages}",
                    callback_data="ignore"
                )
            )
        
        if page < total_pages:
            pagination_buttons.append(
                telebot.types.InlineKeyboardButton(
                    text="Urmatorul ➡️",
                    callback_data=f"reviews_page_{page + 1}"
                )
            )
        
        if pagination_buttons:
            markup.row(*pagination_buttons)
        
        # Back button
        back_text = texts.get('back_to_menu', '🔙 Inapoi')
        markup.row(telebot.types.InlineKeyboardButton(
            text=back_text,
            callback_data="main_menu"
        ))
        
        self.send_page_with_image(
            call.message.chat.id,
            'reviews_menu',
            text,
            markup
        )
            
    def handle_reviews_callbacks(self, call):
        """Handle reviews-related callbacks"""
        user_id = call.from_user.id
        
        user = self.db.get_or_create_user(user_id)
        lang_code = user['language_code'] if user else 'ro'
        
        if call.data.startswith('reviews_page_'):
            page = int(call.data.replace('reviews_page_', ''))
            self.show_reviews_page(call, page, lang_code)
        
        try:
            self.bot.answer_callback_query(call.id)
        except:
            pass
