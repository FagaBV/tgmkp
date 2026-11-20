import telebot
import logging
import json
import requests
import time
import threading
from datetime import datetime
from cache_manager import save_json_safely


def replace_message(bot, call):

    try:

        bot.delete_message(
            call.message.chat.id,
            call.message.message_id
        )

    except:
        pass