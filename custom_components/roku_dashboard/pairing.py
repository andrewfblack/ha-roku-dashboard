"""Device credentials and device-initiated pairing for Family Dashboard.

Every paired client gets its own revocable token instead of sharing one
secret. Clients that have no usable keyboard (Apple TV) start a pairing
request, show the returned code on screen, and wait for an administrator to
approve it in the Home Assistant panel.

The legacy "type the short code" flow stays available forever: Roku channels
cannot be force-updated, so an install that paired before this change must
keep working.
"""

from __future__ import annotations

import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DATA_DEVICES,
    DEVICE_STORE_KEY,
    DEVICE_STORE_VERSION,
    DEVICE_TOUCH_INTERVAL,
    DOMAIN,
    PAIRING_CODE_LENGTH,
    PAIRING_CODE_TTL,
    PAIRING_REQUEST_LIMIT,
    PLATFORMS,
)

# Unambiguous alphabet: no 0/O and no 1/I, so a code survives being read
# aloud from a TV screen and typed on a phone.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# Status values a pairing request moves through.
PENDING = "pending"
APPROVED = "approved"
DENIED = "denied"
CONSUMED = "consumed"


def _now() -> float:
    """Return the current time as a timestamp."""
    return time.time()


def _stamp() -> str:
    """Return the current time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _store(hass: HomeAssistant) -> Store:
    """Return the storage helper for the device store."""
    return Store(hass, DEVICE_STORE_VERSION, DEVICE_STORE_KEY)


def _data(hass: HomeAssistant) -> dict[str, Any]:
    """Return the in-memory device store."""
    return hass.data.setdefault(DOMAIN, {}).setdefault(
        DATA_DEVICES,
        {"devices": {}, "requests": {}, "touched": {}},
    )


def _entry_id(hass: HomeAssistant) -> str:
    """Return the config entry a new device should belong to."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0].entry_id if entries else ""


def generate_code() -> str:
    """Return a new unambiguous pairing code."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def new_token() -> str:
    """Return a new device credential."""
    return secrets.token_hex(32).upper()


async def async_load(hass: HomeAssistant) -> None:
    """Load the device store into memory."""
    raw = (await _store(hass).async_load()) or {}
    devices = raw.get("devices")
    requests = raw.get("requests")
    hass.data.setdefault(DOMAIN, {})[DATA_DEVICES] = {
        "devices": devices if isinstance(devices, dict) else {},
        "requests": requests if isinstance(requests, dict) else {},
        "touched": {},
    }


async def async_save(hass: HomeAssistant) -> None:
    """Persist the device store."""
    data = _data(hass)
    await _store(hass).async_save(
        {"devices": data["devices"], "requests": data["requests"]}
    )


def _prune(data: dict[str, Any]) -> None:
    """Drop expired pairing requests."""
    now = _now()
    for code, record in list(data["requests"].items()):
        if record.get("expires", 0) < now and record.get("status") == PENDING:
            data["requests"].pop(code, None)


def normalize_platform(value: Any) -> str:
    """Return a supported platform identifier."""
    platform = str(value or "").strip().lower()
    return platform if platform in PLATFORMS else "unknown"


async def async_add_device(
    hass: HomeAssistant,
    name: str,
    platform: str,
    token: str | None = None,
    legacy: bool = False,
) -> dict[str, Any]:
    """Register a device and return its credential record."""
    data = _data(hass)
    device_id = uuid.uuid4().hex
    record = {
        "device_id": device_id,
        "name": str(name or "Unknown device")[:60],
        "platform": normalize_platform(platform),
        "token": token or new_token(),
        "entry_id": _entry_id(hass),
        "created": _stamp(),
        "last_seen": _stamp(),
        "legacy": bool(legacy),
    }
    data["devices"][device_id] = record
    await async_save(hass)
    return record


def find_by_token(hass: HomeAssistant, token: str) -> dict[str, Any] | None:
    """Return the device that owns a token."""
    if not token:
        return None
    for record in _data(hass)["devices"].values():
        if secrets.compare_digest(str(record.get("token", "")), token):
            return record
    return None


def find_by_id(hass: HomeAssistant, device_id: str) -> dict[str, Any] | None:
    """Return a device by id."""
    return _data(hass)["devices"].get(device_id)


async def async_touch(hass: HomeAssistant, record: dict[str, Any]) -> None:
    """Note that a device was seen, without writing on every request."""
    data = _data(hass)
    touched = data["touched"]
    now = _now()
    previous = float(touched.get(record["device_id"], 0))
    if now - previous < DEVICE_TOUCH_INTERVAL:
        return
    touched[record["device_id"]] = now
    record["last_seen"] = _stamp()
    await async_save(hass)


async def async_revoke(hass: HomeAssistant, device_id: str) -> bool:
    """Remove a device credential."""
    data = _data(hass)
    if device_id not in data["devices"]:
        return False
    data["devices"].pop(device_id, None)
    data["touched"].pop(device_id, None)
    await async_save(hass)
    return True


def list_devices(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return every registered device, newest first."""
    records = list(_data(hass)["devices"].values())
    records.sort(key=lambda item: str(item.get("created", "")), reverse=True)
    return records


