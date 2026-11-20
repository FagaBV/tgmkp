import logging
import os
from typing import Any, Dict, Optional, Tuple

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


class SHKeeperError(RuntimeError):
    pass


class SHKeeperClient:
    """Small SHKeeper API wrapper used by the Telegram bot.

    Invoice endpoints use X-Shkeeper-Api-Key.
    Payout endpoints use HTTP Basic Auth.
    """

    PRICE_IDS = {
        "BTC": "bitcoin",
        "LTC": "litecoin",
        "XMR": "monero",
        "SOL": "solana",
        "USDTBSC": "tether",
    }

    DEFAULT_CURRENCY_MAP = {
        "BTC": "BTC",
        "LTC": "LTC",
        "XMR": "XMR",
        "SOL": "SOL",
        "USDTBSC": "BNB-USDT",
    }

    def __init__(self, config: Dict[str, Any]):
        cfg = dict(config.get("shkeeper") or {})

        self.base_url = os.getenv("SHKEEPER_BASE_URL", cfg.get("base_url", "")).rstrip("/")
        # SHKeeper exposes a separate API key for each payment gateway/wallet.
        # Keep legacy `api_key` support for older configs, but prefer `api_keys`.
        self.api_key = os.getenv("SHKEEPER_API_KEY", cfg.get("api_key", ""))
        self.api_keys = dict(cfg.get("api_keys") or {})
        for gateway in list(self.api_keys):
            env_name = "SHKEEPER_API_KEY_" + str(gateway).upper().replace("-", "_")
            if os.getenv(env_name):
                self.api_keys[gateway] = os.getenv(env_name)
        self.username = os.getenv("SHKEEPER_USERNAME", cfg.get("username", ""))
        self.password = os.getenv("SHKEEPER_PASSWORD", cfg.get("password", ""))
        self.callback_url = os.getenv("SHKEEPER_CALLBACK_URL", cfg.get("callback_url", ""))
        self.timeout = int(cfg.get("timeout", 20))
        self.price_timeout = int(cfg.get("price_timeout", 10))

        self.currency_map = dict(self.DEFAULT_CURRENCY_MAP)
        self.currency_map.update(cfg.get("currency_map") or {})

        self.payout_fees = {
            "BTC": "5",
            "LTC": "5",
            "XMR": "2",
            "default": "0",
        }
        self.payout_fees.update(cfg.get("payout_fees") or {})

        self.price_api_url = cfg.get(
            "price_api_url",
            "https://api.coingecko.com/api/v3/simple/price",
        )

    def _require_base(self) -> None:
        if not self.base_url:
            raise SHKeeperError("SHKeeper base_url is missing")

    def _key_for_gateway(self, gateway: str) -> str:
        gateway = str(gateway)
        key = self.api_keys.get(gateway) or self.api_keys.get(gateway.upper())
        if not key and self.api_key:
            key = self.api_key
        if not key:
            raise SHKeeperError(f"SHKeeper API key is missing for gateway {gateway}")
        return str(key)

    def _api_headers(self, gateway: str) -> Dict[str, str]:
        return {
            "X-Shkeeper-Api-Key": self._key_for_gateway(gateway),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _configured_gateway_keys(self):
        seen = set()
        for gateway, key in self.api_keys.items():
            if key and (gateway, key) not in seen:
                seen.add((gateway, key))
                yield str(gateway), str(key)
        if self.api_key and ("legacy", self.api_key) not in seen:
            yield "legacy", str(self.api_key)

    def _basic_auth(self) -> HTTPBasicAuth:
        if not self.username or not self.password:
            raise SHKeeperError("SHKeeper username/password for payouts are missing")
        return HTTPBasicAuth(self.username, self.password)

    def map_currency(self, local_code: str) -> str:
        code = str(local_code).upper()
        mapped = self.currency_map.get(code)
        if not mapped:
            raise SHKeeperError(f"No SHKeeper currency mapping configured for {code}")
        return mapped

    def list_currencies(self) -> Any:
        self._require_base()
        response = requests.get(f"{self.base_url}/api/v1/crypto", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def create_invoice(
        self,
        local_crypto: str,
        external_id: str,
        amount_usd: float,
    ) -> Dict[str, Any]:
        self._require_base()
        if not self.callback_url:
            raise SHKeeperError("SHKeeper callback_url is missing")

        crypto = self.map_currency(local_crypto)
        payload = {
            "external_id": str(external_id),
            "fiat": "USD",
            "amount": f"{float(amount_usd):.2f}",
            "callback_url": self.callback_url,
        }

        response = requests.post(
            f"{self.base_url}/api/v1/{crypto}/payment_request",
            json=payload,
            headers=self._api_headers(crypto),
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        if str(data.get("status", "")).lower() != "success":
            raise SHKeeperError(f"SHKeeper invoice error: {data}")

        return {
            "track_id": str(external_id),
            "external_id": str(external_id),
            "shkeeper_invoice_id": data.get("id"),
            "address": data.get("wallet"),
            "pay_amount": data.get("amount"),
            "pay_currency": str(local_crypto).upper(),
            "shkeeper_crypto": crypto,
            "exchange_rate": data.get("exchange_rate"),
            "display_name": data.get("display_name"),
            "recalculate_after": data.get("recalculate_after"),
        }

    @staticmethod
    def _normalize_invoice_status(value: Optional[str]) -> str:
        status = str(value or "").upper()
        if status in {"PAID", "OVERPAID", "SUCCESS", "CONFIRMED"}:
            return "paid"
        if status in {"EXPIRED"}:
            return "expired"
        if status in {"CANCELLED", "CANCELED", "FAILED", "FAILURE", "REJECTED"}:
            return "failed"
        if status in {"REFUNDED"}:
            return "refunded"
        return "pending"

    def get_invoice(self, external_id: str) -> Dict[str, Any]:
        """Find an invoice using the per-wallet API keys configured in SHKeeper.

        SHKeeper's UI generates a distinct API key for each gateway. The existing bot
        stores only external_id in several flows, so status lookup safely tries the
        configured gateway keys until the matching invoice is found.
        """
        self._require_base()
        last_error = None
        keys = list(self._configured_gateway_keys())
        if not keys:
            raise SHKeeperError("No SHKeeper wallet API keys are configured")

        for gateway, key in keys:
            try:
                response = requests.get(
                    f"{self.base_url}/api/v1/invoices/{external_id}",
                    headers={
                        "X-Shkeeper-Api-Key": key,
                        "Accept": "application/json",
                    },
                    timeout=self.timeout,
                )
                if response.status_code in (401, 403, 404):
                    continue
                response.raise_for_status()
                data = response.json()
                invoices = data.get("invoices") if isinstance(data, dict) else None
                if not invoices:
                    continue

                normalized = [self._normalize_invoice_status(item.get("status")) for item in invoices]
                if "paid" in normalized:
                    status = "paid"
                elif "refunded" in normalized:
                    status = "refunded"
                elif "failed" in normalized:
                    status = "failed"
                elif "expired" in normalized:
                    status = "expired"
                else:
                    status = "pending"

                return {
                    "status": status,
                    "gateway": gateway,
                    "invoices": invoices,
                    "raw": data,
                }
            except requests.RequestException as exc:
                last_error = exc
                logger.debug("Invoice lookup with gateway %s failed: %s", gateway, exc)

        if last_error:
            logger.debug("No matching invoice found after wallet-key lookup: %s", last_error)
        return {"status": "pending", "invoices": [], "raw": {}}

    def create_payout(
        self,
        local_crypto: str,
        amount: float,
        destination: str,
        fee: Optional[str] = None,
    ) -> str:
        self._require_base()
        crypto = self.map_currency(local_crypto)
        if fee is None:
            fee = str(self.payout_fees.get(str(local_crypto).upper(), self.payout_fees["default"]))

        payload = {
            "amount": str(amount),
            "destination": destination,
            "fee": str(fee),
        }
        response = requests.post(
            f"{self.base_url}/api/v1/{crypto}/payout",
            json=payload,
            auth=self._basic_auth(),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        task_id = data.get("task_id") if isinstance(data, dict) else None
        if not task_id:
            raise SHKeeperError(f"SHKeeper payout error: {data}")
        return str(task_id)

    def get_payout_status(self, local_crypto: str, task_id: str) -> Tuple[str, Optional[str], Dict[str, Any]]:
        self._require_base()
        crypto = self.map_currency(local_crypto)
        response = requests.get(
            f"{self.base_url}/api/v1/{crypto}/task/{task_id}",
            auth=self._basic_auth(),
            headers={"Accept": "application/json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()

        raw_status = str(data.get("status", "PENDING")).upper()
        if raw_status == "SUCCESS":
            status = "confirmed"
        elif raw_status == "FAILURE":
            status = "rejected"
        else:
            status = "pending"

        txid = None
        for result in data.get("result") or []:
            txids = result.get("txids") or []
            if txids:
                txid = str(txids[0])
                break

        return status, txid, data

    def get_usd_price(self, local_crypto: str) -> float:
        """Get a reference USD price for RON->crypto cashout conversion.

        SHKeeper's documented payout endpoint expects crypto amount, so the bot
        still needs an external market-rate source. This uses CoinGecko only for
        the reference rate; the payment/payout itself stays entirely on SHKeeper.
        """
        code = str(local_crypto).upper()
        asset_id = self.PRICE_IDS.get(code)
        if not asset_id:
            raise SHKeeperError(f"No market-price asset mapping configured for {code}")

        response = requests.get(
            self.price_api_url,
            params={"ids": asset_id, "vs_currencies": "usd"},
            timeout=self.price_timeout,
        )
        response.raise_for_status()
        data = response.json()
        price = ((data.get(asset_id) or {}).get("usd"))
        if price is None:
            raise SHKeeperError(f"Could not obtain USD price for {code}")
        return float(price)
