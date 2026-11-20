import sqlite3
import logging
import json
import os

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='shop_bot.db'):
        self.db_path = db_path
        # Enable WAL mode and optimize SQLite for better performance
        self._optimize_sqlite()
        self.init_database()
    
    def _optimize_sqlite(self):
        """Optimize SQLite for better performance"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('PRAGMA journal_mode=WAL')  # Better concurrency
                conn.execute('PRAGMA synchronous=NORMAL')  # Faster writes
                conn.execute('PRAGMA cache_size=10000')  # Larger cache
                conn.execute('PRAGMA temp_store=memory')  # Use memory for temp tables
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not optimize SQLite: {e}")
    
    def init_database(self):
        """Initialize database and create tables if they don't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Create users table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        username TEXT,
                        first_name TEXT,
                        last_name TEXT,
                        language_code TEXT DEFAULT 'en',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create categories table (for future use)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS categories (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Create products table (for future use)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS products (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        description TEXT,
                        price REAL NOT NULL,
                        category_id INTEGER,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (category_id) REFERENCES categories (id)
                    )
                ''')
                
                # Create user states table for input handling
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_states (
                        user_id INTEGER PRIMARY KEY,
                        state TEXT,
                        data TEXT,
                        message_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create orders table for shopping cart and orders
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS orders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        products TEXT NOT NULL,
                        total_cost REAL DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        deadline TIMESTAMP NOT NULL,
                        delivery_address TEXT,
                        payment_track_id TEXT,
                        payment_url TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create delivery_queue table for deliverable products awaiting delivery
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS delivery_queue (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        products TEXT NOT NULL,
                        total_cost REAL NOT NULL,
                        delivery_address TEXT NOT NULL,
                        payment_track_id TEXT,
                        status TEXT DEFAULT 'awaiting_delivery',
                        order_date TIMESTAMP NOT NULL,
                        payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        delivered_date TIMESTAMP,
                        review TEXT DEFAULT 'pending',
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create selling_history table for completed orders
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS selling_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        original_order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        products TEXT NOT NULL,
                        total_cost REAL NOT NULL,
                        delivery_address TEXT,
                        payment_track_id TEXT,
                        review TEXT DEFAULT 'pending',
                        order_date TIMESTAMP NOT NULL,
                        completed_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Create reviews table for storing detailed reviews
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        product_ids TEXT NOT NULL,
                        products TEXT NOT NULL,
                        star_rating INTEGER NOT NULL CHECK(star_rating >= 1 AND star_rating <= 5),
                        review_text TEXT,
                        order_type TEXT NOT NULL,
                        review_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES users (user_id)
                    )
                ''')
                
                # Add review column to existing tables if they don't have it
                try:
                    cursor.execute("ALTER TABLE selling_history ADD COLUMN review TEXT DEFAULT 'pending'")
                    logger.info("Added review column to selling_history table")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass
                
                try:
                    cursor.execute("ALTER TABLE delivery_queue ADD COLUMN review TEXT DEFAULT 'pending'")
                    logger.info("Added review column to delivery_queue table")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass
                
                conn.commit()
                logger.info("Database initialized successfully")
                
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
    
    def get_user(self, user_id):
        """Get user by user_id"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
                user = cursor.fetchone()
                
                if user:
                    return {
                        'id': user[0],
                        'user_id': user[1],
                        'username': user[2],
                        'first_name': user[3],
                        'last_name': user[4],
                        'language_code': user[5],
                        'created_at': user[6],
                        'updated_at': user[7]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting user: {e}")
            return None
    
    def create_user(self, user_id, username=None, first_name=None, last_name=None, language_code='en'):
        """Create a new user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (user_id, username, first_name, last_name, language_code)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, username, first_name, last_name, language_code))
                conn.commit()
                logger.info(f"User {user_id} created successfully")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error creating user: {e}")
            return False
    
    def update_user_language(self, user_id, language_code):
        """Update user's language preference"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users 
                    SET language_code = ?, updated_at = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (language_code, user_id))
                conn.commit()
                logger.info(f"User {user_id} language updated to {language_code}")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error updating user language: {e}")
            return False
    
    def is_admin(self, user_id, admin_ids):
        """Check if user is admin"""
        return user_id in admin_ids
    
    def set_user_state(self, user_id, state, data=None, message_id=None):
        """Set user's current state for input handling"""
        try:
            # Serialize data as JSON if it's a dict
            serialized_data = json.dumps(data) if isinstance(data, dict) else data
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO user_states (user_id, state, data, message_id)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, state, serialized_data, message_id))
                conn.commit()
                logger.info(f"User {user_id} state set to {state}")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error setting user state: {e}")
            return False
    
    def get_user_state(self, user_id):
        """Get user's current state"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT state, data, message_id FROM user_states WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                
                if result:
                    # Deserialize data if it's JSON
                    data = result[1]
                    if isinstance(data, str) and data.startswith('{'):
                        try:
                            data = json.loads(data)
                        except json.JSONDecodeError:
                            pass  # Keep as string if JSON parsing fails
                    
                    return {
                        'state': result[0],
                        'data': data,
                        'message_id': result[2]
                    }
                return None
        except sqlite3.Error as e:
            logger.error(f"Error getting user state: {e}")
            return None
    
    def clear_user_state(self, user_id):
        """Clear user's state"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_states WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.info(f"User {user_id} state cleared")
                return True
        except sqlite3.Error as e:
            logger.error(f"Error clearing user state: {e}")
            return False
