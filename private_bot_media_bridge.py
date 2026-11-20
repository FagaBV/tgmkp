import io
import logging
import threading
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class PrivateBotMediaBridge:
    """Re-upload media owned by the main bot so a private bot can use it.

    Telegram file_id values belong to the bot that received/uploaded them. The
    main project stores page artwork as main-bot file_ids. This bridge downloads
    those files with the main bot token, uploads them through the private bot,
    and caches the new private-bot file_id in SQLite.
    """

    def __init__(self, store, main_bot_token: str, private_bot_id: int):
        self.store = store
        self.main_bot_token = str(main_bot_token or "").strip()
        self.private_bot_id = int(private_bot_id)
        self.session = requests.Session()
        self.lock = threading.RLock()

    @staticmethod
    def _looks_like_telegram_file_id(value):
        return isinstance(value, str) and value.startswith("AgAC")

    def _download_from_main_bot(self, source_file_id: str) -> bytes:
        if not self.main_bot_token:
            raise RuntimeError("Main bot token is missing; cannot bridge Telegram media")

        get_file = self.session.get(
            f"https://api.telegram.org/bot{self.main_bot_token}/getFile",
            params={"file_id": source_file_id},
            timeout=15,
        )
        get_file.raise_for_status()
        payload = get_file.json()
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description") or "getFile failed")

        file_path = (payload.get("result") or {}).get("file_path")
        if not file_path:
            raise RuntimeError("Telegram getFile returned no file_path")

        download = self.session.get(
            f"https://api.telegram.org/file/bot{self.main_bot_token}/{file_path}",
            timeout=30,
        )
        download.raise_for_status()
        return download.content

    @staticmethod
    def _extract_private_file_id(result) -> Optional[str]:
        if not isinstance(result, dict):
            return None
        photos = result.get("photo") or []
        if isinstance(photos, list) and photos:
            candidate = photos[-1]
            if isinstance(candidate, dict):
                return candidate.get("file_id")
            return getattr(candidate, "file_id", None)
        return None

    def send_photo(self, original_send_photo, send_message, chat_id, photo,
                   caption=None, parse_mode=None, reply_markup=None):
        # URLs, open files, already-private media etc. go through unchanged.
        if not self._looks_like_telegram_file_id(photo):
            return original_send_photo(
                chat_id=chat_id, photo=photo, caption=caption,
                parse_mode=parse_mode, reply_markup=reply_markup,
            )

        source_file_id = photo

        # Fast path: use private bot's cached file_id.
        cached = self.store.get_media_cache(self.private_bot_id, source_file_id)
        if cached:
            result = original_send_photo(
                chat_id=chat_id, photo=cached, caption=caption,
                parse_mode=parse_mode, reply_markup=reply_markup,
            )
            if result is not None:
                return result
            # Cache may have become stale after token rotation.
            self.store.delete_media_cache(self.private_bot_id, source_file_id)

        # First use on this private bot: fetch with main bot and upload bytes.
        try:
            with self.lock:
                # Re-check after waiting for another send of the same image.
                cached = self.store.get_media_cache(self.private_bot_id, source_file_id)
                if cached:
                    result = original_send_photo(
                        chat_id=chat_id, photo=cached, caption=caption,
                        parse_mode=parse_mode, reply_markup=reply_markup,
                    )
                    if result is not None:
                        return result

                content = self._download_from_main_bot(source_file_id)
                media = io.BytesIO(content)
                media.name = "page.jpg"
                result = original_send_photo(
                    chat_id=chat_id, photo=media, caption=caption,
                    parse_mode=parse_mode, reply_markup=reply_markup,
                )
                private_file_id = self._extract_private_file_id(result)
                if private_file_id:
                    self.store.set_media_cache(
                        self.private_bot_id, source_file_id, private_file_id
                    )
                    logger.info(
                        "Cached bridged media for private bot %s", self.private_bot_id
                    )
                if result is not None:
                    return result
                raise RuntimeError("Private bot upload returned no message")
        except Exception as exc:
            # Media must never make navigation unusable. Fall back to text.
            logger.warning(
                "Private media bridge failed for bot=%s; sending text fallback: %s",
                self.private_bot_id, exc,
            )
            return send_message(
                chat_id=chat_id,
                text=caption or "",
                parse_mode=parse_mode,
                reply_markup=reply_markup,
            )
