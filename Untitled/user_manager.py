"""
Bulletproof user management system - no caching, no race conditions
"""
import sqlite3
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class UserManager:
    """Thread-safe user management with atomic operations"""
    
    def __init__(self, db_pool):
        self.db_pool = db_pool
    
    def get_or_ensure_user(self, user_id: int, username: str = None, 
                          first_name: str = None, last_name: str = None, 
                          language_code: str = 'en') -> Optional[Dict[str, Any]]:
        """
        ATOMIC operation: Get user if exists, create if not.
        This eliminates ALL race conditions and caching issues.
        """
        try:
            with self.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # Use a transaction for atomicity
                cursor.execute('BEGIN IMMEDIATE')
                
                try:
                    # First, try to get existing user
                    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                    user = cursor.fetchone()
                    
                    if user:
                        # User exists - return it
                        cursor.execute('COMMIT')
                        return {
                            'id': user[0],
                            'user_id': user[1],
                            'username': user[2],
                            'first_name': user[3],
                            'last_name': user[4],
                            'language_code': user[5],
                            'created_at': user[6],
                            'updated_at': user[7],
                            'is_new': False
                        }
                    else:
                        # User doesn't exist - create it
                        cursor.execute('''
                            INSERT INTO users (user_id, username, first_name, last_name, language_code)
                            VALUES (?, ?, ?, ?, ?)
                        ''', (user_id, username, first_name, last_name, language_code))
                        
                        # Get the created user
                        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                        new_user = cursor.fetchone()
                        
                        cursor.execute('COMMIT')
                        logger.info(f"Created new user: {user_id}")
                        
                        return {
                            'id': new_user[0],
                            'user_id': new_user[1],
                            'username': new_user[2],
                            'first_name': new_user[3],
                            'last_name': new_user[4],
                            'language_code': new_user[5],
                            'created_at': new_user[6],
                            'updated_at': new_user[7],
                            'is_new': True
                        }
                        
                except Exception as e:
                    cursor.execute('ROLLBACK')
                    raise e
                    
        except sqlite3.Error as e:
            logger.error(f"Database error in get_or_ensure_user: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in get_or_ensure_user: {e}")
            return None
    
    def update_user_language(self, user_id: int, language_code: str) -> bool:
        """Update user's language preference"""
        try:
            with self.db_pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET language_code = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (language_code, user_id))
                cursor.execute('COMMIT')
                
                if cursor.rowcount > 0:
                    logger.info(f"Updated language for user {user_id} to {language_code}")
                    return True
                else:
                    logger.warning(f"No user found to update language: {user_id}")
                    return False
                    
        except sqlite3.Error as e:
            logger.error(f"Error updating user language: {e}")
            return False
