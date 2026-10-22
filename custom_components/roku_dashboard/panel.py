"""Home Assistant frontend panel for the Family Dashboard.

The panel adds a "Family Dashboard" entry to the Home Assistant sidebar
(hamburger) menu. It renders the same dashboard as the web app and lets
administrators change the dashboard configuration without leaving Home
Assistant.
"""

from __future__ import annotations

import inspect
import logging
import mimetypes
from pathlib import Path
from typing import Any

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .api import async_dashboard_payload, async_execute_action
from . import pairing, theme
from .const import (
    BACKGROUNDS,
    CONF_BACKGROUND,
    CONF_BACKGROUND_URL,
    CONF_BACKGROUND_VERSION,
    CONF_CALENDAR_ENTITIES,
    CONF_CALENDAR_TAB_ENABLED,
    CONF_CLIMATE_ENTITIES,
    CONF_CLIMATE_TAB_ENABLED,
    CONF_DASHBOARD_TITLE,
    CONF_DEVICE_TOKEN,
    CONF_INDOOR_ENTITY,
    CONF_INDOOR_HUMIDITY_ENTITY,
    CONF_LEGACY_TOKEN_REVOKED,
    CONF_LAYOUT,
    CONF_LIGHT_ENTITIES,
    CONF_LIGHTS_TAB_ENABLED,
    CONF_MEAL_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_SCENE_ENTITIES,
    CONF_SCENES_TAB_ENABLED,
    CONF_WEATHER_TAB_ENABLED,
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
    DOMAIN,
    LAYOUTS,
    MEAL_DAY_KEYS,
    PANEL_ELEMENT_NAME,
    PANEL_ICON,
    PANEL_JS_URL,
    PANEL_URL_PATH,
    THEME_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)

# Options the panel is allowed to change.
_TOGGLE_OPTIONS = (
    CONF_WEATHER_TAB_ENABLED,
    CONF_CALENDAR_TAB_ENABLED,
    CONF_LIGHTS_TAB_ENABLED,
    CONF_SCENES_TAB_ENABLED,
    CONF_CLIMATE_TAB_ENABLED,
)


def _config_entry(hass: HomeAssistant):
    """Return the first Family Dashboard config entry."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _is_admin(request) -> bool:
    """Return True when the request is made by an admin user."""
    user = request.get("hass_user")
    return bool(user and user.is_admin)


def _entity_exists(hass: HomeAssistant, entity_id: str) -> bool:
    """Return True when the entity is known to Home Assistant."""
    if not entity_id:
        return False
    if hass.states.get(entity_id) is not None:
        return True
    return er.async_get(hass).async_get(entity_id) is not None


def _clean_entity(
    hass: HomeAssistant, value: Any, domains: tuple[str, ...]
) -> str:
    """Return a single valid entity id (or an empty string)."""
    entity_id = str(value or "").strip()
    if "." not in entity_id:
        return ""
    if entity_id.split(".", 1)[0] not in domains:
        return ""
    return entity_id if _entity_exists(hass, entity_id) else ""


def _clean_entities(
    hass: HomeAssistant, value: Any, domains: tuple[str, ...]
) -> list[str]:
    """Return the valid entity ids of a list option."""
    if isinstance(value, str):
        value = [value]
    cleaned: list[str] = []
    for item in value or []:
        entity_id = _clean_entity(hass, item, domains)
        if entity_id and entity_id not in cleaned:
            cleaned.append(entity_id)
    return cleaned


def _rgb_hex(value: Any, fallback: list[int]) -> str:
    """Return a theme colour as #RRGGBB."""
    return theme.to_hex(value, fallback)


def _clean_rgb(value: Any, fallback: list[int]) -> list[int]:
    """Accept a panel hex color or an HA RGB selector value."""
    return theme.to_rgb(value, fallback)


