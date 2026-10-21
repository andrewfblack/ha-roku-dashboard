"""Local pairing API consumed by the Roku channel."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import logging
import mimetypes
import ipaddress
from pathlib import Path
import secrets
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

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
    CONF_DASHBOARD_TITLE,
    CONF_INDOOR_ENTITY,
    CONF_INDOOR_HUMIDITY_ENTITY,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    MEAL_DAY_KEYS,
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
    CONF_US_HOLIDAYS_ENABLED,
    CONF_US_OBSERVANCES_ENABLED,
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
        is_pairing = secrets.compare_digest(
            str(entry.data.get(CONF_PAIRING_CODE, "")), code.upper()
        )
        if not request_allowed(request, entry, pairing=is_pairing):
            return self.json({"error": "network_access_denied"}, status_code=403)

        options = entry.options
        indoor = options.get(CONF_INDOOR_ENTITY, "")
        indoor_humidity = options.get(CONF_INDOOR_HUMIDITY_ENTITY, "")
        outdoor = options.get(CONF_OUTDOOR_ENTITY, "")
        meal = options.get(CONF_MEAL_ENTITY, "")
        calendars = options.get(CONF_CALENDAR_ENTITIES, [])
        if isinstance(calendars, str):
            calendars = [calendars]

        states: dict[str, Any] = {}
        for entity_id in (indoor, indoor_humidity, outdoor, meal):
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is not None:
                states[entity_id] = {
                    "state": state.state,
                    "attributes": dict(state.attributes),
                }

        meal_plan, weekly_meals = self._meal_data(options, meal)

        events, month, schedule = await self._calendar_data(
            calendars,
            options.get(CONF_US_HOLIDAYS_ENABLED, True),
            options.get(CONF_US_OBSERVANCES_ENABLED, True),
            options.get(CONF_CALENDAR_SCHEDULE_DAYS, 7),
            options.get(CONF_CALENDAR_EVENTS_PER_DAY, 5),
        )
        weather = await self._weather_data(outdoor, options)
        lights = self._entity_cards(options.get(CONF_LIGHT_ENTITIES, []))
        scenes = self._entity_cards(options.get(CONF_SCENE_ENTITIES, []))
        climates = self._climate_cards(options.get(CONF_CLIMATE_ENTITIES, []))
        payload = {
                "ok": True,
                "access_mode": options.get(CONF_ACCESS_MODE, "lan"),
                "title": options.get(CONF_DASHBOARD_TITLE, "Family Dashboard"),
                "states": states,
                "resolved_entities": {
                    "inside": indoor,
                    "inside_humidity": indoor_humidity,
                    "outside": outdoor,
                },
                "meal_plan": meal_plan,
                "weekly_meal_plan": weekly_meals,
                "calendar_events": events,
                "month_calendar": month,
                "calendar_schedule": schedule,
                "background": options.get(CONF_BACKGROUND, "fall"),
                "background_url": options.get(CONF_BACKGROUND_URL, ""),
                "background_version": options.get(CONF_BACKGROUND_VERSION, ""),
                "has_uploaded_background": bool(
                    options.get(CONF_BACKGROUND_VERSION)
                ),
                "layout": options.get(CONF_LAYOUT, "home"),
                "weather": weather,
                "tabs": {
                    "calendar": options.get(CONF_CALENDAR_TAB_ENABLED, True),
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
        return entry_for_code(self.hass, code)

    @staticmethod
    def _as_list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        return list(value or [])

    def _meal_data(
        self, options: dict[str, Any], fallback_entity: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """Build today's meal and a Monday-Sunday plan with helper fallback."""
        day_names = [
            "Monday", "Tuesday", "Wednesday", "Thursday",
            "Friday", "Saturday", "Sunday",
        ]
        meals = [str(options.get(key, "") or "").strip() for key in MEAL_DAY_KEYS]
        fallback = ""
        state = self.hass.states.get(fallback_entity) if fallback_entity else None
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
        if not request_allowed(request, entry, pairing=False):
            return self.json({"error": "network_access_denied"}, status_code=403)
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
        if action == "meal_week":
            values = body.get("value")
            if not isinstance(values, list) or len(values) != 7:
                return self.json({"error": "invalid_meal_plan"}, status_code=400)
            updated = dict(options)
            for index, key in enumerate(MEAL_DAY_KEYS):
                updated[key] = str(values[index] or "").strip()[:120]
            self.hass.config_entries.async_update_entry(entry, options=updated)
            return self.json({"ok": True})
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
        self,
        calendars: list[str],
        include_us_holidays: bool,
        include_us_observances: bool,
        schedule_days: int,
        events_per_day: int,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        if not calendars:
            calendars = [
                state.entity_id
                for state in self.hass.states.async_all(["calendar"])
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
                response = await self.hass.services.async_call(
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
            state = self.hass.states.get(calendar_id)
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

        generated: list[tuple[date, str]] = []
        years = {month_start.year, fetch_end.year}
        if include_us_holidays:
            for year in years:
                generated.extend(self._us_federal_holidays(year))
        if include_us_observances:
            for year in years:
                generated.extend(self._us_observances(year))
        for event_date, title in generated:
            if month_start.date() <= event_date < fetch_end.date():
                output.append(
                    {
                        "title": title,
                        "start": event_date.isoformat(),
                        "all_day": True,
                        "calendar_id": "calendar.us_holidays",
                        "calendar_name": "US Holidays",
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
        todays_events = [item for item in output if item["start"][:10] == today][:3]

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
        }
        schedule = {
            "title": f"{today_date.strftime('%B')} {today_date.day}",
            "days": schedule_columns,
            "day_count": schedule_days,
            "events_per_day": events_per_day,
        }
        return todays_events, month, schedule

    @staticmethod
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

    @staticmethod
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


class RokuDashboardActionView(RokuDashboardView):
    """Route control commands to the shared allowlisted action handler."""

    url = "/api/roku_dashboard/{code}/action"
    name = "api:roku_dashboard_action"


def entry_for_code(hass, code: str):
    """Resolve a config entry by short pairing code or device credential."""
    return next(
        (
            item
            for item in hass.config_entries.async_entries(DOMAIN)
            if secrets.compare_digest(
                str(item.data.get(CONF_PAIRING_CODE, "")), code.upper()
            )
            or secrets.compare_digest(
                str(item.data.get(CONF_DEVICE_TOKEN, "")), code.upper()
            )
        ),
        None,
    )


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
        path = Path(self.hass.config.path("roku_dashboard", "background"))
        if not path.is_file():
            return self.json({"error": "no_background"}, status_code=404)
        content_type = (
            entry.options.get(CONF_BACKGROUND_TYPE)
            or mimetypes.guess_type(
                entry.options.get("background_name", path.name)
            )[0]
            or "image/jpeg"
        )
        return web.FileResponse(
            path,
            headers={"Content-Type": content_type, "Cache-Control": "no-store"},
        )
