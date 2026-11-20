#!/usr/bin/env python3

import re

# Read the payment handler file
with open('handlers/payment_handler.py', 'r') as f:
    content = f.read()

# Fix 1: Scientific notation issue - improve amount formatting
old_amount_format = '''            # Format amount properly
            try:
                pay_amount_float = float(pay_amount)
                if pay_amount_float < 0.001:
                    formatted_amount = f"{pay_amount_float:.8f}".rstrip('0').rstrip('.')
                elif pay_amount_float < 1:
                    formatted_amount = f"{pay_amount_float:.6f}".rstrip('0').rstrip('.')
                else:
                    formatted_amount = f"{pay_amount_float:.4f}".rstrip('0').rstrip('.')
            except:
                formatted_amount = pay_amount'''

new_amount_format = '''            # Format amount properly (force full decimal display, no scientific notation)
            try:
                pay_amount_float = float(pay_amount)
                # Use format with enough decimal places to avoid scientific notation
                formatted_amount = f"{pay_amount_float:.12f}".rstrip('0').rstrip('.')
                # Ensure we don't get empty string
                if not formatted_amount or formatted_amount == '':
                    formatted_amount = str(pay_amount_float)
            except:
                formatted_amount = str(pay_amount)'''

# Replace the amount formatting code
content = content.replace(old_amount_format, new_amount_format)

# Fix 2: Message too long issue - shorten the callback messages
old_pending_message = '''            # Payment pending with network delay message
            pending_message = f"{self.language.get_text('payment_verification_progress', lang_code)}\\n\\n"
            pending_message += f"{self.language.get_text('blockchain_delay_message', lang_code)}\\n\\n"
            pending_message += f"{self.language.get_text('exact_amount_reminder', lang_code)}"
            self.bot.answer_callback_query(call.id, pending_message, show_alert=True)'''

new_pending_message = '''            # Payment pending with network delay message (shortened for callback)
            pending_message = f"⏳ Payment verification in progress...\\n\\n🌐 Networks can take time to confirm.\\nIf paid, please wait and try again."
            self.bot.answer_callback_query(call.id, pending_message, show_alert=True)'''

old_failed_message = '''            # Payment failed or not found
            failed_message = f"{self.language.get_text('payment_not_detected', lang_code)}\\n\\n"
            failed_message += f"{self.language.get_text('payment_verification_instructions', lang_code)}\\n\\n"
            failed_message += f"{self.language.get_text('network_confirmation_time', lang_code)}"
            self.bot.answer_callback_query(call.id, failed_message, show_alert=True)'''

new_failed_message = '''            # Payment failed or not found (shortened for callback)
            failed_message = f"❌ Payment not detected yet.\\n\\nEnsure you sent exact amount to correct address.\\n🕐 Wait 5-15 minutes for confirmation."
            self.bot.answer_callback_query(call.id, failed_message, show_alert=True)'''

# Replace both occurrences of the message patterns
content = content.replace(old_pending_message, new_pending_message)
content = content.replace(old_failed_message, new_failed_message)

# Also fix the same formatting issue in the main payment display
old_main_format = '''        # Format amount properly (avoid scientific notation)
        pay_amount = payment_result['pay_amount']
        if isinstance(pay_amount, float):
            # Format with appropriate precision to avoid scientific notation
            if pay_amount < 0.001:
                formatted_amount = f"{pay_amount:.8f}".rstrip('0').rstrip('.')
            elif pay_amount < 1:
                formatted_amount = f"{pay_amount:.6f}".rstrip('0').rstrip('.')
            else:
                formatted_amount = f"{pay_amount:.4f}".rstrip('0').rstrip('.')
        else:
            formatted_amount = str(pay_amount)'''

new_main_format = '''        # Format amount properly (force full decimal display, no scientific notation)
        pay_amount = payment_result['pay_amount']
        if isinstance(pay_amount, float):
            # Use format with enough decimal places to avoid scientific notation
            formatted_amount = f"{pay_amount:.12f}".rstrip('0').rstrip('.')
            # Ensure we don't get empty string
            if not formatted_amount or formatted_amount == '':
                formatted_amount = str(pay_amount)
        else:
            formatted_amount = str(pay_amount)'''

content = content.replace(old_main_format, new_main_format)

# Write the fixed content back
with open('handlers/payment_handler.py', 'w') as f:
    f.write(content)

print("✅ Fixed both issues:")
print("1. Amount formatting - no more scientific notation")
print("2. Shortened callback messages to avoid MESSAGE_TOO_LONG error")
