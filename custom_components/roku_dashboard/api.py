"""Local API consumed by every Family Dashboard client.

The canonical namespace is ``/api/family_dashboard``. The older
``/api/roku_dashboard`` namespace stays available so already-sideloaded Roku
channels keep working without a reinstall.

Clients authenticate with a per-device credential, either as an
``Authorization: Bearer`` header or as a URL path segment. Tokens in headers
are preferred: a token in the path ends up in access logs.
"""

from __future__ import annotations

import asyncio
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
import json
import logging
import mimetypes
import ipaddress
from pathlib import Path
import secrets
import time
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import callback
from homeassistant.util import dt as dt_util

from . import pairing, theme
from .const import (
    CONF_ACCESS_MODE,
    CONF_BACKGROUND,
    CONF_BACKGROUND_TYPE,
    CONF_BACKGROUND_URL,
    CONF_BACKGROUND_VERSION,
    CONF_CALENDAR_ENTITIES,
    CONF_CALENDAR_TAB_ENABLED,
    CONF_CALENDAR_SCHEDULE_DAYS,
    CONF_CALENDAR_EVENTS_PER_DAY,
    CONF_NEXT_HOLIDAY_ENABLED,
    CONF_DASHBOARD_TITLE,
    CONF_INDOOR_ENTITY,
    CONF_INDOOR_HUMIDITY_ENTITY,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    MEAL_DAY_KEYS,
    CONF_OUTDOOR_ENTITY,
    CONF_SECONDARY_WEATHER_ENTITY,
    CONF_PAIRING_CODE,
    CONF_DEVICE_TOKEN,
    CONF_WEATHER_TAB_ENABLED,
    CONF_FORECAST_TYPE,
    CONF_FORECAST_COUNT,
    CONF_LIGHTS_TAB_ENABLED,
    CONF_LIGHT_ENTITIES,
    CONF_SCENES_TAB_ENABLED,
    CONF_SCENE_ENTITIES,
    CONF_CLIMATE_TAB_ENABLED,
    CONF_CLIMATE_ENTITIES,
    CONF_SECURITY_TAB_ENABLED,
    CONF_SECURITY_COVER_ENTITIES,
    CONF_SECURITY_LOCK_ENTITIES,
    CONF_SECURITY_ALARM_ENTITY,
    CONF_SECURITY_FAMILY_ENTITIES,
    CONF_US_HOLIDAYS_ENABLED,
    CONF_US_OBSERVANCES_ENABLED,
    CONF_THEME_HEADER_TEXT,
    CONF_THEME_ITEM_HEADER_TEXT,
    CONF_THEME_BODY_TEXT,
    CONF_THEME_MUTED_TEXT,
    CONF_THEME_ACCENT,
    CONF_THEME_BACKGROUND,
    CONF_THEME_ITEM_BACKGROUND,
    CONF_THEME_SELECTED_BACKGROUND,
    CONF_THEME_SELECTED_BORDER,
    CONF_THEME_ITEM_BORDER,
    CONF_THEME_ITEM_OPACITY,
    CONF_THEME_BACKGROUND_OVERLAY,
    API_NAMESPACE,
    DATA_STREAM,
    DOMAIN,
    PAIRING_CODE_TTL,
    PAIRING_POLL_INTERVAL,
    PAYLOAD_SCHEMA_VERSION,
    THEME_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)


def _theme_color(options: dict[str, Any], key: str) -> str:
    """Return a validated theme option as a CSS-compatible hex color."""
    return theme.to_hex(options.get(key), THEME_DEFAULTS[key])


def _theme_data(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "header_text": _theme_color(options, CONF_THEME_HEADER_TEXT),
        "item_header_text": _theme_color(options, CONF_THEME_ITEM_HEADER_TEXT),
        "body_text": _theme_color(options, CONF_THEME_BODY_TEXT),
        "muted_text": _theme_color(options, CONF_THEME_MUTED_TEXT),
        "accent": _theme_color(options, CONF_THEME_ACCENT),
        "background": _theme_color(options, CONF_THEME_BACKGROUND),
        "item_background": _theme_color(options, CONF_THEME_ITEM_BACKGROUND),
        "selected_background": _theme_color(options, CONF_THEME_SELECTED_BACKGROUND),
        "selected_border": _theme_color(options, CONF_THEME_SELECTED_BORDER),
        "item_border": _theme_color(options, CONF_THEME_ITEM_BORDER),
        "item_opacity": max(0, min(100, int(options.get(CONF_THEME_ITEM_OPACITY, THEME_DEFAULTS[CONF_THEME_ITEM_OPACITY])))),
        "background_overlay": max(0, min(100, int(options.get(CONF_THEME_BACKGROUND_OVERLAY, THEME_DEFAULTS[CONF_THEME_BACKGROUND_OVERLAY])))),
    }


def _bearer_token(request) -> str:
    """Return the credential from the Authorization header."""
    header = request.headers.get("Authorization", "")
    if header[:7].lower() == "bearer ":
        return header[7:].strip()
    return ""


def _request_token(request, path_token: str = "") -> str:
    """Return the credential from the header, falling back to the URL path."""
    return _bearer_token(request) or str(path_token or "")


