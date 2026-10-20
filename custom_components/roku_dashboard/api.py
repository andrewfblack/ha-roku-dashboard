"""Local pairing API consumed by the Roku channel."""

from __future__ import annotations

from datetime import timedelta
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

        events = await self._calendar_events(calendars)
        return self.json(
            {
                "ok": True,
                "states": states,
                "resolved_entities": {"inside": indoor, "outside": outdoor},
                "meal_plan": meal_plan,
                "calendar_events": events,
                "background": options.get(CONF_BACKGROUND, "fall"),
                "background_url": options.get(CONF_BACKGROUND_URL, ""),
                "layout": options.get(CONF_LAYOUT, "home"),
            }
        )

    async def _calendar_events(self, calendars: list[str]) -> list[dict[str, Any]]:
        if not calendars:
            calendars = [
                state.entity_id
                for state in self.hass.states.async_all(["calendar"])
            ]
        if not calendars:
            return []

        now = dt_util.now()
        end = now + timedelta(days=1)
        try:
            response = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": calendars,
                    "start_date_time": now.isoformat(),
                    "end_date_time": end.isoformat(),
                },
                blocking=True,
                return_response=True,
            )
        except Exception:  # Calendar providers vary; don't break all dashboard data.
            _LOGGER.exception("Unable to fetch Roku dashboard calendar events")
            return []

        output: list[dict[str, Any]] = []
        for calendar_data in (response or {}).values():
            for event in calendar_data.get("events", []):
                start = event.get("start", "")
                output.append(
                    {
                        "title": event.get("summary", "Untitled"),
                        "start": start,
                        "all_day": "T" not in start,
                    }
                )
        output.sort(key=lambda item: item["start"])
        return output[:5]
