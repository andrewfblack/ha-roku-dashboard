"""Services for the Family Dashboard integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.storage import Store

from .const import (
    BACKGROUNDS,
    CONF_BACKGROUND,
    CONF_BACKGROUND_URL,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    DOMAIN,
    LAYOUTS,
    MEAL_HELPER_ENTITY,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_MEAL_PLAN = "set_meal_plan"
SERVICE_SET_BACKGROUND = "set_background"
SERVICE_SET_LAYOUT = "set_layout"

ATTR_VALUE = "value"
ATTR_ENTITY_ID = "entity_id"


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the Family Dashboard services (idempotent, call from the loop)."""
    if hass.data.get(DOMAIN, {}).get("services_registered"):
        return
    hass.data.setdefault(DOMAIN, {})["services_registered"] = True

    async def set_meal_plan(call: ServiceCall) -> None:
        """Set the meal plan text (into the integration's helper by default)."""
        entity_id = call.data.get(ATTR_ENTITY_ID)
        if not entity_id:
            entity_id = _default_meal_entity(hass)
        value: str = call.data[ATTR_VALUE]

        if entity_id.startswith("input_text."):
            domain, service = "input_text", "set_value"
        elif entity_id.startswith("text."):
            domain, service = "text", "set_value"
        else:
            _LOGGER.warning("set_meal_plan: unsupported entity %s", entity_id)
            return
        await hass.services.async_call(
            domain, service, {"entity_id": entity_id, "value": value}, blocking=True
        )
        # Keep our restore-store in sync immediately, not only via the tracker.
        store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        await store.async_save(value)

    async def _set_option(call: ServiceCall, key: str, valid: dict[str, str]) -> None:
        """Update an option on the config entry and reload it."""
        value: str = call.data[ATTR_VALUE]
        if value not in valid:
            _LOGGER.warning(
                "Invalid value '%s' for %s; expected one of %s",
                value,
                key,
                ", ".join(valid),
            )
            return
        entries = hass.config_entries.async_entries(DOMAIN)
        if not entries:
            _LOGGER.warning("No %s config entry to update", DOMAIN)
            return
        entry = entries[0]
        options = dict(entry.options)
        options[key] = value
        if key == CONF_BACKGROUND and value == "custom_url":
            options[CONF_BACKGROUND_URL] = call.data.get(CONF_BACKGROUND_URL, "")
        hass.config_entries.async_update_entry(entry, options=options)
        # Entry update listener reloads it, which refreshes the config sensor.

    async def set_background(call: ServiceCall) -> None:
        """Change the Roku channel background."""
        await _set_option(call, CONF_BACKGROUND, BACKGROUNDS)

    async def set_layout(call: ServiceCall) -> None:
        """Change the Roku channel layout preset."""
        await _set_option(call, CONF_LAYOUT, LAYOUTS)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MEAL_PLAN,
        set_meal_plan,
        schema=vol.Schema(
            {
                vol.Required(ATTR_VALUE): cv.string,
                vol.Optional(ATTR_ENTITY_ID): cv.entity_id,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BACKGROUND,
        set_background,
        schema=vol.Schema(
            {
                vol.Required(ATTR_VALUE): vol.In(BACKGROUNDS),
                vol.Optional(CONF_BACKGROUND_URL): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LAYOUT,
        set_layout,
        schema=vol.Schema({vol.Required(ATTR_VALUE): vol.In(LAYOUTS)}),
    )


def _default_meal_entity(hass: HomeAssistant) -> str:
    """Resolve the meal entity from the config entry (fall back to our helper)."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if entries:
        entity = entries[0].options.get(CONF_MEAL_ENTITY)
        if entity:
            return entity
    return MEAL_HELPER_ENTITY


def option_entities(hass: HomeAssistant) -> dict[str, Any]:
    """Helper used by the config flow: current options (or defaults)."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return {}
    return dict(entries[0].options)