def _public_options(options: dict[str, Any]) -> dict[str, Any]:
    """Return the options the panel is allowed to read and write."""
    return {
        CONF_DASHBOARD_TITLE: options.get(CONF_DASHBOARD_TITLE, "Family Dashboard"),
        CONF_BACKGROUND: options.get(CONF_BACKGROUND, "fall"),
        CONF_BACKGROUND_URL: options.get(CONF_BACKGROUND_URL, ""),
        "has_uploaded_background": bool(options.get(CONF_BACKGROUND_VERSION)),
        CONF_LAYOUT: options.get(CONF_LAYOUT, "home"),
        CONF_WEATHER_TAB_ENABLED: options.get(CONF_WEATHER_TAB_ENABLED, True),
        CONF_CALENDAR_TAB_ENABLED: options.get(CONF_CALENDAR_TAB_ENABLED, True),
        CONF_LIGHTS_TAB_ENABLED: options.get(CONF_LIGHTS_TAB_ENABLED, True),
        CONF_SCENES_TAB_ENABLED: options.get(CONF_SCENES_TAB_ENABLED, True),
        CONF_CLIMATE_TAB_ENABLED: options.get(CONF_CLIMATE_TAB_ENABLED, True),
        CONF_INDOOR_ENTITY: options.get(CONF_INDOOR_ENTITY, ""),
        CONF_INDOOR_HUMIDITY_ENTITY: options.get(CONF_INDOOR_HUMIDITY_ENTITY, ""),
        CONF_OUTDOOR_ENTITY: options.get(CONF_OUTDOOR_ENTITY, ""),
        CONF_MEAL_ENTITY: options.get(CONF_MEAL_ENTITY, ""),
        CONF_CALENDAR_ENTITIES: options.get(CONF_CALENDAR_ENTITIES, []),
        CONF_LIGHT_ENTITIES: options.get(CONF_LIGHT_ENTITIES, []),
        CONF_SCENE_ENTITIES: options.get(CONF_SCENE_ENTITIES, []),
        CONF_CLIMATE_ENTITIES: options.get(CONF_CLIMATE_ENTITIES, []),
        **{
            key: _rgb_hex(options.get(key), default)
            for key, default in THEME_DEFAULTS.items()
            if isinstance(default, list)
        },
        CONF_THEME_ITEM_OPACITY: options.get(
            CONF_THEME_ITEM_OPACITY, THEME_DEFAULTS[CONF_THEME_ITEM_OPACITY]
        ),
        CONF_THEME_BACKGROUND_OVERLAY: options.get(
            CONF_THEME_BACKGROUND_OVERLAY,
            THEME_DEFAULTS[CONF_THEME_BACKGROUND_OVERLAY],
        ),
        **{key: options.get(key, "") for key in MEAL_DAY_KEYS},
    }


def _merge_options(
    hass: HomeAssistant, current: dict[str, Any], incoming: dict[str, Any]
) -> dict[str, Any]:
    """Validate the panel settings and merge them into the current options."""
    options = dict(current)

    title = str(
        incoming.get(CONF_DASHBOARD_TITLE, options.get(CONF_DASHBOARD_TITLE, ""))
    ).strip()
    if not 1 <= len(title) <= 60:
        raise ValueError("invalid_title")
    options[CONF_DASHBOARD_TITLE] = title

    background = str(incoming.get(CONF_BACKGROUND, options.get(CONF_BACKGROUND, "fall")))
    if background not in BACKGROUNDS:
        raise ValueError("invalid_background")
    options[CONF_BACKGROUND] = background

    background_url = str(
        incoming.get(CONF_BACKGROUND_URL, options.get(CONF_BACKGROUND_URL, "")) or ""
    ).strip()
    options[CONF_BACKGROUND_URL] = background_url if background == "custom_url" else ""

    layout = str(incoming.get(CONF_LAYOUT, options.get(CONF_LAYOUT, "home")))
    if layout not in LAYOUTS:
        raise ValueError("invalid_layout")
    options[CONF_LAYOUT] = layout

    for key, default in THEME_DEFAULTS.items():
        if isinstance(default, list):
            options[key] = _clean_rgb(incoming.get(key, options.get(key)), default)
    for key in (CONF_THEME_ITEM_OPACITY, CONF_THEME_BACKGROUND_OVERLAY):
        try:
            number = int(incoming.get(key, options.get(key, THEME_DEFAULTS[key])))
        except (TypeError, ValueError):
            number = THEME_DEFAULTS[key]
        options[key] = max(0, min(100, number))

    for key in _TOGGLE_OPTIONS:
        options[key] = bool(incoming.get(key, options.get(key, True)))

    options[CONF_INDOOR_ENTITY] = _clean_entity(
        hass, incoming.get(CONF_INDOOR_ENTITY, options.get(CONF_INDOOR_ENTITY)),
        ("sensor", "climate"),
    )
    options[CONF_INDOOR_HUMIDITY_ENTITY] = _clean_entity(
        hass,
        incoming.get(
            CONF_INDOOR_HUMIDITY_ENTITY, options.get(CONF_INDOOR_HUMIDITY_ENTITY)
        ),
        ("sensor",),
    )
    options[CONF_OUTDOOR_ENTITY] = _clean_entity(
        hass, incoming.get(CONF_OUTDOOR_ENTITY, options.get(CONF_OUTDOOR_ENTITY)),
        ("weather",),
    )
    options[CONF_MEAL_ENTITY] = _clean_entity(
        hass, incoming.get(CONF_MEAL_ENTITY, options.get(CONF_MEAL_ENTITY)),
        ("input_text", "text"),
    )
    options[CONF_CALENDAR_ENTITIES] = _clean_entities(
        hass,
        incoming.get(CONF_CALENDAR_ENTITIES, options.get(CONF_CALENDAR_ENTITIES)),
        ("calendar",),
    )
    options[CONF_LIGHT_ENTITIES] = _clean_entities(
        hass,
        incoming.get(CONF_LIGHT_ENTITIES, options.get(CONF_LIGHT_ENTITIES)),
        ("light",),
    )
    options[CONF_SCENE_ENTITIES] = _clean_entities(
        hass,
        incoming.get(CONF_SCENE_ENTITIES, options.get(CONF_SCENE_ENTITIES)),
        ("scene", "script"),
    )
    options[CONF_CLIMATE_ENTITIES] = _clean_entities(
        hass,
        incoming.get(CONF_CLIMATE_ENTITIES, options.get(CONF_CLIMATE_ENTITIES)),
        ("climate",),
    )

    for key in MEAL_DAY_KEYS:
        value = str(incoming.get(key, options.get(key, "")) or "").strip()
        options[key] = value[:120]

    return options


