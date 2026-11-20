#!/usr/bin/env python3
"""
Script to update all handlers to use smart cache management
"""
import os
import re

def update_json_writes(filepath):
    """Update a handler file to use smart cache management"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Add import for cache manager if not present
        if 'from cache_manager import save_json_safely' not in content:
            # Find existing imports and add our import
            import_pattern = r'(import [^\n]+\n|from [^\n]+ import [^\n]+\n)+'
            match = re.search(import_pattern, content)
            if match:
                imports_end = match.end()
                content = (content[:imports_end] + 
                          'from cache_manager import save_json_safely\n' +
                          content[imports_end:])
        
        # Pattern 1: Replace json.dump with save_json_safely for products.json
        pattern1 = r'with open\([\'"]products\.json[\'"], [\'"]w[\'"][^)]*\) as f:\s+json\.dump\(([^,]+), f[^)]*\)'
        replacement1 = r'save_json_safely("products.json", \1)'
        content = re.sub(pattern1, replacement1, content, flags=re.MULTILINE | re.DOTALL)
        
        # Pattern 2: Replace json.dump with save_json_safely for categories.json
        pattern2 = r'with open\([\'"]categories\.json[\'"], [\'"]w[\'"][^)]*\) as f:\s+json\.dump\(([^,]+), f[^)]*\)'
        replacement2 = r'save_json_safely("categories.json", \1)'
        content = re.sub(pattern2, replacement2, content, flags=re.MULTILINE | re.DOTALL)
        
        # Pattern 3: Replace json.dump with save_json_safely for language.json
        pattern3 = r'with open\([\'"]language\.json[\'"], [\'"]w[\'"][^)]*\) as f:\s+json\.dump\(([^,]+), f[^)]*\)'
        replacement3 = r'save_json_safely("language.json", \1)'
        content = re.sub(pattern3, replacement3, content, flags=re.MULTILINE | re.DOTALL)
        
        # Pattern 4: Replace json.dump with save_json_safely for config.json
        pattern4 = r'with open\([\'"]config\.json[\'"], [\'"]w[\'"][^)]*\) as f:\s+json\.dump\(([^,]+), f[^)]*\)'
        replacement4 = r'save_json_safely("config.json", \1)'
        content = re.sub(pattern4, replacement4, content, flags=re.MULTILINE | re.DOTALL)
        
        # Only write if content changed
        if content != original_content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ Updated: {filepath}")
            return True
        else:
            print(f"⚪ No changes needed: {filepath}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating {filepath}: {e}")
        return False

def main():
    """Update all handler files"""
    handlers_dir = 'handlers'
    
    if not os.path.exists(handlers_dir):
        print("❌ Handlers directory not found!")
        return
    
    print("🔧 Updating handlers for smart cache management...")
    
    updated_count = 0
    for filename in os.listdir(handlers_dir):
        if filename.endswith('.py') and filename != '__init__.py':
            filepath = os.path.join(handlers_dir, filename)
            if update_json_writes(filepath):
                updated_count += 1
    
    print(f"\\n🎉 Updated {updated_count} handler files!")
    print("\\n🚀 Smart cache management enabled!")
    print("\\n📝 Benefits:")
    print("   ✅ Automatic cache invalidation when JSON files change")
    print("   ✅ File modification time detection")
    print("   ✅ Speed maintained - only reload when actually changed")
    print("   ✅ No more stale data issues")

if __name__ == "__main__":
    main()
