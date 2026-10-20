"""Local pairing API consumed by the Roku channel."""

from __future__ import annotations

from calendar import monthrange
import logging
import secrets
from typing import Any

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from .const import (
    CONF_BACKGROUND,
    CONF_BACKGROUND_URL,
    CONF_CALENDAR_ENTITIES,
    CONF_INDOOR_ENTITY,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    CONF_OUTDOOR_ENTITY,
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
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class RokuDashboardView(HomeAssistantView):
    """Serve only dashboard-selected data to a paired Roku on the LAN."""

    url = "/api/roku_dashboard/{code}"
    name = "api:roku_dashboard"
    requires_auth = False

    def __init__(self, hass) -> None:
        self.hass = hass

    async def get(self, request, code: str):
        entry = self._entry_for_code(code)
        if entry is None:
            return self.json({"error": "invalid_pairing_code"}, status_code=401)

        options = entry.options
        indoor = options.get(CONF_INDOOR_ENTITY, "")
        outdoor = options.get(CONF_OUTDOOR_ENTITY, "")
        meal = options.get(CONF_MEAL_ENTITY, "")
        calendars = options.get(CONF_CALENDAR_ENTITIES, [])
        if isinstance(calendars, str):
            calendars = [calendars]

        states: dict[str, Any] = {}
        for entity_id in (indoor, outdoor, meal):
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is not None:
                states[entity_id] = {
                    "state": state.state,
                    "attributes": dict(state.attributes),
                }

        meal_state = self.hass.states.get(meal) if meal else None
        meal_plan = ""
        if meal_state and meal_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            meal_plan = meal_state.state

        events, month = await self._calendar_data(calendars)
        weather = await self._weather_data(outdoor, options)
        lights = self._entity_cards(options.get(CONF_LIGHT_ENTITIES, []))
        scenes = self._entity_cards(options.get(CONF_SCENE_ENTITIES, []))
        climates = self._climate_cards(options.get(CONF_CLIMATE_ENTITIES, []))
        payload = {
                "ok": True,
                "states": states,
                "resolved_entities": {"inside": indoor, "outside": outdoor},
                "meal_plan": meal_plan,
                "calendar_events": events,
                "month_calendar": month,
                "background": options.get(CONF_BACKGROUND, "fall"),
                "background_url": options.get(CONF_BACKGROUND_URL, ""),
                "layout": options.get(CONF_LAYOUT, "home"),
                "weather": weather,
                "tabs": {
                    "weather": options.get(CONF_WEATHER_TAB_ENABLED, True),
                    "lights": options.get(CONF_LIGHTS_TAB_ENABLED, True),
                    "scenes": options.get(CONF_SCENES_TAB_ENABLED, True),
                    "climate": options.get(CONF_CLIMATE_TAB_ENABLED, True),
                },
                "lights": lights,
                "scenes": scenes,
                "climates": climates,
            }
        # Exchange the human-friendly code once for a strong device token,
        # then rotate the short code. Control POSTs never accept short codes.
        if secrets.compare_digest(
            str(entry.data.get(CONF_PAIRING_CODE, "")), code.upper()
        ):
            payload["device_token"] = entry.data[CONF_DEVICE_TOKEN]
            data = dict(entry.data)
            data[CONF_PAIRING_CODE] = secrets.token_hex(4).upper()
            self.hass.config_entries.async_update_entry(entry, data=data)
        return self.json(payload)

    def _entry_for_code(self, code: str):
        return next(
            (
                item
                for item in self.hass.config_entries.async_entries(DOMAIN)
                if secrets.compare_digest(
                    str(item.data.get(CONF_PAIRING_CODE, "")), code.upper()
                )
                or secrets.compare_digest(
                    str(item.data.get(CONF_DEVICE_TOKEN, "")), code.upper()
                )
            ),
            None,
        )

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        return list(value or [])

    def _entity_cards(self, configured: Any) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for entity_id in self._as_list(configured):
            state = self.hass.states.get(entity_id)
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

    def _climate_cards(self, configured: Any) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for entity_id in self._as_list(configured):
            state = self.hass.states.get(entity_id)
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

    async def post(self, request, code: str):
        """Execute an allowlisted dashboard command."""
        entry = self._entry_for_code(code)
        if entry is None:
            return self.json({"error": "invalid_pairing_code"}, status_code=401)
        if not secrets.compare_digest(
            str(entry.data.get(CONF_DEVICE_TOKEN, "")), code.upper()
        ):
            return self.json({"error": "pairing_required"}, status_code=403)
        try:
            body = await request.json()
        except Exception:
            return self.json({"error": "invalid_json"}, status_code=400)

        action = str(body.get("action", ""))
        entity_id = str(body.get("entity_id", ""))
        options = entry.options
        lights = self._as_list(options.get(CONF_LIGHT_ENTITIES, []))
        scenes = self._as_list(options.get(CONF_SCENE_ENTITIES, []))
        climates = self._as_list(options.get(CONF_CLIMATE_ENTITIES, []))

        domain = ""
        service = ""
        data: dict[str, Any] = {"entity_id": entity_id}
        if action == "light_toggle" and entity_id in lights:
            domain, service = "light", "toggle"
        elif action == "light_brightness" and entity_id in lights:
            domain, service = "light", "turn_on"
            data["brightness_pct"] = max(1, min(100, int(body.get("value", 100))))
        elif action == "scene_activate" and entity_id in scenes:
            domain = entity_id.split(".", 1)[0]
            if domain not in ("scene", "script"):
                return self.json({"error": "not_allowed"}, status_code=403)
            service = "turn_on"
        elif action == "climate_temperature" and entity_id in climates:
            domain, service = "climate", "set_temperature"
            data["temperature"] = float(body.get("value"))
        elif action == "climate_mode" and entity_id in climates:
            state = self.hass.states.get(entity_id)
            mode = str(body.get("value", ""))
            if state is None or mode not in state.attributes.get("hvac_modes", []):
                return self.json({"error": "invalid_mode"}, status_code=400)
            domain, service = "climate", "set_hvac_mode"
            data["hvac_mode"] = mode
        else:
            return self.json({"error": "not_allowed"}, status_code=403)

        try:
            await self.hass.services.async_call(
                domain, service, data, blocking=True
            )
        except Exception:
            _LOGGER.exception("Roku dashboard command failed")
            return self.json({"error": "service_failed"}, status_code=500)
        return self.json({"ok": True})

    async def _weather_data(
        self, entity_id: str, options: dict[str, Any]
    ) -> dict[str, Any]:
        """Return current conditions and a normalized HA forecast."""
        if not options.get(CONF_WEATHER_TAB_ENABLED, True):
            return {"enabled": False}
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None:
            return {"enabled": True, "available": False, "forecast": []}

        forecast_type = options.get(CONF_FORECAST_TYPE, "daily")
        count = options.get(CONF_FORECAST_COUNT, 5)
        forecasts: list[dict[str, Any]] = []
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": entity_id, "type": forecast_type},
                blocking=True,
                return_response=True,
            )
            raw_items = (response or {}).get(entity_id, {}).get("forecast", [])
            for item in raw_items[:count]:
                forecasts.append(
                    {
                        "datetime": item.get("datetime", ""),
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
        self, calendars: list[str]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if not calendars:
            calendars = [
                state.entity_id
                for state in self.hass.states.async_all(["calendar"])
            ]
        if not calendars:
            return [], {}

        now = dt_util.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            month_end = month_start.replace(year=now.year + 1, month=1)
        else:
            month_end = month_start.replace(month=now.month + 1)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendars,
                    "start_date_time": month_start.isoformat(),
                    "end_date_time": month_end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except Exception:  # Calendar providers vary; don't break all dashboard data.
            _LOGGER.exception("Unable to fetch Roku dashboard calendar events")
            return [], {}

        output: list[dict[str, Any]] = []
        event_days: set[int] = set()
        for calendar_data in (response or {}).values():
            for event in calendar_data.get("events", []):
                start = event.get("start", "")
                start_date = start[:10]
                if start_date.startswith(f"{now.year:04d}-{now.month:02d}-"):
                    try:
                        event_days.add(int(start_date[-2:]))
                    except ValueError:
                        pass
                output.append(
                    {
                        "title": event.get("summary", "Untitled"),
                        "start": start,
                        "all_day": "T" not in start,
                    }
                )
        output.sort(key=lambda item: item["start"])
        today = now.date().isoformat()
        todays_events = [item for item in output if item["start"][:10] == today][:3]
        days_in_month = monthrange(now.year, now.month)[1]
        # Python Monday=0; Roku grid uses Sunday=0.
        first_weekday = (month_start.weekday() + 1) % 7
        return todays_events, {
            "title": now.strftime("%B %Y"),
            "year": now.year,
            "month": now.month,
            "today": now.day,
            "days_in_month": days_in_month,
            "first_weekday": first_weekday,
            "event_days": sorted(event_days),
            "events": output,
        }