async def async_create_request(
    hass: HomeAssistant,
    name: str,
    platform: str,
    app_version: str = "",
    remote: str = "",
) -> dict[str, Any]:
    """Create a pending pairing request and return it."""
    data = _data(hass)
    _prune(data)
    requests = data["requests"]
    if len(requests) >= PAIRING_REQUEST_LIMIT:
        oldest = min(requests.values(), key=lambda item: item.get("created", 0))
        requests.pop(oldest.get("device_code", ""), None)
    code = generate_code()
    while code in requests:
        code = generate_code()
    record = {
        "device_code": code,
        "name": str(name or "Unknown device")[:60],
        "platform": normalize_platform(platform),
        "app_version": str(app_version or "")[:20],
        "remote": str(remote or "")[:64],
        "entry_id": _entry_id(hass),
        "created": _now(),
        "expires": _now() + PAIRING_CODE_TTL,
        "status": PENDING,
        "token": "",
        "device_id": "",
    }
    requests[code] = record
    await async_save(hass)
    return record


def get_request(hass: HomeAssistant, code: str) -> dict[str, Any] | None:
    """Return a pairing request by code."""
    data = _data(hass)
    _prune(data)
    return data["requests"].get(str(code or "").strip().upper())


def list_requests(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return the pending pairing requests, oldest first."""
    data = _data(hass)
    _prune(data)
    records = [
        record for record in data["requests"].values() if record.get("status") == PENDING
    ]
    records.sort(key=lambda item: item.get("created", 0))
    return records


async def async_approve(hass: HomeAssistant, code: str) -> dict[str, Any] | None:
    """Approve a pending request and mint its device credential."""
    record = get_request(hass, code)
    if record is None or record.get("status") != PENDING:
        return None
    device = await async_add_device(
        hass,
        record.get("name", "Unknown device"),
        record.get("platform", "unknown"),
    )
    record["status"] = APPROVED
    record["token"] = device["token"]
    record["device_id"] = device["device_id"]
    await async_save(hass)
    return record


async def async_deny(hass: HomeAssistant, code: str) -> bool:
    """Deny a pending request."""
    record = get_request(hass, code)
    if record is None or record.get("status") != PENDING:
        return False
    record["status"] = DENIED
    record["token"] = ""
    await async_save(hass)
    return True


async def async_claim_token(hass: HomeAssistant, code: str) -> str:
    """Hand the device token to the waiting client, exactly once."""
    record = get_request(hass, code)
    if record is None or record.get("status") != APPROVED:
        return ""
    token = str(record.get("token", ""))
    if not token:
        return ""
    record["token"] = ""
    record["status"] = CONSUMED
    await async_save(hass)
    return token


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    """Return a device record without its token."""
    return {
        "device_id": record.get("device_id", ""),
        "name": record.get("name", ""),
        "platform": record.get("platform", "unknown"),
        "created": record.get("created", ""),
        "last_seen": record.get("last_seen", ""),
        "legacy": bool(record.get("legacy")),
    }


def public_request(record: dict[str, Any]) -> dict[str, Any]:
    """Return a pairing request without its token."""
    return {
        "device_code": record.get("device_code", ""),
        "name": record.get("name", ""),
        "platform": record.get("platform", "unknown"),
        "app_version": record.get("app_version", ""),
        "remote": record.get("remote", ""),
        "created": record.get("created", ""),
        "expires": record.get("expires", ""),
        "status": record.get("status", PENDING),
    }
