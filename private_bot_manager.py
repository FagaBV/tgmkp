import json
import logging
import os
import fcntl
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from cryptography.fernet import Fernet, InvalidToken
from private_bot_media_bridge import PrivateBotMediaBridge

logger = logging.getLogger(__name__)


class PrivateBotError(RuntimeError):
    pass


@dataclass
class PrivateBotRecord:
    owner_user_id: int
    bot_user_id: int
    bot_username: str
    token_encrypted: str
    status: str
    webhook_path_secret: Optional[str]
    webhook_header_secret: Optional[str]


class PrivateBotStore:
    def __init__(self, db_path: str, master_key_file: str):
        self.db_path = db_path
        self.master_key_file = Path(master_key_file)
        self._ensure_key()
        self.fernet = Fernet(self.master_key_file.read_bytes().strip())
        self._ensure_tables()

    def _ensure_key(self):
        if self.master_key_file.exists():
            return
        self.master_key_file.write_bytes(Fernet.generate_key() + b"\n")
        try:
            os.chmod(self.master_key_file, 0o600)
        except OSError:
            pass

    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS private_bots (
                    owner_user_id INTEGER PRIMARY KEY,
                    bot_user_id INTEGER UNIQUE NOT NULL,
                    bot_username TEXT NOT NULL,
                    token_encrypted TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    webhook_path_secret TEXT,
                    webhook_header_secret TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_private_bots_status ON private_bots(status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS private_bot_media_cache (
                    bot_user_id INTEGER NOT NULL,
                    source_file_id TEXT NOT NULL,
                    private_file_id TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (bot_user_id, source_file_id)
                )
                """
            )
            conn.commit()

    def encrypt_token(self, token: str) -> str:
        return self.fernet.encrypt(token.encode("utf-8")).decode("ascii")

    def decrypt_token(self, encrypted: str) -> str:
        try:
            return self.fernet.decrypt(encrypted.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise PrivateBotError("Tokenul salvat nu poate fi decriptat. Verifică master key-ul.") from exc

    def upsert(self, owner_user_id: int, bot_user_id: int, bot_username: str, token: str):
        path_secret = secrets.token_urlsafe(24).replace("/", "_")
        header_secret = secrets.token_urlsafe(32)
        encrypted = self.encrypt_token(token)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO private_bots (
                    owner_user_id, bot_user_id, bot_username, token_encrypted,
                    status, webhook_path_secret, webhook_header_secret
                ) VALUES (?, ?, ?, ?, 'active', ?, ?)
                ON CONFLICT(owner_user_id) DO UPDATE SET
                    bot_user_id=excluded.bot_user_id,
                    bot_username=excluded.bot_username,
                    token_encrypted=excluded.token_encrypted,
                    status='active',
                    webhook_path_secret=excluded.webhook_path_secret,
                    webhook_header_secret=excluded.webhook_header_secret,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (owner_user_id, bot_user_id, bot_username, encrypted, path_secret, header_secret),
            )
            conn.commit()
        return self.get_by_owner(owner_user_id)

    def get_by_owner(self, owner_user_id: int) -> Optional[PrivateBotRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM private_bots WHERE owner_user_id = ?", (owner_user_id,)
            ).fetchone()
        return self._record(row)

    def get_by_bot_id(self, bot_user_id: int) -> Optional[PrivateBotRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM private_bots WHERE bot_user_id = ?", (bot_user_id,)
            ).fetchone()
        return self._record(row)

    def active(self):
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM private_bots WHERE status = 'active' ORDER BY created_at"
            ).fetchall()
        return [self._record(r) for r in rows]

    def count_active(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM private_bots WHERE status='active'").fetchone()[0])

    def delete(self, owner_user_id: int):
        with self._connect() as conn:
            conn.execute("DELETE FROM private_bots WHERE owner_user_id = ?", (owner_user_id,))
            conn.commit()

    def get_media_cache(self, bot_user_id: int, source_file_id: str):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT private_file_id FROM private_bot_media_cache WHERE bot_user_id=? AND source_file_id=?",
                (int(bot_user_id), source_file_id),
            ).fetchone()
        return row[0] if row else None

    def set_media_cache(self, bot_user_id: int, source_file_id: str, private_file_id: str):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO private_bot_media_cache (bot_user_id, source_file_id, private_file_id)
                VALUES (?, ?, ?)
                ON CONFLICT(bot_user_id, source_file_id) DO UPDATE SET
                    private_file_id=excluded.private_file_id,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (int(bot_user_id), source_file_id, private_file_id),
            )
            conn.commit()

    def delete_media_cache(self, bot_user_id: int, source_file_id: str):
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM private_bot_media_cache WHERE bot_user_id=? AND source_file_id=?",
                (int(bot_user_id), source_file_id),
            )
            conn.commit()

    @staticmethod
    def _record(row):
        if not row:
            return None
        d = dict(row)
        return PrivateBotRecord(
            owner_user_id=int(d["owner_user_id"]),
            bot_user_id=int(d["bot_user_id"]),
            bot_username=d["bot_username"],
            token_encrypted=d["token_encrypted"],
            status=d["status"],
            webhook_path_secret=d.get("webhook_path_secret"),
            webhook_header_secret=d.get("webhook_header_secret"),
        )


class PrivateBotManager:
    """Runs personal bot identities on the same ShopBot backend/database.

    polling mode is intended for testing/small deployments.
    webhook mode uses one HTTP listener and is the scalable production mode.
    """

    def __init__(self, db, config, app_factory):
        self.db = db
        self.config = config
        self.cfg = config.get("private_bots", {})
        key_file = self.cfg.get("master_key_file", ".private_bot_master_key")
        self.store = PrivateBotStore(db.db_path, key_file)
        self.app_factory = app_factory
        self.instances = {}
        self.poll_threads = {}
        self.lock = threading.RLock()
        self._webhook_started = False
        self.poll_lock_dir = Path(self.cfg.get("poll_lock_dir", ".private_bot_locks"))
        self.poll_lock_dir.mkdir(parents=True, exist_ok=True)
        self._poll_lock_handles = {}

    @property
    def mode(self):
        return str(self.cfg.get("mode", "polling")).lower().strip()

    def validate_token(self, token: str):
        token = token.strip()
        if ":" not in token or len(token) < 30:
            raise PrivateBotError("Tokenul nu pare a fi un token BotFather valid.")
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            data = r.json()
        except Exception as exc:
            raise PrivateBotError("Nu am putut verifica tokenul la Telegram.") from exc
        if not data.get("ok"):
            raise PrivateBotError("Telegram a respins tokenul. Verifică tokenul generat de BotFather.")
        result = data.get("result", {})
        if not result.get("is_bot") or not result.get("id") or not result.get("username"):
            raise PrivateBotError("Tokenul nu aparține unui bot Telegram valid.")
        return int(result["id"]), str(result["username"])

    def connect_bot(self, owner_user_id: int, token: str):
        bot_user_id, bot_username = self.validate_token(token)
        existing_for_bot = self.store.get_by_bot_id(bot_user_id)
        if existing_for_bot and existing_for_bot.owner_user_id != owner_user_id:
            raise PrivateBotError("Botul acesta este deja conectat altui utilizator.")

        if self.mode == "polling":
            cap = int(self.cfg.get("max_polling_bots", 25))
            current = self.store.count_active()
            old = self.store.get_by_owner(owner_user_id)
            if current >= cap and not old:
                raise PrivateBotError(
                    f"Serverul este în modul polling și limita este {cap} boți. "
                    "Pentru scară mare activează modul webhook."
                )

        old = self.store.get_by_owner(owner_user_id)
        if old:
            self.stop_bot(owner_user_id, clear_webhook=True)

        record = self.store.upsert(owner_user_id, bot_user_id, bot_username, token)
        self.start_record(record)
        return record

    def disconnect_bot(self, owner_user_id: int):
        self.stop_bot(owner_user_id, clear_webhook=True)
        self.store.delete(owner_user_id)

    def status(self, owner_user_id: int):
        return self.store.get_by_owner(owner_user_id)

    def start_existing_async(self):
        t = threading.Thread(target=self.start_existing, name="private-bot-loader", daemon=True)
        t.start()

    def start_existing(self):
        if self.mode == "webhook":
            self._start_webhook_server()
        records = self.store.active()
        logger.info("Private bots: loading %s active bot(s) in %s mode", len(records), self.mode)
        for record in records:
            try:
                self.start_record(record)
                time.sleep(0.05)
            except Exception:
                logger.exception("Could not start private bot @%s", record.bot_username)

    def _build_app(self, record):
        token = self.store.decrypt_token(record.token_encrypted)
        app = self.app_factory(token, record.owner_user_id)
        self._install_media_bridge(app, record)
        return app

    def _install_media_bridge(self, app, record):
        if getattr(app.bot, "_private_media_bridge_installed", False):
            return
        main_token = self.config.get("bot_token", "")
        bridge = PrivateBotMediaBridge(
            store=self.store,
            main_bot_token=main_token,
            private_bot_id=record.bot_user_id,
        )
        original_send_photo = app.bot.send_photo
        original_send_message = app.bot.send_message

        def bridged_send_photo(chat_id, photo, caption=None, parse_mode=None, reply_markup=None):
            return bridge.send_photo(
                original_send_photo=original_send_photo,
                send_message=original_send_message,
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )

        app.bot.send_photo = bridged_send_photo
        app.bot._private_media_bridge_installed = True
        app.bot._private_media_bridge = bridge

    def start_record(self, record: PrivateBotRecord):
        with self.lock:
            if record.owner_user_id in self.instances:
                return self.instances[record.owner_user_id]
            app = self._build_app(record)
            self.instances[record.owner_user_id] = app

        if self.mode == "webhook":
            self._start_webhook_server()
            self._set_webhook(record)
        else:
            self._delete_webhook(record)
            thread = threading.Thread(
                target=self._poll_worker,
                args=(record, app),
                name=f"private-bot-{record.bot_user_id}",
                daemon=True,
            )
            self.poll_threads[record.owner_user_id] = thread
            thread.start()
        logger.info("Private bot started: @%s owner=%s mode=%s", record.bot_username, record.owner_user_id, self.mode)
        return app

    def _poll_worker(self, record, app):
        lock_path = self.poll_lock_dir / f"{record.bot_user_id}.lock"
        lock_handle = open(lock_path, "a+")
        try:
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logger.warning(
                    "Private bot @%s is already being polled by another local process; skipping duplicate getUpdates",
                    record.bot_username,
                )
                return

            self._poll_lock_handles[record.owner_user_id] = lock_handle
            try:
                app.bot.infinity_polling(
                    skip_pending=True,
                    timeout=20,
                    long_polling_timeout=20,
                    allowed_updates=["message", "callback_query"],
                )
            except TypeError:
                app.bot.infinity_polling(skip_pending=True, timeout=20)
            except Exception:
                logger.exception("Polling stopped for private bot @%s", record.bot_username)
        finally:
            self._poll_lock_handles.pop(record.owner_user_id, None)
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                lock_handle.close()
            except Exception:
                pass

    def stop_bot(self, owner_user_id: int, clear_webhook=False):
        record = self.store.get_by_owner(owner_user_id)
        with self.lock:
            app = self.instances.pop(owner_user_id, None)
            self.poll_threads.pop(owner_user_id, None)
        if app:
            try:
                app.bot._original_bot.stop_polling()
            except Exception:
                pass
            try:
                app.bot.client.close()
            except Exception:
                pass
        if clear_webhook and record:
            self._delete_webhook(record)

    def _api_post(self, record, method, payload=None):
        token = self.store.decrypt_token(record.token_encrypted)
        return requests.post(
            f"https://api.telegram.org/bot{token}/{method}",
            json=payload or {},
            timeout=10,
        ).json()

    def _delete_webhook(self, record):
        try:
            self._api_post(record, "deleteWebhook", {"drop_pending_updates": False})
        except Exception:
            logger.warning("Could not clear webhook for @%s", record.bot_username)

    def _set_webhook(self, record):
        base = str(self.cfg.get("webhook_base_url", "")).rstrip("/")
        if not base.startswith("https://"):
            raise PrivateBotError("private_bots.webhook_base_url trebuie să fie HTTPS în modul webhook.")
        url = f"{base}/private-bot/{record.bot_user_id}/{record.webhook_path_secret}"
        payload = {
            "url": url,
            "secret_token": record.webhook_header_secret,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": False,
        }
        result = self._api_post(record, "setWebhook", payload)
        if not result.get("ok"):
            raise PrivateBotError(f"setWebhook a eșuat pentru @{record.bot_username}: {result.get('description')}")

    def _start_webhook_server(self):
        if self._webhook_started:
            return
        with self.lock:
            if self._webhook_started:
                return
            from flask import Flask, abort, request
            import telebot

            flask_app = Flask("private_bot_webhooks")
            manager = self

            @flask_app.post("/private-bot/<int:bot_id>/<path_secret>")
            def private_bot_webhook(bot_id, path_secret):
                record = manager.store.get_by_bot_id(bot_id)
                if not record or record.status != "active":
                    abort(404)
                if not secrets.compare_digest(record.webhook_path_secret or "", path_secret or ""):
                    abort(404)
                header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
                if not secrets.compare_digest(record.webhook_header_secret or "", header):
                    abort(403)

                app = manager.instances.get(record.owner_user_id)
                if app is None:
                    app = manager.start_record(record)
                try:
                    update = telebot.types.Update.de_json(request.get_json(force=True))
                    app.bot._original_bot.process_new_updates([update])
                except Exception:
                    logger.exception("Private webhook processing failed for bot_id=%s", bot_id)
                    return "error", 500
                return "ok", 200

            host = self.cfg.get("webhook_listen_host", "127.0.0.1")
            port = int(self.cfg.get("webhook_listen_port", 8790))
            thread = threading.Thread(
                target=lambda: flask_app.run(host=host, port=port, threaded=True, use_reloader=False),
                name="private-bot-webhook-server",
                daemon=True,
            )
            thread.start()
            self._webhook_started = True
            logger.info("Private bot webhook listener started on %s:%s", host, port)
