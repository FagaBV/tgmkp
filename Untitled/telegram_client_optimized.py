import requests
import logging
import time
import threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

# Disable SSL warnings for development
disable_warnings(InsecureRequestWarning)

logger = logging.getLogger(__name__)

class OptimizedTelegramClient:
    """Optimized HTTP client for Telegram Bot API with connection pooling and retry logic"""
    
    def __init__(self, bot_token, base_url="https://api.telegram.org"):
        self.bot_token = bot_token
        self.base_url = f"{base_url}/bot{bot_token}"
        
        # Create optimized session with connection pooling
        self.session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,  # Total number of retries
            backoff_factor=0.3,  # Wait time between retries
            status_forcelist=[429, 500, 502, 503, 504],  # HTTP status codes to retry
            allowed_methods=["HEAD", "GET", "POST"]  # Methods to retry
        )
        
        # Configure HTTP adapter with connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,      # Max connections per pool
            max_retries=retry_strategy,
            pool_block=False      # Don't block when pool is full
        )
        
        # Mount adapters for both HTTP and HTTPS
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Set optimized session headers
        self.session.headers.update({
            'User-Agent': 'OptimizedTelegramBot/1.0',
            'Connection': 'keep-alive',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate'
        })
        
        # Performance tracking
        self.request_count = 0
        self.total_time = 0
        self.lock = threading.Lock()
        
        logger.info("🚀 OptimizedTelegramClient initialized with connection pooling")
    
    def _make_request(self, method, endpoint, data=None, files=None, timeout=10):
        """Make optimized HTTP request to Telegram API"""
        url = f"{self.base_url}/{endpoint}"
        
        start_time = time.time()
        
        try:
            # Use optimized session with connection pooling
            if method.upper() == 'POST':
                if files:
                    # For file uploads, don't set Content-Type (requests will set it)
                    response = self.session.post(
                        url, 
                        data=data, 
                        files=files, 
                        timeout=timeout,
                        verify=False  # Skip SSL verification for speed (development only)
                    )
                else:
                    # For JSON data
                    response = self.session.post(
                        url, 
                        json=data, 
                        timeout=timeout,
                        verify=False
                    )
            else:
                response = self.session.get(
                    url, 
                    params=data, 
                    timeout=timeout,
                    verify=False
                )
            
            # Track performance
            request_time = time.time() - start_time
            with self.lock:
                self.request_count += 1
                self.total_time += request_time
            
            # Log performance for debugging
            if request_time > 2.0:  # Log slow requests
                logger.warning(f"🐌 Slow request to {endpoint}: {request_time:.3f}s")
            elif request_time > 5.0:  # Log very slow requests
                logger.error(f"🚨 Very slow request to {endpoint}: {request_time:.3f}s")
            else:
                logger.debug(f"⚡ Fast request to {endpoint}: {request_time:.3f}s")
            
            # Handle response
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            logger.error(f"⏰ Timeout on {endpoint} after {timeout}s")
            return {"ok": False, "error_code": 408, "description": "Request timeout"}
        except requests.exceptions.ConnectionError:
            logger.error(f"🔌 Connection error on {endpoint}")
            return {"ok": False, "error_code": 502, "description": "Connection error"}
        except requests.exceptions.RequestException as e:
            logger.error(f"🚫 Request error on {endpoint}: {e}")
            return {"ok": False, "error_code": 500, "description": str(e)}
        except Exception as e:
            logger.error(f"💥 Unexpected error on {endpoint}: {e}")
            return {"ok": False, "error_code": 500, "description": str(e)}
    
    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
        """Optimized send_message method"""
        data = {
            "chat_id": chat_id,
            "text": text
        }
        
        if reply_markup:
            data["reply_markup"] = reply_markup
        if parse_mode:
            data["parse_mode"] = parse_mode
        if disable_web_page_preview is not None:
            data["disable_web_page_preview"] = disable_web_page_preview
            
        return self._make_request("POST", "sendMessage", data, timeout=8)
    
    def edit_message_text(self, text, chat_id=None, message_id=None, inline_message_id=None, 
                         parse_mode=None, reply_markup=None, disable_web_page_preview=None):
        """Optimized edit_message_text method"""
        data = {"text": text}
        
        if chat_id is not None:
            data["chat_id"] = chat_id
        if message_id is not None:
            data["message_id"] = message_id
        if inline_message_id is not None:
            data["inline_message_id"] = inline_message_id
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup
        if disable_web_page_preview is not None:
            data["disable_web_page_preview"] = disable_web_page_preview
            
        return self._make_request("POST", "editMessageText", data, timeout=8)
    
    def edit_message_reply_markup(self, chat_id=None, message_id=None, inline_message_id=None, reply_markup=None):
        """Optimized edit_message_reply_markup method"""
        data = {}
        
        if chat_id is not None:
            data["chat_id"] = chat_id
        if message_id is not None:
            data["message_id"] = message_id
        if inline_message_id is not None:
            data["inline_message_id"] = inline_message_id
        if reply_markup:
            data["reply_markup"] = reply_markup
            
        return self._make_request("POST", "editMessageReplyMarkup", data, timeout=6)
    
    def answer_callback_query(self, callback_query_id, text=None, show_alert=False, url=None, cache_time=None):
        """Optimized answer_callback_query method with better error handling"""
        data = {"callback_query_id": callback_query_id}
        
        if text:
            data["text"] = text[:200]  # Telegram limit is 200 characters
        if show_alert is not None:
            data["show_alert"] = show_alert
        if url:
            data["url"] = url
        if cache_time is not None:
            data["cache_time"] = cache_time
            
        result = self._make_request("POST", "answerCallbackQuery", data, timeout=5)
        
        # Handle common callback query errors gracefully
        if not result.get("ok", False):
            error_code = result.get("error_code")
            description = result.get("description", "")
            
            if error_code == 400:
                if "query is too old" in description.lower():
                    logger.debug(f"🕰️ Callback query {callback_query_id} expired")
                elif "query_id_invalid" in description.lower():
                    logger.debug(f"🚫 Invalid callback query ID: {callback_query_id}")
                else:
                    logger.warning(f"⚠️ Bad request for callback query: {description}")
            else:
                logger.error(f"🚫 Callback query error ({error_code}): {description}")
                
        return result
    
    def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
        """Optimized send_photo method"""
        data = {"chat_id": chat_id}
        files = None
        
        if caption:
            data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        # Handle photo as file or URL
        if isinstance(photo, str) and (photo.startswith('http') or photo.startswith('AgAC')):
            data["photo"] = photo
        else:
            files = {"photo": photo}
            
        return self._make_request("POST", "sendPhoto", data, files=files, timeout=15)
    
    def send_document(self, chat_id, document, caption=None, parse_mode=None, reply_markup=None):
        """Optimized send_document method"""
        data = {"chat_id": chat_id}
        files = None
        
        if caption:
            data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        # Handle document as file or URL
        if isinstance(document, str) and (document.startswith('http') or document.startswith('BAAC')):
            data["document"] = document
        else:
            files = {"document": document}
            
        return self._make_request("POST", "sendDocument", data, files=files, timeout=20)
    
    def send_media_group(self, chat_id, media, disable_notification=None, reply_to_message_id=None):
        """Optimized send_media_group method"""
        import json
        
        # Ensure media is properly formatted as JSON string
        if isinstance(media, str):
            media_json = media
        elif isinstance(media, list):
            media_json = json.dumps(media)
        else:
            media_json = str(media)
        
        data = {
            "chat_id": chat_id,
            "media": media_json
        }
        
        if disable_notification is not None:
            data["disable_notification"] = disable_notification
        if reply_to_message_id is not None:
            data["reply_to_message_id"] = reply_to_message_id
            
        return self._make_request("POST", "sendMediaGroup", data, timeout=15)  # Reduced timeout
    
    def send_video(self, chat_id, video, duration=None, width=None, height=None, 
                  caption=None, parse_mode=None, reply_markup=None):
        """Optimized send_video method"""
        data = {"chat_id": chat_id}
        files = None
        
        if duration is not None:
            data["duration"] = duration
        if width is not None:
            data["width"] = width
        if height is not None:
            data["height"] = height
        if caption:
            data["caption"] = caption
        if parse_mode:
            data["parse_mode"] = parse_mode
        if reply_markup:
            data["reply_markup"] = reply_markup
        
        # Handle video as file or URL
        if isinstance(video, str) and (video.startswith('http') or video.startswith('BAAC')):
            data["video"] = video
        else:
            files = {"video": video}
            
        return self._make_request("POST", "sendVideo", data, files=files, timeout=30)
    
    def delete_message(self, chat_id, message_id):
        """Optimized delete_message method"""
        data = {
            "chat_id": chat_id,
            "message_id": message_id
        }
        
        return self._make_request("POST", "deleteMessage", data, timeout=5)
    
    def get_file(self, file_id):
        """Optimized get_file method"""
        data = {"file_id": file_id}
        
        return self._make_request("POST", "getFile", data, timeout=10)
    
    def get_me(self):
        """Optimized get_me method"""
        return self._make_request("GET", "getMe", timeout=5)
    
    def get_updates(self, offset=None, limit=None, timeout=None, allowed_updates=None):
        """Optimized get_updates method for polling"""
        data = {}
        
        if offset is not None:
            data["offset"] = offset
        if limit is not None:
            data["limit"] = limit
        if timeout is not None:
            data["timeout"] = timeout
        if allowed_updates is not None:
            data["allowed_updates"] = allowed_updates
            
        # Use longer timeout for long polling
        request_timeout = (timeout + 5) if timeout else 30
        return self._make_request("POST", "getUpdates", data, timeout=request_timeout)
    
    def get_stats(self):
        """Get performance statistics"""
        with self.lock:
            if self.request_count > 0:
                avg_time = self.total_time / self.request_count
                return {
                    "total_requests": self.request_count,
                    "total_time": round(self.total_time, 3),
                    "average_time": round(avg_time, 3),
                    "requests_per_second": round(self.request_count / max(self.total_time, 0.001), 2)
                }
            return {"total_requests": 0, "total_time": 0, "average_time": 0, "requests_per_second": 0}
    
    def keep_alive_ping(self):
        """Keep API connection warm with a lightweight ping"""
        try:
            # Use getMe as it's the lightest API call
            result = self._make_request("GET", "getMe", timeout=5)
            
            if result.get("ok"):
                logger.debug("🏓 API keep-alive ping successful")
                return True
            else:
                logger.warning(f"⚠️ API keep-alive ping failed: {result}")
                return False
                
        except Exception as e:
            logger.warning(f"🔌 API keep-alive ping error: {e}")
            return False
    
    def warm_connection(self):
        """Pre-warm the connection pool"""
        try:
            # Make a few lightweight requests to warm up connections
            for _ in range(3):
                result = self.keep_alive_ping()
                if result:
                    break
                time.sleep(0.1)
            
            logger.info("🔥 API connection warmed up")
            return True
            
        except Exception as e:
            logger.warning(f"🌡️ Connection warm-up failed: {e}")
            return False
    
    def close(self):
        """Close the session and clean up resources"""
        try:
            self.session.close()
            logger.info("🔒 OptimizedTelegramClient session closed")
        except Exception as e:
            logger.error(f"Error closing session: {e}")


