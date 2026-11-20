#!/usr/bin/env python3
"""
Script to fix all handlers to use the bulletproof user system
"""
import os
import re

def fix_handler_file(filepath):
    """Fix a handler file to use bulletproof user management"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Pattern 1: Replace get_user() calls with get_or_create_user()
        pattern1 = r'user = self\.db\.get_user\(user_id\)'
        replacement1 = 'user = self.db.get_or_create_user(user_id)'
        content = re.sub(pattern1, replacement1, content)
        
        # Pattern 2: Replace "Please use /start command first" with proper handling
        pattern2 = r'self\.bot\.answer_callback_query\(call\.id, "Please use /start command first"\)'
        replacement2 = 'self.bot.answer_callback_query(call.id, "❌ Database error. Please try again.")'
        content = re.sub(pattern2, replacement2, content)
        
        # Pattern 3: Replace similar patterns in send_message
        pattern3 = r'self\.bot\.send_message\(message\.chat\.id, "Please use /start command first"\)'
        replacement3 = 'self.bot.send_message(message.chat.id, "❌ Database error. Please try again.")'
        content = re.sub(pattern3, replacement3, content)
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"✅ Fixed: {filepath}")
        return True
        
    except Exception as e:
        print(f"❌ Error fixing {filepath}: {e}")
        return False

def main():
    """Fix all handler files"""
    handlers_dir = 'handlers'
    
    if not os.path.exists(handlers_dir):
        print("❌ Handlers directory not found!")
        return
    
    print("🔧 Fixing all handler files...")
    
    fixed_count = 0
    for filename in os.listdir(handlers_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(handlers_dir, filename)
            if fix_handler_file(filepath):
                fixed_count += 1
    
    print(f"\\n🎉 Fixed {fixed_count} handler files!")
    print("\\n🚀 All handlers now use bulletproof user management!")

if __name__ == "__main__":
    main()
