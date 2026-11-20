import telebot
import json

with open("config.json", "r") as f:
    config = json.load(f)

TOKEN = config["bot_token"]

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    file_id = message.photo[-1].file_id

    print("\nNEW FILE ID:")
    print(file_id)

    bot.reply_to(
        message,
        f"File ID:\n{file_id}"
    )

print("Trimite poza catre bot...")
bot.infinity_polling()