class FamilyDashboardPanelView(HomeAssistantView):
    """Serve the dashboard payload to a signed-in Home Assistant user."""

    url = "/api/family_dashboard/panel"
    name = "api:roku_dashboard_panel"
    requires_auth = True

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the dashboard data."""
        entry = _config_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        payload = await async_dashboard_payload(self.hass, entry)
        return self.json(payload)


class FamilyDashboardPanelActionView(HomeAssistantView):
    """Run dashboard control commands from the Home Assistant panel."""

    url = "/api/family_dashboard/panel/action"
    name = "api:roku_dashboard_panel_action"
    requires_auth = True

    def __init__(self, hass) -> None:
        self.hass = hass

    async def post(self, request):
        """Execute an allowlisted dashboard command."""
        entry = _config_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "invalid_json"}, status_code=400)
        result, status = await async_execute_action(self.hass, entry, body)
        return self.json(result, status_code=status)


class FamilyDashboardPanelSettingsView(HomeAssistantView):
    """Read and write the dashboard options from the Home Assistant panel."""

    url = "/api/family_dashboard/panel/settings"
    name = "api:roku_dashboard_panel_settings"
    requires_auth = True

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the current dashboard options."""
        if not _is_admin(request):
            return self.json({"error": "not_allowed"}, status_code=403)
        entry = _config_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        return self.json({"options": _public_options(entry.options)})

    async def post(self, request):
        """Save the dashboard options."""
        if not _is_admin(request):
            return self.json({"error": "not_allowed"}, status_code=403)
        entry = _config_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "invalid_json"}, status_code=400)
        incoming = body.get("options")
        if not isinstance(incoming, dict):
            return self.json({"error": "invalid_options"}, status_code=400)
        try:
            options = _merge_options(self.hass, entry.options, incoming)
        except ValueError as err:
            return self.json({"error": str(err)}, status_code=400)
        self.hass.config_entries.async_update_entry(entry, options=options)
        return self.json({"options": _public_options(options)})


