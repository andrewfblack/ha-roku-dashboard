"""Sensor platform for Family Dashboard.

Publishes sensor.roku_dashboard_config: a JSON blob the Roku channel reads
(via /api/states) to learn which entities, calendars, background and layout
to display.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import Entity

from .const import (
    CONF_ACCESS_MODE,
    CONF_DASHBOARD_TITLE,
    CONF_INDOOR_HUMIDITY_ENTITY,
    CONF_MEAL_MONDAY,
    CONF_MEAL_TUESDAY,
    CONF_MEAL_WEDNESDAY,
    CONF_MEAL_THURSDAY,
    CONF_MEAL_FRIDAY,
    CONF_MEAL_SATURDAY,
    CONF_MEAL_SUNDAY,
    CONF_BACKGROUND,
    CONF_BACKGROUND_URL,
    CONF_CALENDAR_ENTITIES,
    CONF_CALENDAR_TAB_ENABLED,
    CONF_CALENDAR_SCHEDULE_DAYS,
    CONF_CALENDAR_EVENTS_PER_DAY,
    CONF_INDOOR_ENTITY,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_PAIRING_CODE,
    CONF_WEATHER_TAB_ENABLED,
    CONF_FORECAST_TYPE,
    CONF_FORECAST_COUNT,
    CONF_LIGHTS_TAB_ENABLED,
    CONF_LIGHT_ENTITIES,
    CONF_SCENES_TAB_ENABLED,
    CONF_SCENE_ENTITIES,
    CONF_CLIMATE_TAB_ENABLED,
    CONF_CLIMATE_ENTITIES,
    CONF_US_HOLIDAYS_ENABLED,
    CONF_US_OBSERVANCES_ENABLED,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA_VERSION = 1


async def async_setup_entry(
    hass, entry: ConfigEntry, async_add_entities
) -> None:
    """Set up the config sensor from a config entry."""
    async_add_entities([RokuDashboardConfigSensor(entry)])


class RokuDashboardConfigSensor(Entity):
    """JSON configuration sensor consumed by the Roku channel."""

    _attr_has_entity_name = True
    _attr_name = "Config"
    _attr_icon = "mdi:television-classic"
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_config"
        # Fixed entity id so the Roku app can look it up by name.
        self.entity_id = f"sensor.{DOMAIN}_config"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "name": "Family Dashboard",
            "manufacturer": "Family Dashboard",
            "model": "HACS custom integration",
        }

    @property
    def native_value(self) -> str:
        """Keep the state short; complete configuration lives in attributes."""
        return "ready"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Same data as attributes for easy use in automations/templates."""
        return self._config_payload()

    def _config_payload(self) -> dict[str, Any]:
        options = self._entry.options
        indoor = options.get(CONF_INDOOR_ENTITY, "")
        outdoor = options.get(CONF_OUTDOOR_ENTITY, "")
        meal = options.get(CONF_MEAL_ENTITY, "")
        calendars = options.get(CONF_CALENDAR_ENTITIES, [])
        if isinstance(calendars, str):
            calendars = [calendars]
        background = options.get(CONF_BACKGROUND, "fall")
        background_url = options.get(CONF_BACKGROUND_URL, "")
        layout = options.get(CONF_LAYOUT, "home")

        return {
            "schema": CONFIG_SCHEMA_VERSION,
            "pairing_code": self._entry.data.get(CONF_PAIRING_CODE, ""),
            "access_mode": options.get(CONF_ACCESS_MODE, "lan"),
            "dashboard_title": options.get(CONF_DASHBOARD_TITLE, "Family Dashboard"),
            "indoor_entity": indoor,
            "indoor_humidity_entity": options.get(CONF_INDOOR_HUMIDITY_ENTITY, ""),
            "outdoor_entity": outdoor,
            "weather_tab_enabled": options.get(CONF_WEATHER_TAB_ENABLED, True),
            "forecast_type": options.get(CONF_FORECAST_TYPE, "daily"),
            "forecast_count": options.get(CONF_FORECAST_COUNT, 5),
            "lights_tab_enabled": options.get(CONF_LIGHTS_TAB_ENABLED, True),
            "light_entities": options.get(CONF_LIGHT_ENTITIES, []),
            "scenes_tab_enabled": options.get(CONF_SCENES_TAB_ENABLED, True),
            "scene_entities": options.get(CONF_SCENE_ENTITIES, []),
            "climate_tab_enabled": options.get(CONF_CLIMATE_TAB_ENABLED, True),
            "climate_entities": options.get(CONF_CLIMATE_ENTITIES, []),
            "meal_entity": meal,
            "weekly_meals": [
                options.get(CONF_MEAL_MONDAY, ""),
                options.get(CONF_MEAL_TUESDAY, ""),
                options.get(CONF_MEAL_WEDNESDAY, ""),
                options.get(CONF_MEAL_THURSDAY, ""),
                options.get(CONF_MEAL_FRIDAY, ""),
                options.get(CONF_MEAL_SATURDAY, ""),
                options.get(CONF_MEAL_SUNDAY, ""),
            ],
            "calendar_entities": [c for c in calendars if c],
            "calendar_tab_enabled": options.get(CONF_CALENDAR_TAB_ENABLED, True),
            "calendar_schedule_days": options.get(CONF_CALENDAR_SCHEDULE_DAYS, 7),
            "calendar_events_per_day": options.get(CONF_CALENDAR_EVENTS_PER_DAY, 5),
            "us_holidays_enabled": options.get(CONF_US_HOLIDAYS_ENABLED, True),
            "us_observances_enabled": options.get(
                CONF_US_OBSERVANCES_ENABLED, True
            ),
            "background": background,
            "background_url": background_url if background == "custom_url" else "",
            "layout": layout,
        }
