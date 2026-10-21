"""Roku Dashboard integration.

Bridges your Roku HA Dashboard channel to Home Assistant:
- creates (and owns) a meal-planner text helper,
- tracks the indoor sensor / outdoor weather entity you pick,
- publishes everything (plus layout/background choices) on
  sensor.roku_dashboard_config for the Roku app to consume.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store

from .const import (
    CONF_MEAL_ENTITY,
    CONF_PAIRING_CODE,
    CONF_DEVICE_TOKEN,
    DOMAIN,
    MEAL_HELPER_ENTITY,
    MEAL_HELPER_KEY,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .services import async_setup_services
from .api import (
    RokuDashboardActionView,
    RokuDashboardBackgroundView,
    RokuDashboardView,
)
from .web import FamilyDashboardAssetView, FamilyDashboardWebView

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Roku Dashboard component (services are registered here)."""
    hass.data.setdefault(DOMAIN, {})
    async_setup_services(hass)
    hass.http.register_view(RokuDashboardView(hass))
    hass.http.register_view(RokuDashboardActionView(hass))
    hass.http.register_view(RokuDashboardBackgroundView(hass))
    hass.http.register_view(FamilyDashboardWebView)
    hass.http.register_view(FamilyDashboardAssetView)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a Roku Dashboard config entry."""
    hass.data.setdefault(DOMAIN, {})

    if not entry.data.get(CONF_PAIRING_CODE):
        data = dict(entry.data)
        data[CONF_PAIRING_CODE] = secrets.token_hex(4).upper()
        hass.config_entries.async_update_entry(entry, data=data)
    if not entry.data.get(CONF_DEVICE_TOKEN):
        data = dict(entry.data)
        data[CONF_DEVICE_TOKEN] = secrets.token_hex(32).upper()
        hass.config_entries.async_update_entry(entry, data=data)

    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_value: str = (await store.async_load()) or ""

    meal_entity = entry.options.get(CONF_MEAL_ENTITY) or MEAL_HELPER_ENTITY

    # Create our own helper when the user wants us to manage it.
    if meal_entity == MEAL_HELPER_ENTITY and hass.states.get(meal_entity) is None:
        if er.async_get(hass).async_get(meal_entity) is None:
            _create_meal_helper(hass, stored_value)

    # Mirror the helper's value into our store so it survives restarts
    # (helpers we create are not written to input_text's own storage).
    # The tracker matches by entity_id, so it also works if the helper's
    # first state only appears a moment after we create it.
    entry.async_on_unload(
        async_track_state_change_event(
            hass, [meal_entity], _meal_state_changed(hass, store)
        )
    )

    # Restore a previously saved value into an empty helper (covers the
    # case where input_text.async_create was unavailable and the user
    # created the helper manually without an initial value).
    current = hass.states.get(meal_entity)
    if (
        current is not None
        and stored_value
        and current.state in ("", "unknown", "unavailable")
    ):
        await _set_meal_value(hass, meal_entity, stored_value)

    if not _meal_entity_available(hass, meal_entity):
        _LOGGER.warning(
            "Meal plan entity %s not found; the meal panel will be empty. "
            "Create a text helper or fix the entity in the integration options.",
            meal_entity,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _meal_entity_available(hass: HomeAssistant, entity_id: str) -> bool:
    return (
        er.async_get(hass).async_get(entity_id) is not None
        or hass.states.get(entity_id) is not None
    )


def _create_meal_helper(hass: HomeAssistant, initial: str) -> None:
    """Create the input_text meal-plan helper (idempotent by entity id)."""
    from homeassistant.components import input_text

    config: dict[str, Any] = {
        "name": "Roku Meal Plan",
        "max": 255,
        "mode": "text",
        "icon": "mdi:food-serve",
    }
    if initial:
        config["initial"] = initial

    creator = getattr(input_text, "async_create", None)
    if creator is None:
        _LOGGER.error(
            "input_text.async_create is unavailable in this Home Assistant "
            "version. Create a text helper and select it under this "
            "integration's options (meal plan entity: %s).",
            MEAL_HELPER_ENTITY,
        )
        return
    creator(hass, MEAL_HELPER_KEY, config)
    _LOGGER.info("Created meal plan helper %s", MEAL_HELPER_ENTITY)


def _meal_state_changed(hass: HomeAssistant, store: Store):
    """Build a state-change listener that mirrors the helper into storage."""

    @callback
    def _handler(event) -> None:
        new_state = event.data.get("new_state")
        if new_state is not None and new_state.state not in ("unknown", "unavailable"):
            hass.async_create_task(store.async_save(new_state.state))

    return _handler


async def _set_meal_value(hass: HomeAssistant, entity_id: str, value: str) -> None:
    """Write a value into a text-style helper entity."""
    if entity_id.startswith("input_text."):
        domain, service = "input_text", "set_value"
    elif entity_id.startswith("text."):
        domain, service = "text", "set_value"
    else:
        _LOGGER.warning("Unsupported meal entity type: %s", entity_id)
        return
    await hass.services.async_call(
        domain, service, {"entity_id": entity_id, "value": value}, blocking=True
    )
