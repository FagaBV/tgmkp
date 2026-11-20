# 🛒 OutlawMan's Shopbot Project

A comprehensive Telegram bot for e-commerce with cryptocurrency payments, multi-language support, and advanced order management.

## 📁 Project Structure

cd /root/obp/otmen_bot/source_code
source venv/bin/activate
python3 -m py_compile handlers/menu_handler.py handlers/admin_handler.py handlers/shopping_handler.py handlers/cart_handler.py handlers/reviews_handler.py handlers/dispute_handler.py handlers/history_handler.py handlers/topup_handler.py

```
shopbot1/
├── 📄 main.py                          # Main bot application entry point
├── 📄 requirements.txt                 # Python dependencies
├── 📄 config.json                      # Bot configuration (tokens, admin IDs, etc.)
├── 📄 language.json                    # Multi-language translations (EN/ES)
├── 📄 ecosystem.config.js              # PM2 configuration for process management
├── 📄 manage.sh                        # Management script for bot operations
│
├── 🗃️ Database Files
│   ├── database.py                     # Main database handler
│   ├── database_pool.py                # Database connection pooling
│   ├── shop_bot.db                     # SQLite database file
│   ├── shop_bot.db-shm                 # SQLite shared memory
│   └── shop_bot.db-wal                 # SQLite write-ahead log
│
├── 🛠️ Core Components
│   ├── cache_manager.py                # JSON file caching system
│   ├── json_cache.py                   # JSON cache implementation
│   ├── language.py                     # Language management system
│   ├── user_manager.py                 # User management utilities
│   └── heartbeat_handler.py            # Bot health monitoring
│
├── 📊 Data Files
│   ├── products.json                   # Product catalog data
│   ├── categories.json                 # Product categories
│   └── currencies.json                 # Supported cryptocurrency data
│
├── 📁 handlers/                        # Bot command and callback handlers
│   ├── __init__.py                     # Package initialization
│   ├── admin_handler.py                # Admin panel functionality
│   ├── admin_command_handler.py        # Admin commands management
│   ├── cart_handler.py                 # Shopping cart operations
│   ├── category_handler.py             # Product category management
│   ├── cleanup_handler.py              # Database cleanup tasks
│   ├── currency_handler.py             # Cryptocurrency handling
│   ├── file_serving_handler.py         # Digital product file delivery
│   ├── history_handler.py              # Order history management
│   ├── menu_handler.py                 # Main menu navigation
│   ├── order_management_handler.py     # Order processing
│   ├── payment_handler.py              # Payment processing (OxaPay integration)
│   ├── product_creation_handler.py     # Product creation workflow
│   ├── product_file_handler.py         # Product file management
│   ├── product_handler.py              # Product display and management
│   ├── review_handler.py               # Product review system
│   ├── shopping_handler.py             # Shopping and browsing
│   └── start_handler.py                # Bot startup and user onboarding
│
├── 📁 images/                          # Product images and media files
├── 📁 products/                        # Digital product files for delivery
├── 📁 logs/                            # Application log files
├── 📁 venv/                            # Python virtual environment
└── 📁 __pycache__/                     # Python bytecode cache
```

## 🚀 Setup Instructions

### 1. Server Access & Initial Setup

```bash
# Connect to your server via SSH
ssh root@YOUR_SERVER_IP

# Enter your password when prompted
# (Change root password from hosting provider if needed)

# Navigate to the project directory
cd /root/shopbot1
```

### 2. Configuration Setup

#### Edit Bot Configuration
```bash
# Open config.json with your preferred editor
nano config.json
# or
vim config.json
```

**Required Configuration Changes:**
```json
{
    "bot_token": "YOUR_BOT_TOKEN_FROM_BOTFATHER",
    "admin_ids": [
        YOUR_TELEGRAM_USER_ID,
        ADDITIONAL_ADMIN_ID
    ],
    "oxapay_api_key": "YOUR_OXAPAY_API_KEY",
    "admin_chat_link": "@your_support_username"
}
```

