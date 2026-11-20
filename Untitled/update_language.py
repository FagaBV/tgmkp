#!/usr/bin/env python3
"""
Update language.py to use smart cache management
"""

# Read current language.py
with open('language.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add import if not present
if 'from cache_manager import get_json_cached' not in content:
    # Find the imports section and add our import
    import_lines = []
    other_lines = []
    in_imports = True
    
    for line in content.split('\n'):
        if line.strip().startswith(('import ', 'from ')) and in_imports:
            import_lines.append(line)
        else:
            if in_imports and line.strip() and not line.strip().startswith('#'):
                in_imports = False
            other_lines.append(line)
    
    # Add our import
    import_lines.append('from cache_manager import get_json_cached')
    
    # Reconstruct content
    content = '\n'.join(import_lines) + '\n' + '\n'.join(other_lines)

# Replace json_cache.get with get_json_cached
content = content.replace('json_cache.get(self.language_file)', 'get_json_cached(self.language_file)')

# Write back
with open('language.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Updated language.py to use smart cache management")
print("✅ Language system now automatically detects file changes")
