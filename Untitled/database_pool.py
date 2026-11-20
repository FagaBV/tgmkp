import sqlite3
import threading
import logging
import time
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class DatabasePool:
    """SQLite connection pool to reduce connection overhead"""
    
    def __init__(self, db_path='shop_bot.db', pool_size=10, max_overflow=20):
        self.db_path = db_path
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool = []
        self.overflow = []
        self.lock = threading.RLock()
        self.checked_out = set()
        
        # Initialize the pool
        self._initialize_pool()
    
    def _initialize_pool(self):
        """Initialize the connection pool"""
        try:
            for _ in range(self.pool_size):
                conn = self._create_connection()
                if conn:
                    self.pool.append(conn)
            logger.info(f"Database pool initialized with {len(self.pool)} connections")
        except Exception as e:
            logger.error(f"Error initializing database pool: {e}")
    
    def _create_connection(self):
        """Create a new SQLite connection with optimizations"""
        try:
            conn = sqlite3.connect(
                self.db_path, 
                check_same_thread=False,  # Allow sharing between threads
                timeout=30.0,  # 30 second timeout
                isolation_level=None  # Autocommit mode for better performance
            )
            
            # Apply SQLite optimizations
            conn.execute('PRAGMA journal_mode=WAL')  # Better concurrency
            conn.execute('PRAGMA synchronous=NORMAL')  # Faster writes
            conn.execute('PRAGMA cache_size=10000')  # Larger cache
            conn.execute('PRAGMA temp_store=memory')  # Use memory for temp tables
            conn.execute('PRAGMA busy_timeout=30000')  # 30 second busy timeout
            
            return conn
        except Exception as e:
            logger.error(f"Error creating database connection: {e}")
            return None
    
    @contextmanager
    def get_connection(self):
        """Get a connection from the pool (context manager)"""
        conn = None
        try:
            conn = self._checkout_connection()
            yield conn
        finally:
            if conn:
                self._checkin_connection(conn)
    
    def _checkout_connection(self):
        """Check out a connection from the pool with validation"""
        with self.lock:
            # Try to get from main pool first
            if self.pool:
                conn = self.pool.pop()
                
                # Quick validation - if connection is dead, create a new one
                if not self._quick_validate(conn):
                    logger.warning("🔄 Dead connection detected, creating new one")
                    try:
                        conn.close()
                    except:
                        pass
                    conn = self._create_connection()
                    if not conn:
                        # If we can't create a connection, try another from pool
                        if self.pool:
                            conn = self.pool.pop()
                
                if conn:
                    self.checked_out.add(id(conn))
                    return conn
            
            # Try overflow if main pool is empty
            if len(self.overflow) < self.max_overflow:
                conn = self._create_connection()
                if conn:
                    self.overflow.append(conn)
                    self.checked_out.add(id(conn))
                    return conn
            
            # If we reach here, all connections are busy
            # Create a temporary connection (not pooled)
            logger.warning("All connections busy, creating temporary connection")
            return self._create_connection()
    
    def _checkin_connection(self, conn):
        """Check in a connection back to the pool"""
        if not conn:
            return
            
        with self.lock:
            conn_id = id(conn)
            
            # Remove from checked out set
            self.checked_out.discard(conn_id)
            
            # Put back in main pool if there's space
            if len(self.pool) < self.pool_size:
                self.pool.append(conn)
            # Otherwise put in overflow
            elif conn in self.overflow:
                # Keep it in overflow
                pass
            else:
                # Close excess connections
                try:
                    conn.close()
                except:
                    pass
    
    def close_all(self):
        """Close all connections in the pool"""
        with self.lock:
            # Close main pool connections
            for conn in self.pool:
                try:
                    conn.close()
                except:
                    pass
            self.pool.clear()
            
            # Close overflow connections
            for conn in self.overflow:
                try:
                    conn.close()
                except:
                    pass
            self.overflow.clear()
            
            self.checked_out.clear()
            logger.info("All database connections closed")
    
    def _quick_validate(self, conn):
        """Quick connection validation without throwing exceptions"""
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT 1')
            cursor.fetchone()
            return True
        except:
            return False
    
    def get_stats(self):
        """Get pool statistics"""
        with self.lock:
            return {
                'pool_size': len(self.pool),
                'overflow_size': len(self.overflow),
                'checked_out': len(self.checked_out),
                'total_available': len(self.pool) + len(self.overflow) - len(self.checked_out)
            }