def _entry_for_id(hass, entry_id: str):
    """Return the config entry with an id."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == entry_id:
            return entry
    return None


def _first_entry(hass):
    """Return the first Family Dashboard config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def entry_for_pairing_code(hass, code: str):
    """Return the config entry whose short pairing code matches."""
    if not code:
        return None
    for entry in hass.config_entries.async_entries(DOMAIN):
        if secrets.compare_digest(
            str(entry.data.get(CONF_PAIRING_CODE, "")), code.upper()
        ):
            return entry
    return None


def entry_for_legacy_token(hass, token: str):
    """Return the config entry that owns the shared token used before 0.13.

    Installs that paired before per-device credentials existed only know this
    one token, so it has to keep working.
    """
    if not token:
        return None
    for entry in hass.config_entries.async_entries(DOMAIN):
        if secrets.compare_digest(
            str(entry.data.get(CONF_DEVICE_TOKEN, "")), token.upper()
        ):
            return entry
    return None


async def _resolve_client(hass, request, path_token: str = ""):
    """Return the (entry, device) a request belongs to."""
    token = _request_token(request, path_token)
    if not token:
        return None, None
    device = pairing.find_by_token(hass, token.upper())
    if device is not None:
        entry = _entry_for_id(hass, device.get("entry_id", "")) or _first_entry(hass)
        return entry, device
    return entry_for_legacy_token(hass, token), None


