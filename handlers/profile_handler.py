import sqlite3
import telebot
from utils import replace_message

class ProfileHandler:

    def __init__(self, bot, db, config, language):
        self.bot = bot
        self.db = db
        self.config = config
        self.language = language

    def calculate_trust_score(
        self,
        total_orders,
        total_reviews,
        total_disputes,
        warnings
    ):

        score = 0

        # +0.75 pentru fiecare comandă
        score += total_orders * 0.75

        # +0.75 pentru fiecare review
        score += total_reviews * 0.75

        # -1.0 pentru fiecare dispută
        score -= total_disputes * 1.0

        # -20 pentru fiecare warning
        score -= warnings * 20

        if score < 0:
            score = 0

        if score > 100:
            score = 100

        return round(score, 1)

    def show_profile(self, call):

        try:

            user_id = call.from_user.id

            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            # balance + warnings
            cursor.execute(
                """
                SELECT balance, warnings
                FROM users
                WHERE user_id = ?
                """,
                (user_id,)
            )

            row = cursor.fetchone()

            balance = 0
            warnings = 0

            if row:
                balance = float(row[0] or 0)
                warnings = int(row[1] or 0)

            # total orders
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM selling_history
                WHERE user_id = ?
                """,
                (user_id,)
            )

            orders_row = cursor.fetchone()

            total_orders = 0

            if orders_row:
                total_orders = int(orders_row[0])

            # total reviews
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM reviews
                WHERE user_id = ?
                """,
                (user_id,)
            )

            reviews_row = cursor.fetchone()

            total_reviews = 0

            if reviews_row:
                total_reviews = int(reviews_row[0])

            # total disputes
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM disputes
                WHERE user_id = ?
                """,
                (user_id,)
            )

            disputes_row = cursor.fetchone()

            total_disputes = 0

            if disputes_row:
                total_disputes = int(disputes_row[0])

            conn.close()

            trust_score = self.calculate_trust_score(
                total_orders,
                total_reviews,
                total_disputes,
                warnings
            )

            text = (
                "👤 <b>Profil</b>\n\n"

                f"🆔 <b>ID:</b> {user_id}\n"
                f"💰 <b>Balanță:</b> {balance:.2f} RON\n\n"

                f"📦 <b>Comenzi:</b> {total_orders}\n"
                f"🆘 <b>Tichete deschise:</b> {total_disputes}\n\n"

                f"📈 <b>Scor de Încredere:</b> {trust_score}%\n"
                f"⚠️ <b>Avertismente:</b> {warnings}/3"
            )

            markup = telebot.types.InlineKeyboardMarkup()

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="📋 Istoric Comenzi",
                    callback_data="menu_history"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="🆘 Tichetele Mele",
                    callback_data="menu_disputes"
                )
            )

            markup.row(
                telebot.types.InlineKeyboardButton(
                    text="🔙 Înapoi",
                    callback_data="main_menu"
                )
            )

            
            self.bot.send_message(
                chat_id=call.message.chat.id,
                text=text,
                reply_markup=markup,
                parse_mode='HTML'
            )

        except Exception as e:

            print(f"PROFILE ERROR: {e}")

            self.bot.answer_callback_query(
                call.id,
                "❌ Eroare profil"
            )