**How to get required values:**
- **Bot Token**: Create a bot with [@BotFather](https://t.me/botfather) on Telegram
- **Admin IDs**: Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot)
- **OxaPay API Key**: Register at [OxaPay](https://oxapay.com) and get your API key

### 3. Python Environment Setup

#### Install Python and Virtual Environment
```bash
# Update system packages
apt update && apt upgrade -y

# Install Python 3 and pip
apt install python3 python3-pip python3-venv -y

# Verify Python installation
python3 --version
```

#### Create and Activate Virtual Environment
```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install required packages
pip install -r requirements.txt
```

### 4. Database Setup

The bot automatically creates and initializes the SQLite database on first run. No manual database setup required.

### 5. Running the Bot

#### Option A: Direct Execution (for testing)
```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the bot
python3 main.py
```

#### Option B: Using tmux (Recommended)
```bash
# Install tmux if not installed
apt install tmux -y

# Create a new tmux session
tmux new-session -d -s shopbot

# Attach to the session
tmux attach-session -t shopbot

# Inside tmux session:
cd /root/shopbot1
source venv/bin/activate
python3 main.py

# Detach from tmux: Ctrl+B, then D
# Reattach later: tmux attach-session -t shopbot
```

#### Option C: Using PM2 (Production Recommended)
```bash
# Install Node.js and PM2
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
apt-get install -y nodejs
npm install -g pm2

# Start bot with PM2
pm2 start ecosystem.config.js

# Useful PM2 commands:
pm2 status          # Check bot status
pm2 logs shopbot     # View logs
pm2 restart shopbot  # Restart bot
pm2 stop shopbot     # Stop bot
pm2 save            # Save PM2 configuration
pm2 startup         # Auto-start on server reboot
```

## 🔧 Features

### 🛍️ E-commerce Features
- **Product Management**: Create, edit, and manage products with images
- **Category System**: Organize products in categories and subcategories
- **Shopping Cart**: Add/remove items, quantity management, empty cart
- **Order Processing**: Digital and physical product order workflows
- **Inventory Management**: Stock tracking and automatic updates

### 💳 Payment System
- **Cryptocurrency Payments**: Bitcoin, Ethereum, USDT, and more
- **OxaPay Integration**: Secure payment processing
- **Real-time Verification**: Automatic payment confirmation
- **Multiple Currencies**: Support for various cryptocurrencies

### 👥 User Management
- **Multi-language Support**: English and Spanish
- **User Profiles**: Order history and preferences
- **Admin Panel**: Comprehensive admin management tools
- **Review System**: Product ratings and reviews

### 🔐 Security & Administration
- **Admin Controls**: Product management, order fulfillment
- **Secure File Delivery**: Protected digital product downloads
- **Database Cleanup**: Automatic expired order cleanup
- **Logging System**: Comprehensive error and activity logging

## 📋 Configuration Options

### Bot Settings (`config.json`)
```json
{
    "bot_token": "Your Telegram bot token",
    "admin_ids": [123456789],
    "currency": {
        "code": "EUR",
        "symbol": "€",
        "flag": "🇪🇺"
    },
    "order_expiry_minutes": 180,
    "cleanup_interval_minutes": 5,
    "payment_testing_mode": false,
    "oxapay_api_key": "Your OxaPay API key",
    "oxapay_sandbox": false
}
```

### Language Support
- **English (en)**: Default language
- **Spanish (es)**: Full translation available
- **Extensible**: Easy to add more languages in `language.json`

## 🛠️ Maintenance

### Log Files
```bash
# View recent logs
tail -f bot.log

# View specific log files
ls logs/
```

### Database Backup
```bash
# Backup database
cp shop_bot.db shop_bot_backup_$(date +%Y%m%d).db
```

### Updates and Restart
```bash
# If using tmux
tmux attach-session -t shopbot
# Ctrl+C to stop, then restart with python3 main.py

# If using PM2
pm2 restart shopbot
```

## 🚨 Troubleshooting

### Common Issues

1. **Bot not responding**
   - Check bot token in `config.json`
   - Verify bot is running: `pm2 status` or check tmux session

2. **Payment issues**
   - Verify OxaPay API key
   - Check `oxapay_sandbox` setting
   - Review payment logs in `bot.log`

3. **Database errors**
   - Check database file permissions
   - Restart bot to reinitialize database

4. **File upload issues**
   - Check `images/` and `products/` directory permissions
   - Ensure sufficient disk space

### Support Commands
```bash
# Check bot status
pm2 status shopbot

# View logs
pm2 logs shopbot --lines 100

# Restart bot
pm2 restart shopbot

# Check system resources
htop
df -h
```

## 📞 Support

For technical support and additional information:
- Admin Contact: `@hbeire`;`@oreo47999` or `@droptianuu`
- Check logs for error details
- Ensure all configuration values are correct

## 📝 License

This project is proprietary software. All rights reserved.

---

**🎉 Your ShopBot is now ready to serve customers!**

The bot includes features like:
- ✅ Multi-language support (EN/ES)
- ✅ Cryptocurrency payments
- ✅ Product catalog management
- ✅ Order processing workflows
- ✅ Admin panel for management
- ✅ Automatic stock management
- ✅ Digital product delivery
- ✅ Review and rating system
- ✅ Empty cart functionality
- ✅ Comprehensive logging

Start the bot and begin selling! 🚀