import threading
import time
import logging
import sqlite3

logger = logging.getLogger(__name__)

class HeartbeatHandler:
    """High-frequency heartbeat to keep bot always warm and responsive"""
    
    def __init__(self, db, bot=None, interval=15):  # Every 15 seconds - more frequent
        self.db = db
        self.bot = bot
        self.interval = interval
        self.running = False
        self.heartbeat_thread = None
        self.last_heartbeat = time.time()
        self.pulse_count = 0
        self.failed_pulses = 0
        
        # Connection recovery settings
        self.max_failed_attempts = 3
        self.recovery_delay = 5  # seconds
    
    def start_heartbeat(self):
        """Start the high-frequency heartbeat service"""
        if not self.running:
            self.running = True
            self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self.heartbeat_thread.start()
            logger.info(f"🫀 High-frequency heartbeat started - pulse every {self.interval} seconds")
    
    def stop_heartbeat(self):
        """Stop the heartbeat service"""
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
        logger.info("💤 Heartbeat service stopped")
    
    def _heartbeat_loop(self):
        """Main heartbeat loop - keeps everything warm with frequent pulses"""
        consecutive_failures = 0
        
        while self.running:
            try:
                pulse_success = self._pulse()
                
                if pulse_success:
                    consecutive_failures = 0
                    time.sleep(self.interval)
                else:
                    consecutive_failures += 1
                    self.failed_pulses += 1
                    
                    # If multiple failures, try recovery
                    if consecutive_failures >= self.max_failed_attempts:
                        logger.warning(f"🚨 {consecutive_failures} consecutive heartbeat failures, attempting recovery...")
                        self._attempt_recovery()
                        consecutive_failures = 0
                        time.sleep(self.recovery_delay)
                    else:
                        time.sleep(2)  # Short delay before retry
                        
            except Exception as e:
                logger.error(f"💔 Heartbeat loop error: {e}")
                time.sleep(10)  # Wait before retrying
    
    def _pulse(self):
        """Single heartbeat pulse - multiple lightweight operations"""
        try:
            current_time = time.time()
            pulse_success = True
            
            # 1. Database pulse - most critical
            if not self._db_pulse():
                pulse_success = False
            
            # 2. API pulse - keep Telegram API connection warm (every 3rd pulse to avoid spam)
            if self.pulse_count % 3 == 0:  # Every ~45 seconds
                if not self._api_pulse():
                    pulse_success = False
            
            # 3. Memory pulse - keep Python objects warm
            self._memory_pulse()
            
            # 4. Thread pulse - keep thread pool active
            self._thread_pulse()
            
            # 5. Update heartbeat metrics
            if pulse_success:
                self.last_heartbeat = current_time
                self.pulse_count += 1
                
                # Log heartbeat every 5 minutes to avoid spam
                if self.pulse_count % (300 // self.interval) == 0:  # Every ~5 minutes
                    logger.info(f"💓 Heartbeat alive - {self.pulse_count} pulses, {self.failed_pulses} failures")
            
            return pulse_success
                
        except Exception as e:
            logger.warning(f"💔 Heartbeat pulse failed: {e}")
            return False
    
    def _db_pulse(self):
        """Frequent database operation to keep connections warm"""
        try:
            # Multiple lightweight queries to keep different parts warm
            with self.db.pool.get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. Simple count query
                cursor.execute('SELECT COUNT(*) FROM users LIMIT 1')
                cursor.fetchone()
                
                # 2. Check if connection is truly alive with a write operation
                cursor.execute('PRAGMA quick_check')
                cursor.fetchone()
                
                return True
                
        except Exception as e:
            logger.warning(f"🗄️ Database pulse failed: {e}")
            return False
    
    def _api_pulse(self):
        """Keep Telegram API connection warm with lightweight ping"""
        try:
            if self.bot and hasattr(self.bot, 'keep_api_warm'):
                success = self.bot.keep_api_warm()
                if success:
                    logger.debug("🏓 API connection kept warm")
                    return True
                else:
                    logger.warning("⚠️ API warm-up failed")
                    return False
            return True  # If no API warming available, don't fail the pulse
            
        except Exception as e:
            logger.warning(f"🔌 API pulse failed: {e}")
            return False
    
    def _memory_pulse(self):
        """Keep Python objects and caches warm"""
        try:
            # Touch some cached objects to prevent garbage collection
            if hasattr(self.db, 'user_manager'):
                # Just access the object to keep it warm
                _ = self.db.user_manager
            
            # Keep performance cache warm
            if hasattr(self.db, 'pool'):
                stats = self.db.pool.get_stats()
                
        except Exception as e:
            logger.debug(f"🧠 Memory pulse warning: {e}")
    
    def _thread_pulse(self):
        """Keep thread pools active"""
        try:
            # If bot is available, do a tiny operation
            if self.bot:
                # Just access bot properties to keep it warm
                _ = self.bot.token  # This doesn't make API calls
                
        except Exception as e:
            logger.debug(f"🧵 Thread pulse warning: {e}")
    
    def _attempt_recovery(self):
        """Attempt to recover from connection failures"""
        try:
            logger.info("🔄 Attempting heartbeat recovery...")
            
            # 1. Try to reinitialize database pool
            if hasattr(self.db, 'pool') and hasattr(self.db.pool, '_initialize_pool'):
                self.db.pool._initialize_pool()
                logger.info("✅ Database pool reinitialized")
            
            # 2. Clear any stale caches
            try:
                from performance_optimizations import clear_cache
                clear_cache()
                logger.info("✅ Performance cache cleared")
            except ImportError:
                pass
            
            # 3. Test recovery with a simple operation
            test_success = self._db_pulse()
            if test_success:
                logger.info("✅ Heartbeat recovery successful")
            else:
                logger.warning("⚠️ Heartbeat recovery may have failed")
                
        except Exception as e:
            logger.error(f"🚨 Heartbeat recovery failed: {e}")
    
    def is_alive(self):
        """Check if heartbeat is running and recent"""
        if not self.running:
            return False
        
        # Consider alive if last heartbeat was within 3x interval
        time_since_last = time.time() - self.last_heartbeat
        return time_since_last < (self.interval * 3)
    
    def get_health_status(self):
        """Get detailed health status"""
        current_time = time.time()
        time_since_last = current_time - self.last_heartbeat
        
        # Determine health status
        if not self.running:
            status = "STOPPED"
        elif time_since_last < self.interval * 2:
            status = "HEALTHY"
        elif time_since_last < self.interval * 5:
            status = "WARNING"
        else:
            status = "CRITICAL"
        
        return {
            'status': status,
            'running': self.running,
            'pulse_count': self.pulse_count,
            'failed_pulses': self.failed_pulses,
            'success_rate': (self.pulse_count / max(self.pulse_count + self.failed_pulses, 1)) * 100,
            'last_heartbeat': self.last_heartbeat,
            'seconds_since_last': time_since_last,
            'interval': self.interval,
            'is_alive': self.is_alive()
        }
    
    def get_stats(self):
        """Get heartbeat statistics (legacy method)"""
        return self.get_health_status()
