import json
import logging
import re
import os
from json_cache import json_cache
from cache_manager import get_json_cached

logger = logging.getLogger(__name__)

class Language:
    def __init__(self, language_file='language.json'):
        self.language_file = language_file
        self.languages = self.load_languages()
        self.available_languages = list(self.languages.keys())
    
    def load_languages(self):
        """Load language data from JSON file with caching"""
        import time
        start_time = time.time()
        
        try:
            logger.info(f"🔍 DEBUG: Starting load_languages() at {start_time:.3f}")
            
            # Use cached JSON loading for massive performance boost
            cache_start = time.time()
            data = get_json_cached(self.language_file)
            cache_time = time.time() - cache_start
            logger.info(f"🔍 DEBUG: get_json_cached('{self.language_file}') took {cache_time:.3f}s")
            
            if data:
                load_time = time.time() - start_time
                logger.info(f"🔍 DEBUG: load_languages() completed in {load_time:.3f}s, loaded {len(data)} languages")
                return data
            else:
                load_time = time.time() - start_time
                logger.error(f"🔍 DEBUG: Language file {self.language_file} not found, load_languages() took {load_time:.3f}s")
                return {}
        except Exception as e:
            load_time = time.time() - start_time
            logger.error(f"🔍 DEBUG: Error parsing language file: {e}, load_languages() took {load_time:.3f}s")
            return {}
    
    def get_text(self, key, lang_code='en', **kwargs):
        """Get text by key and language code with formatting support"""
        import time
        start_time = time.time()
        
        try:
            # DEBUG: Check if languages dict is populated
            if not self.languages:
                lookup_time = time.time() - start_time
                logger.error(f"🔍 DEBUG: Languages dict is empty! get_text('{key}', '{lang_code}') took {lookup_time:.3f}s")
                return f"[No Languages Loaded]"
            
            lang_check_time = time.time()
            if lang_code not in self.languages:
                lang_code = 'en'  # Fallback to English
            lang_check_duration = time.time() - lang_check_time
            
            key_lookup_time = time.time()
            if key not in self.languages[lang_code]:
                if 'en' in self.languages and key in self.languages['en']:
                    text = self.languages['en'][key]  # Fallback to English
                else:
                    lookup_time = time.time() - start_time
                    logger.warning(f"🔍 DEBUG: Missing key '{key}' for lang '{lang_code}', get_text took {lookup_time:.3f}s")
                    return f"[Missing: {key}]"
            else:
                text = self.languages[lang_code][key]
            key_lookup_duration = time.time() - key_lookup_time
            
            # If text is a list or dict, return it as-is (for button arrays or nested objects)
            if isinstance(text, (list, dict)):
                lookup_time = time.time() - start_time
                if lookup_time > 0.001:  # Log if > 1ms
                    logger.info(f"🔍 DEBUG: get_text('{key}', '{lang_code}') {type(text).__name__} result took {lookup_time:.3f}s")
                return text
            
            # Format the text with provided kwargs
            format_time = time.time()
            if kwargs:
                text = text.format(**kwargs)
            format_duration = time.time() - format_time
            
            # Process HTML-like tags and escape sequences
            html_time = time.time()
            text = self.format_text(text)
            html_duration = time.time() - html_time
            
            lookup_time = time.time() - start_time
            if lookup_time > 0.001:  # Log if > 1ms
                logger.info(f"🔍 DEBUG: get_text('{key}', '{lang_code}') took {lookup_time:.3f}s (lang_check: {lang_check_duration:.3f}s, key_lookup: {key_lookup_duration:.3f}s, format: {format_duration:.3f}s, html: {html_duration:.3f}s)")
            
            return text
            
        except Exception as e:
            lookup_time = time.time() - start_time
            logger.error(f"🔍 DEBUG: Error getting text for key '{key}': {e}, took {lookup_time:.3f}s")
            return f"[Error: {key}]"
    
    def format_text(self, text):
        """Format text with HTML tags and escape sequences"""
        # Replace escape sequences
        text = text.replace('\\n', '\n')
        text = text.replace('\\t', '\t')
        
        # HTML tags are already supported by Telegram's HTML parse mode
        # Just ensure they're properly formatted
        return text
    
    def get_combined_language_setup_message(self):
        """Get combined language setup message from all languages"""
        messages = []
        for lang_code in self.available_languages:
            if 'lang_setup_msg' in self.languages[lang_code]:
                messages.append(self.languages[lang_code]['lang_setup_msg'])
        return '\n\n'.join(messages)
    
    def get_language_buttons(self):
        """Get list of available language buttons"""
        buttons = []
        for lang_code in self.available_languages:
            if 'button_show' in self.languages[lang_code]:
                buttons.append({
                    'text': self.languages[lang_code]['button_show'],
                    'callback_data': f'lang_{lang_code}'
                })
        return buttons
    
    def get_menu_buttons(self, lang_code, is_admin=False):
        """Get main menu buttons for given language"""
        buttons = []
        
        # Main Menu button
        main_menu_text = self.get_text('menu_button_main', lang_code)
        buttons.append([{
            'text': main_menu_text,
            'callback_data': 'main_menu'
        }])
        
        # Admin Panel button (only for admins)
        if is_admin:
            admin_panel_text = self.get_text('menu_button_admin', lang_code)
            buttons[0].append({
                'text': admin_panel_text,
                'callback_data': 'admin_panel'
            })
        
        return buttons
    
    def get_main_menu_buttons(self, lang_code, user_id=None, cart_handler=None):
        """Get main menu action buttons with dynamic cart button"""
        buttons = []
        button_data = self.get_text('button_texts_mainmenu', lang_code)
        
        if isinstance(button_data, list):
            admin_history_row = []
            
            for button_info in button_data:
                if isinstance(button_info, dict):
                    button_text = button_info['text']
                    
                    # Handle dynamic cart button
                    if button_info['id'] == 'cart' and cart_handler and user_id:
                        button_text = cart_handler.get_cart_button_text(lang_code, user_id)
                    
                    button_obj = {
                        'text': button_text,
                        'callback_data': f"menu_{button_info['id']}"
                    }
                    
                    # Special handling for Admin and History buttons - put them in the same row
                    if button_info['id'] == 'admin_link':
                        admin_history_row.append(button_obj)
                    elif button_info['id'] == 'history':
                        admin_history_row.append(button_obj)
                        # After adding history, add the row with both buttons
                        if admin_history_row:
                            buttons.append(admin_history_row)
                            admin_history_row = []
                    else:
                        # Add single button in its own row
                        buttons.append([button_obj])
                else:
                    # Fallback for old structure
                    buttons.append([{
                        'text': button_info,
                        'callback_data': f'menu_{len(buttons)}'
                    }])
            
            # If admin_history_row has remaining buttons (edge case)
            if admin_history_row:
                buttons.append(admin_history_row)
        
        return buttons
    
    def get_admin_buttons(self, lang_code):
        """Get admin panel buttons with new structure"""
        buttons = []
        button_data = self.get_text('button_texts_admin', lang_code)
        
        if isinstance(button_data, list):
            for button_info in button_data:
                if isinstance(button_info, dict):
                    buttons.append([{
                        'text': button_info['text'],
                        'callback_data': f"admin_{button_info['id']}"
                    }])
                else:
                    # Fallback for old structure
                    buttons.append([{
                        'text': button_info,
                        'callback_data': f'admin_{len(buttons)}'
                    }])
        
        return buttons
    
    def get_button_response(self, button_id, field=None, lang_code='en'):
        """Get button response message by button ID"""
        try:
            if lang_code not in self.languages:
                lang_code = 'en'
            
            button_responses = self.languages[lang_code].get('button_responses', {})
            if button_id in button_responses:
                response = button_responses[button_id]
                if field:
                    # Return specific field
                    if field == 'message':
                        return self.format_text(response.get('message', f'Response for {button_id}'))
                    else:
                        return response.get(field, button_id)
                else:
                    # Return full response object
                    return {
                        'title': response.get('title', button_id),
                        'message': self.format_text(response.get('message', f'Response for {button_id}'))
                    }
            
            # Fallback to English if not found
            if lang_code != 'en' and 'en' in self.languages:
                button_responses = self.languages['en'].get('button_responses', {})
                if button_id in button_responses:
                    response = button_responses[button_id]
                    if field:
                        if field == 'message':
                            return self.format_text(response.get('message', f'Response for {button_id}'))
                        else:
                            return response.get(field, button_id)
                    else:
                        return {
                            'title': response.get('title', button_id),
                            'message': self.format_text(response.get('message', f'Response for {button_id}'))
                        }
            
            # Default fallback
            if field == 'message':
                return f'Feature "{button_id}" coming soon!'
            elif field:
                return button_id.replace('_', ' ').title()
            else:
                return {
                    'title': button_id.replace('_', ' ').title(),
                    'message': f'Feature "{button_id}" coming soon!'
                }
            
        except Exception as e:
            logger.error(f"Error getting button response for '{button_id}': {e}")
            if field == 'message':
                return f'Error loading content for {button_id}'
            elif field:
                return 'Error'
            else:
                return {
                    'title': 'Error',
                    'message': f'Error loading content for {button_id}'
                }
    
    def reload_languages(self):
        """Reload language data from file"""
        # Force reload from file, bypassing cache
        json_cache.invalidate(self.language_file)
        self.languages = self.load_languages()
        self.available_languages = list(self.languages.keys())
        logger.info("Language data reloaded")