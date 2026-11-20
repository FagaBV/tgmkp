module.exports = {
  apps: [{
    name: 'shopbot',
    script: '/root/shopbot/hits/bin/python',
    args: '/root/shopbot/main.py',
    cwd: '/root/shopbot',
    instances: 1,
    exec_mode: 'fork',
    
    // Auto restart configuration
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    
    // Error handling
    restart_delay: 4000,
    max_restarts: 10,
    min_uptime: '10s',
    
    // Environment variables
    env: {
      NODE_ENV: 'production',
      PYTHONPATH: '/root/shopbot',
      PYTHONUNBUFFERED: '1'
    },
    
    // Logging configuration
    log_file: '/root/shopbot/logs/combined.log',
    out_file: '/root/shopbot/logs/out.log',
    error_file: '/root/shopbot/logs/error.log',
    log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    merge_logs: true,
    
    // Process management
    kill_timeout: 5000,
    listen_timeout: 3000,
    
    // Health monitoring
    health_check_grace_period: 3000
  }]
};
