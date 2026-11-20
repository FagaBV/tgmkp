import sqlite3
import telebot
import logging
import requests
import json
import threading
import time
from shkeeper_client import SHKeeperClient

logger = logging.getLogger(__name__)


class SellerHandler:

    def __init__(
        self,
        bot,
        db,
        language,
        config
    ):

        self.bot = bot
        self.db = db
        self.language = language
        self.config = config
        self.shkeeper = SHKeeperClient(config)
        self.cashout_checker_running = False
        self.cashout_checker_thread = None

        if not self.config.get('_private_instance', False):
            self.start_cashout_checker()
                
    def handle_callback(self, call):

        data = call.data

        if data == "seller_statistics":
            return self.show_statistics(call)

        elif data == "seller_cashout":
            return self.show_cashout(call)
            
        elif data == "seller_cashout_crypto":
            self.start_crypto_cashout(call)

        elif data == "seller_cashout_cash":
            return self.start_cash_cashout(call)
            
        elif data == "seller_cashout_confirm":
            return self.confirm_cashout(call)    
            
        elif data == "seller_cashout_crypto_confirm":
            return self.confirm_crypto_cashout(call)
        
        return False
    
    def handle_text_input(self, message):

        state = self.db.get_user_state(
            message.from_user.id
        )

        if not state:
            return False

        if state["state"] == "seller_cashout_amount":
            return self.handle_amount_input(message)
            
        if state["state"] == "seller_cashout_ltc_address":
            return self.handle_ltc_address_input(message)
            
        if state["state"] == "seller_cashout_crypto_amount":
            return self.handle_crypto_amount_input(message)

        return False
    
    def show_statistics(
        self,
        call
    ):

        user_id = call.from_user.id

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        # =========================
        # Vânzări luna curentă
        # =========================

        cursor.execute("""
            SELECT
            COALESCE(SUM(amount),0)
            FROM wallet_transactions
            WHERE user_id=?
            AND type='SELLER_SALE'
            AND strftime('%Y-%m',created_at)=strftime('%Y-%m','now')
        """,(user_id,))

        month_income = float(
            cursor.fetchone()[0]
        )

        # =========================
        # Vânzări anul curent
        # =========================

        cursor.execute("""
            SELECT
            COALESCE(SUM(amount),0)
            FROM wallet_transactions
            WHERE user_id=?
            AND type='SELLER_SALE'
            AND strftime('%Y',created_at)=strftime('%Y','now')
        """,(user_id,))

        year_income = float(
            cursor.fetchone()[0]
        )

        # =========================
        # Rating magazin
        # =========================

        seller_product_prefix = f"%seller_prod_{user_id}_%"

        cursor.execute("""
            SELECT
                COALESCE(AVG(star_rating),0),
                COUNT(*)
            FROM reviews
            WHERE product_ids LIKE ?
        """,(seller_product_prefix,))

        row = cursor.fetchone()

        rating = float(row[0] or 0)
        reviews_count = int(row[1] or 0)

        conn.close()

        text = f"""
    🏪 <b>Statistici Magazin</b>

    💰 <b>Vânzări luna aceasta</b>

    {month_income:.2f} RON

    📅 <b>Vânzări anul acesta</b>

    {year_income:.2f} RON

    ⭐ <b>Rating magazin</b>

    {rating:.2f} / 5
    ({reviews_count} review-uri)
    """

        markup = telebot.types.InlineKeyboardMarkup()

        markup.add(
            telebot.types.InlineKeyboardButton(
                "🔙 Înapoi",
                callback_data="menu_edit_seller_shop"
            )
        )

        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

        self.bot.answer_callback_query(call.id)
    
    def show_cashout(
        self,
        call
    ):

        user_id = call.from_user.id

        balance = self.db.get_user_balance(
            user_id
        )

        minimum = self.config["fees"]["cashout_minimum"]
        fee = self.config["fees"]["cashout"]

        text = f"""
    💸 <b>Retragere Fonduri</b>

    💰 <b>Sold disponibil:</b>
    {balance:.2f} RON

    ⚠️ <b>Suma minimă:</b>
    {minimum:.2f} RON

    💸 <b>Taxă platformă:</b>
    {fee:.0f}%

    Alege metoda de retragere:
    """

        markup = telebot.types.InlineKeyboardMarkup()

        markup.row(
            telebot.types.InlineKeyboardButton(
                "🪙 Crypto",
                callback_data="seller_cashout_crypto"
            ),
            telebot.types.InlineKeyboardButton(
                "📷 Cash (BRASOV)",
                callback_data="seller_cashout_cash"
            )
        )

        markup.row(
            telebot.types.InlineKeyboardButton(
                "🔙 Înapoi",
                callback_data="menu_edit_seller_shop"
            )
        )

        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

        self.bot.answer_callback_query(
            call.id
        )

        return True
            
    
    def start_crypto_cashout(
        self,
        call
    ):
        user_id = call.from_user.id

        self.db.set_user_state(
            user_id=user_id,
            state="seller_cashout_ltc_address",
            data={}
        )

        self.bot.send_message(
            call.message.chat.id,
            """
    🪙 <b>Retragere LTC</b>

    📤 Introdu adresa ta LTC:

    ⚠️ Verifică atent adresa înainte de trimitere.
    
    !! O DATA TRIMISA CEREREA NU SE MAI POATE FACE NIMIC
    
    FITI ATENTI SI TRIMITE-TI ADRESA LTC CUM TREBUIE
    """,
            parse_mode="HTML"
        )

        self.bot.answer_callback_query(call.id)

        return True
        
    def handle_ltc_address_input(
        self,
        message
    ):

        user_id = message.from_user.id
        address = message.text.strip()

        if not address:
            self.bot.send_message(
                message.chat.id,
                "❌ Adresă LTC invalidă."
            )
            return True

        self.db.set_user_state(
            user_id=user_id,
            state="seller_cashout_crypto_amount",
            data={
                "wallet_address": address
            }
        )

        balance = self.db.get_user_balance(user_id)
        minimum = self.config["fees"]["cashout_minimum"]
        fee = self.config["fees"]["cashout"]

        self.bot.send_message(
            message.chat.id,
            f"""
    🪙 <b>Retragere LTC</b>

    💰 Sold disponibil:
    {balance:.2f} RON

    ⚠️ Suma minimă:
    {minimum:.2f} RON

    💸 Taxă:
    {fee:.0f}%

    📤 Introdu suma pe care dorești să o retragi.
    """,
            parse_mode="HTML"
        )

        return True 

    def handle_crypto_amount_input(
        self,
        message
    ):

        user_id = message.from_user.id

        state = self.db.get_user_state(
            user_id
        )

        if not state:
            return False

        state_data = state.get("data")

        if isinstance(state_data, str):
            try:
                import json
                state_data = json.loads(state_data)
            except Exception:
                state_data = {}

        wallet_address = state_data.get("wallet_address")

        if not wallet_address:
            self.db.clear_user_state(user_id)

            self.bot.send_message(
                message.chat.id,
                "❌ Adresa LTC nu a fost găsită. Retragerea a fost anulată."
            )

            return True

        try:

            amount = float(
                message.text.strip().replace(",", ".")
            )

        except:

            self.db.clear_user_state(user_id)

            self.bot.send_message(
                message.chat.id,
                "❌ Sumă invalidă. Retragerea a fost anulată."
            )

            return True

        balance = self.db.get_user_balance(
            user_id
        )

        minimum = self.config["fees"]["cashout_minimum"]
        fee_percent = self.config["fees"]["cashout"]

        if amount < minimum:

            self.bot.send_message(
                message.chat.id,
                f"❌ Suma minimă pentru retragere este {minimum:.2f} RON."
            )

            return True

        if amount > balance:

            self.bot.send_message(
                message.chat.id,
                f"❌ Sold insuficient.\n\nSold disponibil: {balance:.2f} RON"
            )

            return True

        fee = round(
            amount * fee_percent / 100,
            2
        )

        receive_ron = round(
            amount - fee,
            2
        )

        # =========================
        # LTC PRICE (reference market rate; payout remains SHKeeper)
        # =========================

        try:
            ltc_price_usd = self.shkeeper.get_usd_price("LTC")
            usd_to_ron = float(self.config.get("usd_to_ron", 4.55))
            if ltc_price_usd <= 0 or usd_to_ron <= 0:
                raise ValueError("Invalid LTC/USD or USD/RON rate")
            ltc_price_ron = ltc_price_usd * usd_to_ron
            ltc_amount = round(receive_ron / ltc_price_ron, 8)
        except Exception as e:
            logger.error(f"LTC price error: {e}")
            self.db.clear_user_state(user_id)
            self.bot.send_message(
                message.chat.id,
                "❌ Nu am putut obține prețul LTC. Retragerea a fost anulată."
            )
            return True

        self.db.set_user_state(

            user_id=user_id,

            state="seller_cashout_crypto_confirm",

            data={

                "wallet_address": wallet_address,

                "amount": amount,

                "fee": fee,

                "receive_ron": receive_ron,

                "ltc_amount": ltc_amount

            }

        )

        markup = telebot.types.InlineKeyboardMarkup()

        markup.row(

            telebot.types.InlineKeyboardButton(
                "✅ Confirmă Retragerea",
                callback_data="seller_cashout_crypto_confirm"
            )

        )

        markup.row(

            telebot.types.InlineKeyboardButton(
                "❌ Anulează",
                callback_data="menu_edit_seller_shop"
            )

        )

        text = f"""
    🪙 <b>Confirmare Retragere LTC</b>

    💰 <b>Sumă solicitată:</b>
    {amount:.2f} RON

    💸 <b>Taxă platformă:</b>
    {fee:.2f} RON ({fee_percent:.0f}%)

    📤 <b>Valoare după taxă:</b>
    {receive_ron:.2f} RON

    🪙 <b>LTC estimat:</b>
    {ltc_amount:.8f} LTC

    🏦 <b>Adresă LTC:</b>
    <code>{wallet_address}</code>

    ⚠️ <i>Valoarea LTC este calculată folosind prețul disponibil în momentul confirmării.</i>
    """

        self.bot.send_message(
            message.chat.id,
            text,
            parse_mode="HTML",
            reply_markup=markup
        )

        return True        
    
    def handle_amount_input(
        self,
        message
    ):

        user_id = message.from_user.id

        state = self.db.get_user_state(
            user_id
        )

        try:

            amount = float(
                message.text
            )

        except:

            self.db.clear_user_state(user_id)

            self.bot.send_message(
                message.chat.id,
                "❌ Sumă invalidă. Retragerea a fost anulată."
            )

            return True

        balance = self.db.get_user_balance(
            user_id
        )

        minimum = self.config["fees"]["cashout_minimum"]

        if amount < minimum:

            self.bot.send_message(

                message.chat.id,

                f"❌ Minimum {minimum} RON."

            )

            return True

        if amount > balance:

            self.bot.send_message(

                message.chat.id,

                "❌ Sold insuficient."

            )

            return True

        fee_percent = self.config["fees"]["cashout"]

        fee = round(
            amount * fee_percent / 100,
            2
        )

        receive = round(
            amount - fee,
            2
        )

        self.db.set_user_state(

            user_id=user_id,

            state="seller_cashout_confirm",

            data={

                "amount": amount,

                "fee": fee,

                "receive": receive

            }

        )

        markup = telebot.types.InlineKeyboardMarkup()

        markup.row(

            telebot.types.InlineKeyboardButton(

                "✅ Confirmă Retragerea",

                callback_data="seller_cashout_confirm"

            )

        )

        markup.row(

            telebot.types.InlineKeyboardButton(

                "❌ Anulează",

                callback_data="menu_edit_seller_shop"

            )

        )

        self.bot.send_message(

            message.chat.id,

            f"""
💸 <b>Confirmare Retragere</b>

💰 Soliciți:

<b>{amount:.2f} RON</b>

💸 Taxă platformă:

<b>{fee:.2f} RON (5%)</b>

📤 Vei primi:

<b>{receive:.2f} RON</b>

Apasă <b>Confirmă Retragerea</b> pentru a trimite cererea administratorilor.
""",

            parse_mode="HTML",

            reply_markup=markup

        )

        return True
            
    def confirm_crypto_cashout(self, call):
        """Create an LTC payout through SHKeeper.

        The balance is reserved before the network payout is requested. If SHKeeper
        rejects/fails the request before a task exists, the same refund path restores it.
        """
        user_id = call.from_user.id
        state = self.db.get_user_state(user_id)
        if not state or state.get("state") != "seller_cashout_crypto_confirm":
            self.bot.answer_callback_query(call.id, "❌ Cererea a expirat.", show_alert=True)
            return True

        data = state["data"]
        if isinstance(data, str):
            data = json.loads(data)

        amount = float(data["amount"])
        fee = float(data["fee"])
        receive_ron = float(data["receive_ron"])
        ltc_amount = float(data["ltc_amount"])
        wallet_address = data["wallet_address"]

        balance_before = self.db.get_user_balance(user_id)
        if amount > balance_before:
            self.db.clear_user_state(user_id)
            self.bot.answer_callback_query(call.id, "❌ Sold insuficient.", show_alert=True)
            return True

        request_id = self.db.create_cashout_request(
            seller_id=user_id,
            amount=amount,
            fee=fee,
            amount_after_fee=receive_ron,
            method="crypto",
            wallet_address=wallet_address,
        )
        if not request_id:
            self.bot.answer_callback_query(call.id, "❌ Nu s-a putut crea cererea de retragere.", show_alert=True)
            return True

        try:
            with self.db.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE cashout_requests
                       SET method=?, wallet_address=?, crypto_amount=?, payout_status=?
                       WHERE id=?""",
                    ("crypto", wallet_address, ltc_amount, "creating", request_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            logger.error("Error preparing crypto cashout #%s: %s", request_id, e)
            self.bot.answer_callback_query(call.id, "❌ Eroare la pregătirea retragerii.", show_alert=True)
            return True

        # Reserve user balance BEFORE asking the wallet to send funds.
        if not self.db.add_user_balance(user_id, -amount):
            with self.db.pool.get_connection() as conn:
                conn.execute("UPDATE cashout_requests SET status='rejected', payout_status='balance_error' WHERE id=?", (request_id,))
                conn.commit()
            self.bot.answer_callback_query(call.id, "❌ Soldul nu a putut fi rezervat.", show_alert=True)
            return True

        balance_after = self.db.get_user_balance(user_id)
        self.db.add_wallet_transaction(
            user_id=user_id,
            transaction_type="CASHOUT_CRYPTO",
            amount=-amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"LTC Cashout #{request_id}",
            reference_id=str(request_id),
        )

        try:
            payout_track_id = self.shkeeper.create_payout(
                local_crypto="LTC",
                amount=ltc_amount,
                destination=wallet_address,
            )
        except Exception as e:
            logger.exception("SHKeeper LTC payout creation failed for #%s: %s", request_id, e)
            self._refund_failed_crypto_cashout(request_id, user_id, amount, fee)
            self.db.clear_user_state(user_id)
            self.bot.answer_callback_query(call.id, "❌ SHKeeper a respins sau nu a putut crea payout-ul. Soldul a fost restituit.", show_alert=True)
            return True

        try:
            with self.db.pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """UPDATE cashout_requests
                       SET payout_track_id=?, payout_status='pending'
                       WHERE id=?""",
                    (payout_track_id, request_id),
                )
                conn.commit()
        except sqlite3.Error as e:
            # A payout task already exists. Do NOT refund automatically here, because
            # that could pay the user twice. Keep the balance reserved and alert logs.
            logger.critical("SHKeeper payout %s exists but could not be saved for request #%s: %s", payout_track_id, request_id, e)
            self.bot.answer_callback_query(call.id, "⚠️ Payout creat, dar salvarea locală a eșuat. Verifică manual logurile SHKeeper.", show_alert=True)
            return True

        if fee:
            self.db.add_platform_fee("cashout", fee)
        self.db.clear_user_state(user_id)

        self.bot.edit_message_text(
            f"""✅ <b>Retragerea LTC a fost trimisă către SHKeeper.</b>