class FamilyDashboardDataView(HomeAssistantView):
    """Serve the dashboard payload to a paired client."""

    url = f"/api/{API_NAMESPACE}/device"
    name = "api:family_dashboard_device"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the dashboard data for the calling device."""
        entry, device = await _resolve_client(self.hass, request)
        if entry is None:
            return self.json({"error": "invalid_token"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
        payload = await async_dashboard_payload(self.hass, entry)
        if device is not None:
            await pairing.async_touch(self.hass, device)
            payload["device_id"] = device["device_id"]
        return self.json(payload)


class FamilyDashboardTokenDataView(HomeAssistantView):
    """Serve the dashboard payload when the credential is part of the URL."""

    url = f"/api/{API_NAMESPACE}/{{token}}"
    name = "api:family_dashboard_token"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request, token: str = ""):
        """Return the dashboard data for the calling device."""
        entry, device = await _resolve_client(self.hass, request, token)
        if entry is None:
            return self.json({"error": "invalid_token"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
        payload = await async_dashboard_payload(self.hass, entry)
        if device is not None:
            await pairing.async_touch(self.hass, device)
            payload["device_id"] = device["device_id"]
        return self.json(payload)


class FamilyDashboardActionView(HomeAssistantView):
    """Run dashboard control commands for a paired client."""

    url = f"/api/{API_NAMESPACE}/device/action"
    name = "api:family_dashboard_device_action"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def post(self, request):
        """Execute an allowlisted dashboard command."""
        entry, _device = await _resolve_client(self.hass, request)
        if entry is None:
            return self.json({"error": "invalid_token"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "invalid_json"}, status_code=400)

        result, status = await async_execute_action(self.hass, entry, body)
        return self.json(result, status_code=status)


class FamilyDashboardBackgroundView(HomeAssistantView):
    """Serve the uploaded background to a paired client."""

    url = f"/api/{API_NAMESPACE}/device/background"
    name = "api:family_dashboard_device_background"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the uploaded background image."""
        entry, _device = await _resolve_client(self.hass, request)
        if entry is None:
            return self.json({"error": "invalid_token"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
        return await _background_response(self.hass, entry)


class RokuDashboardView(HomeAssistantView):
    """Serve only dashboard-selected data to a paired Roku on the LAN."""

    url = "/api/roku_dashboard/{code}"
    name = "api:roku_dashboard"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request, code: str):
        token = _request_token(request, code)
        entry = self._entry_for_code(token)
        if entry is None:
            return self.json({"error": "invalid_pairing_code"}, status_code=401)
        is_pairing = secrets.compare_digest(
            str(entry.data.get(CONF_PAIRING_CODE, "")), token.upper()
        )
        if not request_allowed(request, entry, pairing=is_pairing):
            return self.json({"error": "network_access_denied"}, status_code=403)

        payload = await async_dashboard_payload(self.hass, entry)

        # Exchange the human-friendly code once for a strong device token,
        # then rotate the short code. Control POSTs never accept short codes.
        if is_pairing:
            device = await pairing.async_add_device(
                self.hass, "Roku", "roku", legacy=True
            )
            payload["device_token"] = device["token"]
            payload["device_id"] = device["device_id"]
            data = dict(entry.data)
            data[CONF_PAIRING_CODE] = secrets.token_hex(4).upper()
            self.hass.config_entries.async_update_entry(entry, data=data)
        return self.json(payload)

    def _entry_for_code(self, code: str):
        return entry_for_code(self.hass, code)

    async def post(self, request, code: str):
        """Execute an allowlisted dashboard command."""
        token = _request_token(request, code)
        entry = self._entry_for_code(token)
        if entry is None:
            return self.json({"error": "invalid_pairing_code"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
        if not self._is_credential(entry, token):
            return self.json({"error": "pairing_required"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "invalid_json"}, status_code=400)

        result, status = await async_execute_action(self.hass, entry, body)
        return self.json(result, status_code=status)

    def _is_credential(self, entry, token: str) -> bool:
        """Return True when the token is a device credential, not a short code."""
        if secrets.compare_digest(
            str(entry.data.get(CONF_DEVICE_TOKEN, "")), token.upper()
        ):
            return True
        return pairing.find_by_token(self.hass, token.upper()) is not None


class FamilyDashboardPairingRequestView(HomeAssistantView):
    """Start a device-initiated pairing request.

    The client shows the returned code and waits for an administrator to
    approve it in the Home Assistant panel. This is the only pairing flow
    that works on a device without a keyboard, such as Apple TV.
    """

    url = f"/api/{API_NAMESPACE}/pairing/request"
    name = "api:family_dashboard_pairing_request"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def post(self, request):
        """Create a pending pairing request."""
        entry = _first_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        if not request_allowed(request, entry, pairing=True):
            return self.json({"error": "network_access_denied"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        record = await pairing.async_create_request(
            self.hass,
            name=body.get("device_name") or body.get("name") or "",
            platform=body.get("platform") or body.get("device_type") or "",
            app_version=body.get("app_version") or "",
            remote=request.remote or "",
        )
        return self.json(
            {
                "device_code": record["device_code"],
                "expires_in": PAIRING_CODE_TTL,
                "poll_interval": PAIRING_POLL_INTERVAL,
            }
        )


class FamilyDashboardPairingStatusView(HomeAssistantView):
    """Report the state of a pairing request."""

    url = f"/api/{API_NAMESPACE}/pairing/status"
    name = "api:family_dashboard_pairing_status"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the status of a pairing request."""
        code = request.query.get("device_code", "")
        record = pairing.get_request(self.hass, code)
        if record is None:
            return self.json({"error": "unknown_device_code"}, status_code=404)
        # The poll hands out the device credential, so it follows the same
        # network policy as the request that started the pairing.
        entry = _entry_for_id(self.hass, record.get("entry_id", "")) or _first_entry(
            self.hass
        )
        if entry is None or not request_allowed(request, entry, pairing=True):
            return self.json({"error": "network_access_denied"}, status_code=403)
        status = record.get("status")
        body: dict[str, Any] = {"status": status}
        if status == pairing.APPROVED:
            token = await pairing.async_claim_token(self.hass, code)
            body["status"] = "approved"
            body["device_token"] = token
        body["expires_in"] = max(
            0, int(float(record.get("expires", 0)) - time.time())
        )
        return self.json(body)


class FamilyDashboardPairingCodeView(HomeAssistantView):
    """Exchange the legacy short pairing code for a device credential.

    Devices with a keyboard can still type the short code shown in Home
    Assistant. New clients should prefer the device-initiated flow.
    """

    url = f"/api/{API_NAMESPACE}/pairing/code"
    name = "api:family_dashboard_pairing_code"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def post(self, request):
        """Trade the short pairing code for a device credential."""
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}
        code = str(body.get("code", "")).strip().upper()
        entry = entry_for_pairing_code(self.hass, code)
        if entry is None:
            return self.json({"error": "invalid_pairing_code"}, status_code=401)
        if not request_allowed(request, entry, pairing=True):
            return self.json({"error": "network_access_denied"}, status_code=403)
        device = await pairing.async_add_device(
            self.hass,
            body.get("device_name") or "Unknown device",
            body.get("platform") or "unknown",
        )
        # Rotate the short code so it cannot be reused.
        data = dict(entry.data)
        data[CONF_PAIRING_CODE] = secrets.token_hex(4).upper()
        self.hass.config_entries.async_update_entry(entry, data=data)
        return self.json(
            {"device_token": device["token"], "device_id": device["device_id"]}
        )


class StreamHub:
    """Fan dashboard updates out to the connected clients."""

    def __init__(self) -> None:
        """Start with no subscribers."""
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        """Register a new subscriber."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Drop a subscriber."""
        self._subscribers.discard(queue)

    def publish(self, event: str, data: dict[str, Any]) -> None:
        """Send an event to every subscriber."""
        for queue in list(self._subscribers):
            try:
                queue.put_nowait((event, data))
            except asyncio.QueueFull:
                # A slow client loses the oldest update, never the stream.
                try:
                    queue.get_nowait()
                    queue.put_nowait((event, data))
                except asyncio.QueueEmpty:  # pragma: no cover - race guard
                    pass


def stream_hub(hass) -> StreamHub:
    """Return the stream hub for this Home Assistant instance."""
    data = hass.data.setdefault(DOMAIN, {})
    hub = data.get(DATA_STREAM)
    if hub is None:
        hub = StreamHub()
        data[DATA_STREAM] = hub
    return hub


async def _sse_write(response, event: str, data: dict[str, Any]) -> None:
    """Write one server-sent event."""
    payload = json.dumps(data, default=str)
    await response.write(f"event: {event}\ndata: {payload}\n\n".encode())


def tracked_entities(entry) -> set[str]:
    """Return the entity ids the dashboard displays."""
    options = entry.options
    entity_ids: set[str] = set()
    for key in (
        CONF_INDOOR_ENTITY,
        CONF_INDOOR_HUMIDITY_ENTITY,
        CONF_OUTDOOR_ENTITY,
        CONF_MEAL_ENTITY,
    ):
        value = str(options.get(key, "") or "")
        if value:
            entity_ids.add(value)
    for key in (CONF_LIGHT_ENTITIES, CONF_SCENE_ENTITIES, CONF_CLIMATE_ENTITIES):
        entity_ids.update(_as_list(options.get(key, [])))
    return entity_ids


class FamilyDashboardStreamView(HomeAssistantView):
    """Push dashboard updates to a paired client over server-sent events.

    Home Assistant's own websocket API needs a long-lived access token, which
    is far too much authority to hand a television. This stream is scoped to
    the entities the dashboard already shows.
    """

    url = f"/api/{API_NAMESPACE}/stream"
    name = "api:family_dashboard_stream"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Stream updates until the client disconnects."""
        entry, device = await _resolve_client(self.hass, request)
        if entry is None:
            return self.json({"error": "invalid_token"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)

        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-store",
                "Connection": "keep-alive",
                # Stop reverse proxies from buffering the stream.
                "X-Accel-Buffering": "no",
            },
        )
        await response.prepare(request)
        hub = stream_hub(self.hass)
        queue = hub.subscribe()
        try:
            payload = await async_dashboard_payload(self.hass, entry)
            if device is not None:
                payload["device_id"] = device["device_id"]
                await pairing.async_touch(self.hass, device)
            await _sse_write(response, "dashboard", payload)
            while True:
                try:
                    event, data = await asyncio.wait_for(queue.get(), timeout=25)
                except asyncio.TimeoutError:
                    await response.write(b": keepalive\n\n")
                    continue
                await _sse_write(response, event, data)
        except (ConnectionResetError, ConnectionAbortedError):
            _LOGGER.debug("Family Dashboard stream client disconnected")
        finally:
            hub.unsubscribe(queue)
        return response


async def setup_state_stream(hass, entry) -> None:
    """Publish state changes for the dashboard entities to stream clients."""
    from homeassistant.const import EVENT_STATE_CHANGED

    @callback
    def _handle(event) -> None:
        """Forward a state change to the connected clients."""
        entity_id = event.data.get("entity_id")
        if not entity_id or entity_id not in tracked_entities(entry):
            return
        new_state = event.data.get("new_state")
        stream_hub(hass).publish(
            "state",
            {
                "entity_id": entity_id,
                "domain": entity_id.split(".", 1)[0],
                "state": new_state.state if new_state else "unavailable",
                "attributes": dict(new_state.attributes) if new_state else {},
            },
        )

    entry.async_on_unload(hass.bus.async_listen(EVENT_STATE_CHANGED, _handle))


def _as_list(value: Any) -> list[str]:
    """Return a list for list-ish option values."""
    if isinstance(value, str):
        return [value]
    return list(value or [])


def _meal_data(
    hass, options: dict[str, Any], fallback_entity: str
) -> tuple[str, list[dict[str, Any]]]:
    """Build today's meal and a Monday-Sunday plan with helper fallback."""
    day_names = [
        "Monday", "Tuesday", "Wednesday", "Thursday",
        "Friday", "Saturday", "Sunday",
    ]
    meals = [str(options.get(key, "") or "").strip() for key in MEAL_DAY_KEYS]
    fallback = ""
    state = hass.states.get(fallback_entity) if fallback_entity else None
    if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
        fallback = state.state.strip()

    if not any(meals) and fallback:
        # Accept lines such as "Monday: Tacos" from the legacy helper.
        for line in fallback.splitlines():
            left, separator, right = line.partition(":")
            if not separator:
                continue
            for index, day in enumerate(day_names):
                if left.strip().lower() in (day.lower(), day[:3].lower()):
                    meals[index] = right.strip()
        if not any(meals):
            meals[dt_util.now().weekday()] = fallback

    today_index = dt_util.now().weekday()
    weekly = [
        {
            "day": day,
            "meal": meals[index],
            "is_today": index == today_index,
        }
        for index, day in enumerate(day_names)
    ]
    return meals[today_index] or "No meal planned", weekly


def _entity_cards(hass, configured: Any) -> list[dict[str, Any]]:
    """Build light/scene cards for the configured entities."""
    cards: list[dict[str, Any]] = []
    for entity_id in _as_list(configured):
        state = hass.states.get(entity_id)
        if state is None:
            continue
        cards.append(
            {
                "entity_id": entity_id,
                "name": state.attributes.get("friendly_name", entity_id),
                "state": state.state,
                "brightness": state.attributes.get("brightness"),
                "color_temp_kelvin": state.attributes.get("color_temp_kelvin"),
            }
        )
    return cards


def _security_data(hass, options: dict[str, Any]) -> dict[str, Any]:
    """Build the allowlisted security controls and family presence list."""
    def cards(configured: Any, limit: int) -> list[dict[str, Any]]:
        result = []
        for entity_id in _as_list(configured)[:limit]:
            state = hass.states.get(entity_id)
            if state is None:
                continue
            result.append({
                "entity_id": entity_id,
                "name": state.attributes.get("friendly_name", entity_id),
                "state": state.state,
            })
        return result

    family = []
    for entity_id in _as_list(options.get(CONF_SECURITY_FAMILY_ENTITIES, [])):
        state = hass.states.get(entity_id)
        if state is None:
            continue
        family.append({
            "entity_id": entity_id,
            "name": state.attributes.get("friendly_name", entity_id),
            "state": state.state,
            "home": state.state == "home",
        })

    alarm_id = options.get(CONF_SECURITY_ALARM_ENTITY, "")
    alarm = None
    if alarm_id:
        state = hass.states.get(alarm_id)
        if state is not None:
            alarm = {
                "entity_id": alarm_id,
                "name": state.attributes.get("friendly_name", alarm_id),
                "state": state.state,
                "states": state.attributes.get("code_arm_required", False),
            }
    return {
        "garage_doors": cards(options.get(CONF_SECURITY_COVER_ENTITIES, []), 2),
        "locks": cards(options.get(CONF_SECURITY_LOCK_ENTITIES, []), 4),
        "alarm": alarm,
        "family": family,
    }


def _climate_cards(hass, configured: Any) -> list[dict[str, Any]]:
    """Build thermostat cards for the configured climate entities."""
    cards: list[dict[str, Any]] = []
    for entity_id in _as_list(configured):
        state = hass.states.get(entity_id)
        if state is None:
            continue
        attrs = state.attributes
        cards.append(
            {
                "entity_id": entity_id,
                "name": attrs.get("friendly_name", entity_id),
                "state": state.state,
                "current_temperature": attrs.get("current_temperature"),
                "temperature": attrs.get("temperature"),
                "target_temp_low": attrs.get("target_temp_low"),
                "target_temp_high": attrs.get("target_temp_high"),
                "humidity": attrs.get("humidity"),
                "hvac_action": attrs.get("hvac_action"),
                "hvac_modes": attrs.get("hvac_modes", []),
                "min_temp": attrs.get("min_temp"),
                "max_temp": attrs.get("max_temp"),
                "target_temp_step": attrs.get("target_temp_step", 1),
            }
        )
    return cards


async def _weather_data(
    hass, entity_id: str, options: dict[str, Any]
) -> dict[str, Any]:
    """Return current conditions and a normalized HA forecast."""
    if not options.get(CONF_WEATHER_TAB_ENABLED, True):
        return {"enabled": False}
    state = hass.states.get(entity_id) if entity_id else None
    if state is None:
        return {"enabled": True, "available": False, "forecast": []}

    forecast_type = options.get(CONF_FORECAST_TYPE, "daily")
    count = options.get(CONF_FORECAST_COUNT, 5)
    forecasts: list[dict[str, Any]] = []
    try:
        response = await hass.services.async_call(
            "weather",
            "get_forecasts",
            {"entity_id": entity_id, "type": forecast_type},
            blocking=True,
            return_response=True,
        )
        raw_items = (response or {}).get(entity_id, {}).get("forecast", [])
        for item in raw_items[:count]:
            forecast_datetime = item.get("datetime", "")
            parsed = dt_util.parse_datetime(forecast_datetime) if forecast_datetime else None
            if parsed is not None:
                parsed = dt_util.as_local(parsed)
                forecast_label = (
                    parsed.strftime("%a %I %p").replace(" 0", " ")
                    if forecast_type == "hourly"
                    else parsed.strftime("%a").upper()
                )
            else:
                forecast_label = ""
            forecasts.append(
                {
                    "datetime": forecast_datetime,
                    "label": forecast_label,
                    "condition": item.get("condition", "unknown"),
                    "temperature": item.get("temperature"),
                    "templow": item.get("templow"),
                    "precipitation_probability": item.get(
                        "precipitation_probability"
                    ),
                    "wind_speed": item.get("wind_speed"),
                }
            )
    except Exception:
        _LOGGER.exception("Unable to fetch Roku dashboard weather forecast")

    attrs = state.attributes
    return {
        "enabled": True,
        "available": state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE),
        "entity_id": entity_id,
        "name": attrs.get("friendly_name", "Weather"),
        "condition": state.state,
        "temperature": attrs.get("temperature"),
        "temperature_unit": attrs.get("temperature_unit", ""),
        "humidity": attrs.get("humidity"),
        "pressure": attrs.get("pressure"),
        "wind_speed": attrs.get("wind_speed"),
        "wind_bearing": attrs.get("wind_bearing"),
        "visibility": attrs.get("visibility"),
        "forecast_type": forecast_type,
        "forecast": forecasts,
    }


async def _calendar_data(
    hass,
    calendars: list[str],
    include_us_holidays: bool,
    include_us_observances: bool,
    schedule_days: int,
    events_per_day: int,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    """Return today's agenda, a month grid and the rolling schedule."""
    if not calendars:
        calendars = [
            state.entity_id
            for state in hass.states.async_all(["calendar"])
        ]
    now = dt_util.now()
    today_date = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        month_end = month_start.replace(year=now.year + 1, month=1)
    else:
        month_end = month_start.replace(month=now.month + 1)
    schedule_end_date = today_date + timedelta(days=schedule_days)
    schedule_end = now.replace(
        year=schedule_end_date.year,
        month=schedule_end_date.month,
        day=schedule_end_date.day,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    fetch_end = max(month_end, schedule_end)

    response = {}
    if calendars:
        try:
            response = await hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendars,
                    "start_date_time": month_start.isoformat(),
                    "end_date_time": fetch_end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except Exception:
            _LOGGER.exception("Unable to fetch Roku dashboard calendar events")

    palette = ["E87979", "69A7E8", "70BF86", "D18BE3", "E6A85C", "58BFC2", "C58A6A"]
    output: list[dict[str, Any]] = []
    for calendar_index, (calendar_id, calendar_data) in enumerate(
        (response or {}).items()
    ):
        state = hass.states.get(calendar_id)
        calendar_name = (
            state.attributes.get("friendly_name", calendar_id)
            if state is not None
            else calendar_id
        )
        color = palette[calendar_index % len(palette)]
        for event in calendar_data.get("events", []):
            start_value = event.get("start", "")
            output.append(
                {
                    "title": event.get("summary", "Untitled"),
                    "start": start_value,
                    "all_day": "T" not in start_value,
                    "calendar_id": calendar_id,
                    "calendar_name": calendar_name,
                    "color": color,
                }
            )

    generated: list[tuple[date, str, str, str]] = []
    years = {month_start.year, fetch_end.year, today_date.year + 1}
    if include_us_holidays:
        for year in years:
            generated.extend((event_date, title, "calendar.us_holidays", "US Holidays") for event_date, title in _us_federal_holidays(year))
    if include_us_observances:
        for year in years:
            generated.extend((event_date, title, "calendar.us_observances", "US Observances") for event_date, title in _us_observances(year))
    for event_date, title, calendar_id, calendar_name in generated:
        if month_start.date() <= event_date < fetch_end.date():
            output.append(
                {
                    "title": title,
                    "start": event_date.isoformat(),
                    "all_day": True,
                    "calendar_id": calendar_id,
                    "calendar_name": calendar_name,
                    "color": "E5A84B",
                }
            )

    # Remove exact generated duplicates while preserving separate calendars.
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in output:
        key = (item["start"], item["title"], item["calendar_id"])
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    output = sorted(deduped, key=lambda item: item["start"])

    month_prefix = f"{now.year:04d}-{now.month:02d}-"
    month_events = [item for item in output if item["start"].startswith(month_prefix)]
    event_days = sorted({int(item["start"][8:10]) for item in month_events})
    today = today_date.isoformat()
    todays_events = [item for item in output if item["start"][:10] == today]
    next_holiday = None
    holiday_candidates = sorted(
        (event_date, title)
        for event_date, title, calendar_id, _calendar_name in generated
        if calendar_id in ("calendar.us_holidays", "calendar.us_observances")
        and event_date >= today_date
    )
    if holiday_candidates:
        event_date, title = holiday_candidates[0]
        next_holiday = {
            "title": title,
            "start": event_date.isoformat(),
            "all_day": True,
        }

    schedule_columns = []
    for offset in range(schedule_days):
        current = today_date + timedelta(days=offset)
        current_iso = current.isoformat()
        day_events = [
            item for item in output if item["start"][:10] == current_iso
        ]
        schedule_columns.append(
            {
                "date": current_iso,
                "weekday": current.strftime("%a").upper(),
                "day": current.day,
                "month": current.strftime("%b").upper(),
                "is_today": offset == 0,
                "is_weekend": current.weekday() >= 5,
                "events": day_events[:events_per_day],
                "overflow": max(0, len(day_events) - events_per_day),
            }
        )

    days_in_month = monthrange(now.year, now.month)[1]
    first_weekday = (month_start.weekday() + 1) % 7
    month = {
        "title": now.strftime("%B %Y"),
        "year": now.year,
        "month": now.month,
        "today": now.day,
        "days_in_month": days_in_month,
        "first_weekday": first_weekday,
        "event_days": event_days,
        "events": month_events,
        "next_holiday": next_holiday,
    }
    schedule = {
        "title": f"{today_date.strftime('%B')} {today_date.day}",
        "days": schedule_columns,
        "day_count": schedule_days,
        "events_per_day": events_per_day,
    }
    return todays_events, month, schedule


def _us_federal_holidays(year: int) -> list[tuple[date, str]]:
    """Calculate US federal holidays without an external dependency."""
    holidays: list[tuple[date, str]] = []

    def add_fixed(month: int, day: int, name: str) -> None:
        actual = date(year, month, day)
        holidays.append((actual, name))
        if actual.weekday() == 5:  # Saturday -> Friday
            holidays.append((actual - timedelta(days=1), f"{name} (observed)"))
        elif actual.weekday() == 6:  # Sunday -> Monday
            holidays.append((actual + timedelta(days=1), f"{name} (observed)"))

    def nth_weekday(month: int, weekday: int, occurrence: int) -> date:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + (occurrence - 1) * 7)

    def last_weekday(month: int, weekday: int) -> date:
        last = date(year, month, monthrange(year, month)[1])
        return last - timedelta(days=(last.weekday() - weekday) % 7)

    add_fixed(1, 1, "New Year's Day")
    holidays.append((nth_weekday(1, 0, 3), "Martin Luther King Jr. Day"))
    holidays.append((nth_weekday(2, 0, 3), "Washington's Birthday"))
    holidays.append((last_weekday(5, 0), "Memorial Day"))
    add_fixed(6, 19, "Juneteenth National Independence Day")
    add_fixed(7, 4, "Independence Day")
    holidays.append((nth_weekday(9, 0, 1), "Labor Day"))
    holidays.append((nth_weekday(10, 0, 2), "Columbus Day"))
    add_fixed(11, 11, "Veterans Day")
    holidays.append((nth_weekday(11, 3, 4), "Thanksgiving Day"))
    add_fixed(12, 25, "Christmas Day")
    return holidays


def _us_observances(year: int) -> list[tuple[date, str]]:
    """Calculate common US cultural and family observances."""

    def nth_weekday(month: int, weekday: int, occurrence: int) -> date:
        first = date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + timedelta(days=offset + (occurrence - 1) * 7)

    # Anonymous Gregorian algorithm (Meeus/Jones/Butcher) for Easter.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    length = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * length) // 451
    easter_month = (h + length - 7 * m + 114) // 31
    easter_day = ((h + length - 7 * m + 114) % 31) + 1
    easter = date(year, easter_month, easter_day)

    return [
        (date(year, 2, 2), "Groundhog Day"),
        (date(year, 2, 14), "Valentine's Day"),
        (easter - timedelta(days=47), "Mardi Gras"),
        (date(year, 3, 17), "St. Patrick's Day"),
        (date(year, 4, 1), "April Fools' Day"),
        (easter, "Easter Sunday"),
        (nth_weekday(5, 6, 2), "Mother's Day"),
        (date(year, 6, 14), "Flag Day"),
        (nth_weekday(6, 6, 3), "Father's Day"),
        (date(year, 10, 31), "Halloween"),
        (date(year, 12, 31), "New Year's Eve"),
    ]


async def async_dashboard_payload(hass, entry) -> dict[str, Any]:
    """Build the dashboard payload for a config entry."""
    options = entry.options
    indoor = options.get(CONF_INDOOR_ENTITY, "")
    indoor_humidity = options.get(CONF_INDOOR_HUMIDITY_ENTITY, "")
    outdoor = options.get(CONF_OUTDOOR_ENTITY, "")
    secondary_weather = options.get(CONF_SECONDARY_WEATHER_ENTITY, "")
    meal = options.get(CONF_MEAL_ENTITY, "")
    calendars = options.get(CONF_CALENDAR_ENTITIES, [])
    if isinstance(calendars, str):
        calendars = [calendars]

    states: dict[str, Any] = {}
    for entity_id in (indoor, indoor_humidity, outdoor, meal):
        state = hass.states.get(entity_id) if entity_id else None
        if state is not None:
            states[entity_id] = {
                "state": state.state,
                "attributes": dict(state.attributes),
            }

    meal_plan, weekly_meals = _meal_data(hass, options, meal)

    events, month, schedule = await _calendar_data(
        hass,
        calendars,
        options.get(CONF_US_HOLIDAYS_ENABLED, True),
        options.get(CONF_US_OBSERVANCES_ENABLED, True),
        options.get(CONF_CALENDAR_SCHEDULE_DAYS, 7),
        options.get(CONF_CALENDAR_EVENTS_PER_DAY, 5),
    )
    weather = await _weather_data(hass, outdoor, options)
    secondary_weather_data = {}
    if secondary_weather and options.get(CONF_FORECAST_COUNT, 5) <= 5:
        secondary_weather_data = await _weather_data(hass, secondary_weather, options)
    lights = _entity_cards(hass, options.get(CONF_LIGHT_ENTITIES, []))
    scenes = _entity_cards(hass, options.get(CONF_SCENE_ENTITIES, []))
    climates = _climate_cards(hass, options.get(CONF_CLIMATE_ENTITIES, []))
    security = _security_data(hass, options)
    return {
        "ok": True,
        "schema_version": PAYLOAD_SCHEMA_VERSION,
        "server_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dashboard_id": entry.entry_id,
        "access_mode": options.get(CONF_ACCESS_MODE, "lan"),
        "title": options.get(CONF_DASHBOARD_TITLE, "Family Dashboard"),
        "theme": _theme_data(options),
        "capabilities": {
            "actions": [
                "meal_week",
                "light_toggle",
                "light_brightness",
                "scene_activate",
                "climate_temperature",
                "climate_mode",
                "security_cover_toggle",
                "security_lock_toggle",
                "security_alarm_command",
            ],
            "stream": True,
            "background": True,
            "theme": True,
            "weekly_meals": True,
            "schedule": True,
        },
        "states": states,
        "resolved_entities": {
            "inside": indoor,
            "inside_humidity": indoor_humidity,
            "outside": outdoor,
        },
        "meal_plan": meal_plan,
        "weekly_meal_plan": weekly_meals,
        "calendar_events": events[:3],
        "today_events": events,
        "month_calendar": month,
        "calendar_schedule": schedule,
        "next_holiday": month.get("next_holiday") if options.get(CONF_NEXT_HOLIDAY_ENABLED, True) else None,
        "background": options.get(CONF_BACKGROUND, "fall"),
        "background_url": options.get(CONF_BACKGROUND_URL, ""),
        "background_version": options.get(CONF_BACKGROUND_VERSION, ""),
        "has_uploaded_background": bool(options.get(CONF_BACKGROUND_VERSION)),
        "layout": options.get(CONF_LAYOUT, "home"),
        "weather": weather,
        "secondary_weather": secondary_weather_data,
        "tabs": {
            "calendar": options.get(CONF_CALENDAR_TAB_ENABLED, True),
            "weather": options.get(CONF_WEATHER_TAB_ENABLED, True),
            "lights": options.get(CONF_LIGHTS_TAB_ENABLED, True),
            "scenes": options.get(CONF_SCENES_TAB_ENABLED, True),
            "climate": options.get(CONF_CLIMATE_TAB_ENABLED, True),
            "security": options.get(CONF_SECURITY_TAB_ENABLED, True),
        },
        "lights": lights,
        "scenes": scenes,
        "climates": climates,
        "security": security,
    }


async def async_execute_action(
    hass, entry, body: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """Execute an allowlisted dashboard command for a config entry."""
    action = str(body.get("action", ""))
    entity_id = str(body.get("entity_id", ""))
    options = entry.options
    if action == "meal_week":
        values = body.get("value")
        if not isinstance(values, list) or len(values) != 7:
            return {"error": "invalid_meal_plan"}, 400
        updated = dict(options)
        for index, key in enumerate(MEAL_DAY_KEYS):
            updated[key] = str(values[index] or "").strip()[:120]
        hass.config_entries.async_update_entry(entry, options=updated)
        return {"ok": True}, 200
    lights = _as_list(options.get(CONF_LIGHT_ENTITIES, []))
    scenes = _as_list(options.get(CONF_SCENE_ENTITIES, []))
    climates = _as_list(options.get(CONF_CLIMATE_ENTITIES, []))
    security_covers = _as_list(options.get(CONF_SECURITY_COVER_ENTITIES, []))[:2]
    security_locks = _as_list(options.get(CONF_SECURITY_LOCK_ENTITIES, []))[:4]
    security_alarm = options.get(CONF_SECURITY_ALARM_ENTITY, "")

    domain = ""
    service = ""
    data: dict[str, Any] = {"entity_id": entity_id}
    if action == "light_toggle" and entity_id in lights:
        domain = entity_id.split(".", 1)[0]
        if domain not in ("light", "switch"):
            return {"error": "not_allowed"}, 403
        service = "toggle"
    elif action == "light_brightness" and entity_id in lights:
        domain, service = "light", "turn_on"
        data["brightness_pct"] = max(1, min(100, int(body.get("value", 100))))
    elif action == "scene_activate" and entity_id in scenes:
        domain = entity_id.split(".", 1)[0]
        if domain not in ("scene", "script"):
            return {"error": "not_allowed"}, 403
        service = "turn_on"
    elif action == "climate_temperature" and entity_id in climates:
        domain, service = "climate", "set_temperature"
        data["temperature"] = float(body.get("value"))
    elif action == "climate_mode" and entity_id in climates:
        state = hass.states.get(entity_id)
        mode = str(body.get("value", ""))
        if state is None or mode not in state.attributes.get("hvac_modes", []):
            return {"error": "invalid_mode"}, 400
        domain, service = "climate", "set_hvac_mode"
        data["hvac_mode"] = mode
    elif action == "security_cover_toggle" and entity_id in security_covers:
        domain, service = "cover", "toggle"
    elif action == "security_lock_toggle" and entity_id in security_locks:
        domain, service = "lock", "toggle"
    elif action == "security_alarm_command" and entity_id == security_alarm:
        command = str(body.get("command", ""))
        if command not in ("alarm_disarm", "alarm_arm_home", "alarm_arm_away"):
            return {"error": "invalid_command"}, 400
        domain, service = "alarm_control_panel", command
    else:
        return {"error": "not_allowed"}, 403

    try:
        await hass.services.async_call(domain, service, data, blocking=True)
    except Exception:
        _LOGGER.exception("Roku dashboard command failed")
        return {"error": "service_failed"}, 500
    return {"ok": True}, 200


class RokuDashboardActionView(RokuDashboardView):
    """Route control commands to the shared allowlisted action handler."""

    url = "/api/roku_dashboard/{code}/action"
    name = "api:roku_dashboard_action"


def entry_for_code(hass, code: str):
    """Resolve a config entry by short pairing code or device credential."""
    if not code:
        return None
    token = code.upper()
    for item in hass.config_entries.async_entries(DOMAIN):
        if secrets.compare_digest(
            str(item.data.get(CONF_PAIRING_CODE, "")), token
        ):
            return item
        if secrets.compare_digest(
            str(item.data.get(CONF_DEVICE_TOKEN, "")), token
        ):
            return item
    device = pairing.find_by_token(hass, token)
    if device is not None:
        return _entry_for_id(hass, device.get("entry_id", "")) or _first_entry(hass)
    return None


def request_allowed(request, entry, pairing: bool) -> bool:
    """Enforce LAN/Tailscale/external policy for paired API requests."""
    try:
        address = ipaddress.ip_address(request.remote or "")
    except ValueError:
        return False
    is_lan = address.is_private or address.is_loopback or address.is_link_local
    is_tailscale = address in ipaddress.ip_network("100.64.0.0/10")
    if pairing:
        return is_lan or is_tailscale
    mode = entry.options.get(CONF_ACCESS_MODE, "lan")
    if is_lan:
        return True
    if is_tailscale:
        return mode in ("tailscale", "external")
    if mode != "external":
        return False
    return request.secure or request.headers.get("X-Forwarded-Proto") == "https"


async def _background_response(hass, entry):
    """Return the uploaded background image for a paired client."""
    path = Path(hass.config.path("roku_dashboard", "background"))
    if not path.is_file():
        return web.json_response({"error": "no_background"}, status=404)
    content_type = (
        entry.options.get(CONF_BACKGROUND_TYPE)
        or mimetypes.guess_type(entry.options.get("background_name", path.name))[0]
        or "image/jpeg"
    )
    return web.FileResponse(
        path,
        headers={"Content-Type": content_type, "Cache-Control": "no-store"},
    )


class RokuDashboardBackgroundView(HomeAssistantView):
    """Serve the uploaded background to a paired client."""

    url = "/api/roku_dashboard/{code}/background"
    name = "api:roku_dashboard_background"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request, code: str):
        entry = entry_for_code(self.hass, code)
        if entry is None:
            return self.json({"error": "invalid_pairing_code"}, status_code=401)
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
        return await _background_response(self.hass, entry)