class TelebotOptimizedWrapper:
    """Wrapper to make OptimizedTelegramClient compatible with existing telebot code"""
    
    def __init__(self, bot_token, **kwargs):
        self.token = bot_token
        self.client = OptimizedTelegramClient(bot_token)
        
        # Store original telebot instance for compatibility
        import telebot
        self._original_bot = telebot.TeleBot(bot_token, **kwargs)
        
        # Copy handler registration methods from original bot
        self.message_handler = self._original_bot.message_handler
        self.callback_query_handler = self._original_bot.callback_query_handler
        self.infinity_polling = self._original_bot.infinity_polling
        
        logger.info("🔄 TelebotOptimizedWrapper initialized")
    
    def send_message(self, chat_id, text, reply_markup=None, parse_mode=None, disable_web_page_preview=None):
        """Optimized send_message using our fast HTTP client"""
        # Convert reply_markup to JSON if it's a telebot object
        markup_json = None
        if reply_markup:
            if hasattr(reply_markup, 'to_json'):
                markup_json = reply_markup.to_json()
            else:
                import json
                markup_json = json.dumps(reply_markup)
        
        result = self.client.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=markup_json,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        
        # Return telebot-compatible result
        if result.get("ok"):
            return result["result"]
        else:
            logger.error(f"Send message failed: {result}")
            return None
    
    def edit_message_text(self, text, chat_id=None, message_id=None, inline_message_id=None, 
                         parse_mode=None, reply_markup=None, disable_web_page_preview=None):
        """Optimized edit_message_text"""
        markup_json = None
        if reply_markup:
            if hasattr(reply_markup, 'to_json'):
                markup_json = reply_markup.to_json()
            else:
                import json
                markup_json = json.dumps(reply_markup)
        
        result = self.client.edit_message_text(
            text=text,
            chat_id=chat_id,
            message_id=message_id,
            inline_message_id=inline_message_id,
            parse_mode=parse_mode,
            reply_markup=markup_json,
            disable_web_page_preview=disable_web_page_preview
        )
        
        if result.get("ok"):
            return result["result"]
        return None
    
    def answer_callback_query(self, callback_query_id, text=None, show_alert=False, url=None, cache_time=None):
        """Optimized answer_callback_query with proper error handling"""
        try:
            result = self.client.answer_callback_query(
                callback_query_id=callback_query_id,
                text=text,
                show_alert=show_alert,
                url=url,
                cache_time=cache_time
            )
            
            if result.get("ok", False):
                return True
            else:
                # Log the specific error but don't raise exception
                error_code = result.get("error_code", "unknown")
                description = result.get("description", "unknown error")
                if error_code == 400 and "query is too old" in description.lower():
                    logger.debug(f"🕰️ Callback query expired: {description}")
                else:
                    logger.warning(f"⚠️ Callback query failed ({error_code}): {description}")
                return False
                
        except Exception as e:
            logger.error(f"🚫 Exception in answer_callback_query: {e}")
            return False
    
    def send_photo(self, chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
        """Optimized send_photo"""
        markup_json = None
        if reply_markup:
            if hasattr(reply_markup, 'to_json'):
                markup_json = reply_markup.to_json()
            else:
                import json
                markup_json = json.dumps(reply_markup)
        
        result = self.client.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=markup_json
        )
        
        if result.get("ok"):
            return result["result"]
        return None
    
    def send_document(self, chat_id, document, caption=None, parse_mode=None, reply_markup=None):
        """Optimized send_document"""
        markup_json = None
        if reply_markup:
            if hasattr(reply_markup, 'to_json'):
                markup_json = reply_markup.to_json()
            else:
                import json
                markup_json = json.dumps(reply_markup)
        
        result = self.client.send_document(
            chat_id=chat_id,
            document=document,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=markup_json
        )
        
        if result.get("ok"):
            return result["result"]
        return None
    
    def send_media_group(self, chat_id, media, disable_notification=None, reply_to_message_id=None):
        """Optimized send_media_group"""
        # Convert media list to JSON if needed
        media_json = media
        if isinstance(media, list) and media:
            import json
            # Handle telebot objects
            if hasattr(media[0], 'to_dict'):
                media_json = json.dumps([item.to_dict() for item in media])
            # Handle dict objects
            elif isinstance(media[0], dict):
                media_json = json.dumps(media)
            # Handle string (already JSON)
            elif isinstance(media, str):
                media_json = media
        
        result = self.client.send_media_group(
            chat_id=chat_id,
            media=media_json,
            disable_notification=disable_notification,
            reply_to_message_id=reply_to_message_id
        )
        
        if result.get("ok"):
            return result["result"]
        return None
    
    def send_video(self, chat_id, video, duration=None, width=None, height=None, 
                  caption=None, parse_mode=None, reply_markup=None):
        """Optimized send_video"""
        markup_json = None
        if reply_markup:
            if hasattr(reply_markup, 'to_json'):
                markup_json = reply_markup.to_json()
            else:
                import json
                markup_json = json.dumps(reply_markup)
        
        result = self.client.send_video(
            chat_id=chat_id,
            video=video,
            duration=duration,
            width=width,
            height=height,
            caption=caption,
            parse_mode=parse_mode,
            reply_markup=markup_json
        )
        
        if result.get("ok"):
            return result["result"]
        return None
    
    def delete_message(self, chat_id, message_id):
        """Optimized delete_message"""
        result = self.client.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )
        
        return result.get("ok", False)
    
    def get_file(self, file_id):
        """Optimized get_file"""
        result = self.client.get_file(file_id)
        
        if result.get("ok"):
            # Create a compatible File object
            import telebot.types
            file_data = result["result"]
            return telebot.types.File(
                file_id=file_data['file_id'],
                file_unique_id=file_data.get('file_unique_id'),
                file_size=file_data.get('file_size'),
                file_path=file_data.get('file_path')
            )
        return None
    
    def download_file(self, file_path):
        """Download file from Telegram servers"""
        try:
            # Construct the file URL
            url = f"https://api.telegram.org/file/bot{self.token}/{file_path}"
            
            # Download the file using the optimized session
            response = self.client.session.get(url, timeout=30, verify=False)
            response.raise_for_status()
            
            return response.content
        except Exception as e:
            logger.error(f"Error downloading file: {e}")
            # Fallback to original bot's download method
            return self._original_bot.download_file(file_path)
    
    def get_me(self):
        """Optimized get_me - returns telebot-compatible User object"""
        result = self.client.get_me()
        
        if result.get("ok"):
            # Convert dict to telebot User object for compatibility
            import telebot.types
            user_data = result["result"]
            return telebot.types.User(
                id=user_data['id'],
                is_bot=user_data['is_bot'],
                first_name=user_data['first_name'],
                username=user_data.get('username'),
                last_name=user_data.get('last_name'),
                language_code=user_data.get('language_code'),
                can_join_groups=user_data.get('can_join_groups'),
                can_read_all_group_messages=user_data.get('can_read_all_group_messages'),
                supports_inline_queries=user_data.get('supports_inline_queries')
            )
        return None
    
    def get_performance_stats(self):
        """Get performance statistics from the optimized client"""
        return self.client.get_stats()
    
    def keep_api_warm(self):
        """Keep the API connection warm"""
        return self.client.keep_alive_ping()
    
    def warm_connection(self):
        """Pre-warm the API connection"""
        return self.client.warm_connection()
    
    def close(self):
        """Close the optimized client"""
        self.client.close()