class FamilyDashboardPanelBackgroundView(HomeAssistantView):
    """Serve the uploaded background to the Home Assistant panel."""

    url = "/api/family_dashboard/panel/background"
    name = "api:roku_dashboard_panel_background"
    requires_auth = True

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the uploaded background image."""
        entry = _config_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        path = Path(self.hass.config.path("roku_dashboard", "background"))
        if not path.is_file():
            return self.json({"error": "no_background"}, status_code=404)
        content_type = (
            entry.options.get("background_type")
            or mimetypes.guess_type(entry.options.get("background_name", path.name))[0]
            or "image/jpeg"
        )
        return web.FileResponse(
            path,
            headers={"Content-Type": content_type, "Cache-Control": "no-store"},
        )


class FamilyDashboardPanelPairingView(HomeAssistantView):
    """Review pairing requests and manage the paired devices.

    Devices without a keyboard, such as Apple TV, ask to pair and wait for an
    administrator to approve them here. Approval never happens in a client
    app, so a paired device holds no administrative access.
    """

    url = "/api/family_dashboard/panel/pairing"
    name = "api:roku_dashboard_panel_pairing"
    requires_auth = True

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request):
        """Return the pending requests and the paired devices."""
        if not _is_admin(request):
            return self.json({"error": "not_allowed"}, status_code=403)
        return self.json(
            {
                "pending": [
                    pairing.public_request(record)
                    for record in pairing.list_requests(self.hass)
                ],
                "devices": [
                    pairing.public_record(record)
                    for record in pairing.list_devices(self.hass)
                ],
                "legacy_token": self._legacy_device(),
            }
        )

    async def post(self, request):
        """Approve, deny or revoke a device."""
        if not _is_admin(request):
            return self.json({"error": "not_allowed"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "invalid_json"}, status_code=400)
        action = str(body.get("action", ""))
        if action in ("approve", "deny"):
            code = str(body.get("device_code", "")).strip().upper()
            if action == "approve":
                record = await pairing.async_approve(self.hass, code)
                if record is None:
                    return self.json({"error": "unknown_request"}, status_code=404)
                return self.json({"ok": True, "device_id": record["device_id"]})
            if not await pairing.async_deny(self.hass, code):
                return self.json({"error": "unknown_request"}, status_code=404)
            return self.json({"ok": True})
        if action == "revoke":
            device_id = str(body.get("device_id", ""))
            if not await pairing.async_revoke(self.hass, device_id):
                return self.json({"error": "unknown_device"}, status_code=404)
            return self.json({"ok": True})
        if action == "revoke_legacy":
            return await self._revoke_legacy()
        return self.json({"error": "invalid_action"}, status_code=400)

    def _legacy_device(self) -> dict[str, Any] | None:
        """Return the shared credential used before per-device tokens."""
        entry = _config_entry(self.hass)
        if entry is None or not entry.data.get(CONF_DEVICE_TOKEN):
            return None
        return {
            "device_id": "legacy",
            "name": "Legacy shared token",
            "platform": "legacy",
            "created": "",
            "last_seen": "",
            "legacy": True,
        }

    async def _revoke_legacy(self):
        """Clear the shared credential used before per-device tokens."""
        entry = _config_entry(self.hass)
        if entry is None:
            return self.json({"error": "not_configured"}, status_code=404)
        data = dict(entry.data)
        data[CONF_DEVICE_TOKEN] = ""
        # Remember the revocation, otherwise the next reload would hand out a
        # fresh shared token and the revoke would look like it did nothing.
        data[CONF_LEGACY_TOKEN_REVOKED] = True
        self.hass.config_entries.async_update_entry(entry, data=data)
        return self.json({"ok": True})


async def async_setup_panel(hass: HomeAssistant) -> None:
    """Register the Family Dashboard panel in the Home Assistant menu."""
    from homeassistant.components.frontend import async_remove_panel
    from homeassistant.components.panel_custom import async_register_panel

    entry = _config_entry(hass)
    title = "Family Dashboard"
    if entry is not None:
        title = entry.options.get(CONF_DASHBOARD_TITLE) or title

    # Re-registering an existing panel is not allowed, so drop the old one.
    async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)

    result = async_register_panel(
        hass,
        frontend_url_path=PANEL_URL_PATH,
        webcomponent_name=PANEL_ELEMENT_NAME,
        sidebar_title=title,
        sidebar_icon=PANEL_ICON,
        js_url=PANEL_JS_URL,
        embed_iframe=False,
        require_admin=False,
    )
    if inspect.isawaitable(result):
        await result


def async_unsetup_panel(hass: HomeAssistant) -> None:
    """Remove the Family Dashboard panel from the Home Assistant menu."""
    try:
        from homeassistant.components.frontend import async_remove_panel
    except ImportError:
        return
    async_remove_panel(hass, PANEL_URL_PATH, warn_if_unknown=False)