💰 Sumă solicitată: <b>{amount:.2f} RON</b>
💸 Taxă platformă: <b>{fee:.2f} RON</b>
📤 Valoare după taxă: <b>{receive_ron:.2f} RON</b>
🪙 LTC: <b>{ltc_amount:.8f} LTC</b>
🏦 Adresă: <code>{wallet_address}</code>
🆔 Task ID: <code>{payout_track_id}</code>
📌 Status: <b>pending</b>""",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML",
        )
        self.bot.answer_callback_query(call.id, "✅ Payout LTC trimis către SHKeeper.")
        return True

    def start_cash_cashout(
        self,
        call
    ):

        user_id = call.from_user.id

        self.db.set_user_state(
            user_id=user_id,
            state="seller_cashout_amount"
        )

        return self.handle_cashout_amount_prompt(
            call
        )
        
    def handle_cashout_amount_prompt(
        self,
        call
    ):

        balance = self.db.get_user_balance(
            call.from_user.id
        )

        minimum = self.config["fees"]["cashout_minimum"]
        fee = self.config["fees"]["cashout"]

        text = f"""
    📷 <b>Retragere Cash</b>

    💰 Sold disponibil:
    {balance:.2f} RON

    ⚠️ Suma minimă:
    {minimum:.2f} RON

    💸 Taxă:
    {fee:.0f}%

    ✍️ Introdu suma pe care dorești să o retragi.
    """

        self.bot.send_message(
            call.message.chat.id,
            text,
            parse_mode="HTML"
        )

        self.bot.answer_callback_query(
            call.id
        )

        return True
        
    def check_shkeeper_payout(self, track_id):
        try:
            status, txid, raw = self.shkeeper.get_payout_status("LTC", str(track_id))
            logger.info("SHKeeper payout check %s: %s", track_id, status)
            return {"status": status, "txid": txid, "raw": raw}
        except Exception as e:
            logger.error("Error checking SHKeeper payout %s: %s", track_id, e)
            return None

    def start_cashout_checker(
        self
    ):

        if self.cashout_checker_running:
            return

        self.cashout_checker_running = True

        self.cashout_checker_thread = threading.Thread(
            target=self._cashout_checker_loop,
            daemon=True
        )

        self.cashout_checker_thread.start()

        logger.info(
            "🔄 Crypto cashout checker started."
        )


    def stop_cashout_checker(
        self
    ):

        self.cashout_checker_running = False

        logger.info(
            "🛑 Crypto cashout checker stopped."
        )


    def _cashout_checker_loop(
        self
    ):

        while self.cashout_checker_running:

            try:

                self._check_pending_crypto_cashouts()

            except Exception as e:

                logger.error(
                    f"Cashout checker error: {e}"
                )

            time.sleep(30)
            
    def _check_pending_crypto_cashouts(
        self
    ):

        conn = sqlite3.connect(
            self.db.db_path
        )

        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id,
                seller_id,
                amount,
                fee,
                amount_after_fee,
                payout_track_id,
                payout_status
            FROM cashout_requests
            WHERE method='crypto'
            AND payout_track_id IS NOT NULL
            AND status NOT IN (
                'completed',
                'rejected_refunded'
            )
            ORDER BY created_at
        """)

        requests_list = cursor.fetchall()

        conn.close()

        if not requests_list:
            return

        for row in requests_list:

            request_id = row[0]
            seller_id = row[1]
            amount = float(row[2])
            fee = float(row[3])
            receive_ron = float(row[4])
            track_id = row[5]

            payout = self.check_shkeeper_payout(
                track_id
            )

            if not payout:
                continue

            payout_status = payout["status"]
            txid = payout.get("txid")

            # =========================
            # UPDATE STATUS
            # =========================

            with self.db.pool.get_connection() as conn:

                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE cashout_requests

                    SET
                        payout_status=?,
                        txid=COALESCE(?, txid)

                    WHERE id=?
                """,(
                    payout_status,
                    txid,
                    request_id
                ))

                conn.commit()

            # =========================
            # SUCCESS
            # =========================

            if payout_status == "confirmed":

                with self.db.pool.get_connection() as conn:

                    cursor = conn.cursor()

                    cursor.execute("""
                        UPDATE cashout_requests

                        SET
                            status='completed',
                            completed_at=CURRENT_TIMESTAMP

                        WHERE id=?

                        AND status!='completed'
                    """,(request_id,))

                    conn.commit()

                try:

                    self.bot.send_message(
                        seller_id,

                        f"""
    ✅ <b>Retragerea Crypto a fost finalizată.</b>

    💰 Sumă:
    {amount:.2f} RON

    💸 Taxă:
    {fee:.2f} RON

    📤 Valoare primită:
    {receive_ron:.2f} RON

    🪙 LTC trimis către adresa ta.

    🧾 TXID:
    <code>{txid or 'N/A'}</code>
    """,

                        parse_mode="HTML"
                    )

                except Exception as e:

                    logger.error(
                        f"Failed notifying seller {seller_id}: {e}"
                    )

            # =========================
            # FAILED
            # =========================

            elif payout_status in (
                "rejected",
                "canceled"
            ):

                self._refund_failed_crypto_cashout(
                    request_id=request_id,
                    seller_id=seller_id,
                    amount=amount,
                    fee=fee
                )
                
    def _refund_failed_crypto_cashout(self, request_id, seller_id, amount, fee):
        conn = sqlite3.connect(self.db.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM cashout_requests WHERE id=?", (request_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return
        if row[0] == "rejected_refunded":
            conn.close()
            return

        # Claim the refund exactly once.
        cursor.execute(
            """UPDATE cashout_requests
               SET status='rejected_refunded', payout_status='rejected', completed_at=CURRENT_TIMESTAMP
               WHERE id=? AND status!='rejected_refunded'""",
            (request_id,),
        )
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        if not changed:
            return

        balance_before = self.db.get_user_balance(seller_id)
        self.db.add_user_balance(seller_id, amount)
        balance_after = self.db.get_user_balance(seller_id)
        self.db.add_wallet_transaction(
            user_id=seller_id,
            transaction_type="CASHOUT_REFUND",
            amount=amount,
            balance_before=balance_before,
            balance_after=balance_after,
            description=f"Refund cashout #{request_id}",
            reference_id=str(request_id),
        )
        # Fee was recorded after the payout task was accepted; reverse it on failure.
        if fee:
            self.db.add_platform_fee("cashout", -float(fee))
        try:
            self.bot.send_message(
                seller_id,
                f"""❌ <b>Retragerea Crypto a eșuat.</b>
💰 Sumă returnată: {amount:.2f} RON
💸 Taxa a fost anulată.
💳 Soldul a fost restituit automat.""",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Failed notifying seller about refund %s: %s", seller_id, e)

