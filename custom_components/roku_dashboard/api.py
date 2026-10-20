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
    CONF_WEATHER_TAB_ENABLED,
    CONF_FORECAST_TYPE,
    CONF_FORECAST_COUNT,
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
        entry = next(
            (
                item
                for item in self.hass.config_entries.async_entries(DOMAIN)
                if secrets.compare_digest(
                    str(item.data.get(CONF_PAIRING_CODE, "")), code.upper()
                )
            ),
            None,
        )
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
        return self.json(
            {
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
            }
        )

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
        }
