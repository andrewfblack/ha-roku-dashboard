"""Config and options flow for Family Dashboard."""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path
import secrets
import shutil
from typing import Any

import voluptuous as vol

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    FileSelector,
    FileSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import theme
from .const import (
    ACCESS_MODES,
    BACKGROUNDS,
    CONF_ACCESS_MODE,
    CONF_BACKGROUND,
    CONF_BACKGROUND_FILE,
    CONF_BACKGROUND_NAME,
    CONF_BACKGROUND_RESET,
    CONF_BACKGROUND_TYPE,
    CONF_BACKGROUND_URL,
    CONF_BACKGROUND_VERSION,
    CONF_CALENDAR_ENTITIES,
    CONF_CALENDAR_TAB_ENABLED,
    CONF_CALENDAR_SCHEDULE_DAYS,
    CONF_CALENDAR_EVENTS_PER_DAY,
    CONF_INDOOR_ENTITY,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CONF_SECONDARY_WEATHER_ENTITY,
    CONF_PANEL_ENABLED,
    CONF_WEATHER_TAB_ENABLED,
    CONF_FORECAST_TYPE,
    CONF_FORECAST_COUNT,
    CONF_LIGHTS_TAB_ENABLED,
    CONF_LIGHT_ENTITIES,
    CONF_SCENES_TAB_ENABLED,
    CONF_SCENE_ENTITIES,
    CONF_CLIMATE_TAB_ENABLED,
    CONF_CLIMATE_ENTITIES,
    CONF_PAIRING_CODE,
    CONF_DEVICE_TOKEN,
    CONF_DASHBOARD_TITLE,
    CONF_INDOOR_HUMIDITY_ENTITY,
    CONF_MEAL_MONDAY,
    CONF_MEAL_TUESDAY,
    CONF_MEAL_WEDNESDAY,
    CONF_MEAL_THURSDAY,
    CONF_MEAL_FRIDAY,
    CONF_MEAL_SATURDAY,
    CONF_MEAL_SUNDAY,
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
    CREATE_NEW_MEAL_HELPER,
    DOMAIN,
    LAYOUTS,
    FORECAST_TYPES,
    MEAL_HELPER_ENTITY,
    THEME_COLOR_KEYS,
    THEME_DEFAULTS,
)

_LOGGER = logging.getLogger(__name__)

# Label shown in the options menu and in the "saved" confirmation.
SECTION_LABELS = {
    "access": "Network access",
    "home": "Home tab",
    "meals": "Weekly meal plan",
    "calendar": "Calendar tab",
    "weather": "Weather tab",
    "lights": "Lights tab",
    "scenes": "Scenes and scripts",
    "climate": "Climate tab",
    "appearance": "Appearance",
    "theme": "Theme and colors",
    "panel": "Home Assistant menu",
    "pairing": "Pairing and security",
}

MENU_OPTIONS = [
    "access",
    "home",
    "meals",
    "calendar",
    "weather",
    "lights",
    "scenes",
    "climate",
    "appearance",
    "theme",
    "panel",
    "pairing",
]


def _theme_hex(value: Any, fallback: list[int]) -> str:
    """Return a theme colour as a hex string, whatever shape it is stored in.

    Colours are stored either as a hex string or as an RGB list, so both are
    accepted here and the form always shows the same value.
    """
    return theme.to_hex(value, fallback)


def _valid_theme_color(value: Any) -> bool:
    """Return True when a colour is a hex string such as #1F1711."""
    return theme.is_hex(value)


def _meal_entity_options(hass) -> list[dict[str, str]]:
    """Existing text helpers + the 'create new' option."""
    registry = er.async_get(hass)
    options: list[dict[str, str]] = [
        {
            "value": MEAL_HELPER_ENTITY,
            "label": "Roku Meal Plan helper (managed by this integration)",
        },
        {
            "value": CREATE_NEW_MEAL_HELPER,
            "label": "Create new helper (input_text.roku_dashboard_meal_plan)",
        },
    ]
    seen = {MEAL_HELPER_ENTITY}
    for entry in registry.entities.values():
        if entry.domain in ("input_text", "text") and entry.entity_id not in seen:
            seen.add(entry.entity_id)
            options.append({"value": entry.entity_id, "label": entry.entity_id})
    return options


def _schema(defaults: dict[str, Any], hass) -> vol.Schema:
    indoor = EntitySelector(
        EntitySelectorConfig(domain=["sensor", "climate"], multiple=False)
    )
    outdoor = EntitySelector(
        EntitySelectorConfig(domain=["weather"], multiple=False)
    )
    calendars = EntitySelector(
        EntitySelectorConfig(domain=["calendar"], multiple=True)
    )
    lights = EntitySelector(EntitySelectorConfig(domain=["light", "switch"], multiple=True))
    scenes = EntitySelector(
        EntitySelectorConfig(domain=["scene", "script"], multiple=True)
    )
    climates = EntitySelector(
        EntitySelectorConfig(domain=["climate"], multiple=True)
    )
    meal = SelectSelector(
        SelectSelectorConfig(
            options=_meal_entity_options(hass),
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    background = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": k, "label": v} for k, v in BACKGROUNDS.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    layout = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": k, "label": v} for k, v in LAYOUTS.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    forecast_type = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": k, "label": v} for k, v in FORECAST_TYPES.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    access_mode = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": key, "label": label} for key, label in ACCESS_MODES.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )

    schema: dict[Any, Any] = {
        vol.Required(
            CONF_ACCESS_MODE,
            default=defaults.get(CONF_ACCESS_MODE, "lan"),
        ): access_mode,
        vol.Required(
            CONF_INDOOR_ENTITY,
            default=defaults.get(CONF_INDOOR_ENTITY, vol.UNDEFINED),
        ): indoor,
        vol.Optional(
            CONF_INDOOR_HUMIDITY_ENTITY,
            default=defaults.get(CONF_INDOOR_HUMIDITY_ENTITY, vol.UNDEFINED),
        ): EntitySelector(EntitySelectorConfig(domain=["sensor"], multiple=False)),
        vol.Optional(
            CONF_OUTDOOR_ENTITY,
            default=defaults.get(CONF_OUTDOOR_ENTITY, vol.UNDEFINED),
        ): outdoor,
        vol.Optional(
            CONF_SECONDARY_WEATHER_ENTITY,
            default=defaults.get(CONF_SECONDARY_WEATHER_ENTITY, vol.UNDEFINED),
        ): outdoor,
        vol.Required(
            CONF_WEATHER_TAB_ENABLED,
            default=defaults.get(CONF_WEATHER_TAB_ENABLED, True),
        ): bool,
        vol.Required(
            CONF_FORECAST_TYPE,
            default=defaults.get(CONF_FORECAST_TYPE, "daily"),
        ): forecast_type,
        vol.Required(
            CONF_FORECAST_COUNT,
            default=defaults.get(CONF_FORECAST_COUNT, 5),
        ): vol.All(vol.Coerce(int), vol.Range(min=3, max=8)),
        vol.Required(
            CONF_LIGHTS_TAB_ENABLED,
            default=defaults.get(CONF_LIGHTS_TAB_ENABLED, True),
        ): bool,
        vol.Optional(
            CONF_LIGHT_ENTITIES,
            default=defaults.get(CONF_LIGHT_ENTITIES, vol.UNDEFINED),
        ): lights,
        vol.Required(
            CONF_SCENES_TAB_ENABLED,
            default=defaults.get(CONF_SCENES_TAB_ENABLED, True),
        ): bool,
        vol.Optional(
            CONF_SCENE_ENTITIES,
            default=defaults.get(CONF_SCENE_ENTITIES, vol.UNDEFINED),
        ): scenes,
        vol.Required(
            CONF_CLIMATE_TAB_ENABLED,
            default=defaults.get(CONF_CLIMATE_TAB_ENABLED, True),
        ): bool,
        vol.Optional(
            CONF_CLIMATE_ENTITIES,
            default=defaults.get(CONF_CLIMATE_ENTITIES, vol.UNDEFINED),
        ): climates,
        vol.Optional(
            CONF_CALENDAR_ENTITIES,
            default=defaults.get(CONF_CALENDAR_ENTITIES, vol.UNDEFINED),
        ): calendars,
        vol.Required(
            CONF_CALENDAR_TAB_ENABLED,
            default=defaults.get(CONF_CALENDAR_TAB_ENABLED, True),
        ): bool,
        vol.Required(
            CONF_CALENDAR_SCHEDULE_DAYS,
            default=defaults.get(CONF_CALENDAR_SCHEDULE_DAYS, 7),
        ): vol.All(vol.Coerce(int), vol.Range(min=3, max=7)),
        vol.Required(
            CONF_CALENDAR_EVENTS_PER_DAY,
            default=defaults.get(CONF_CALENDAR_EVENTS_PER_DAY, 5),
        ): vol.All(vol.Coerce(int), vol.Range(min=2, max=6)),
        vol.Required(
            CONF_US_HOLIDAYS_ENABLED,
            default=defaults.get(CONF_US_HOLIDAYS_ENABLED, True),
        ): bool,
        vol.Required(
            CONF_US_OBSERVANCES_ENABLED,
            default=defaults.get(CONF_US_OBSERVANCES_ENABLED, True),
        ): bool,
        vol.Required(
            CONF_MEAL_ENTITY,
            default=defaults.get(CONF_MEAL_ENTITY, CREATE_NEW_MEAL_HELPER),
        ): meal,
        vol.Required(
            CONF_BACKGROUND,
            default=defaults.get(CONF_BACKGROUND, "fall"),
        ): background,
        vol.Required(
            CONF_DASHBOARD_TITLE,
            default=defaults.get(CONF_DASHBOARD_TITLE, "Family Dashboard"),
        ): vol.All(vol.Coerce(str), vol.Length(min=1, max=60)),
        vol.Optional(
            CONF_BACKGROUND_URL,
            default=defaults.get(CONF_BACKGROUND_URL, vol.UNDEFINED),
        ): vol.Coerce(str),
        vol.Required(
            CONF_LAYOUT,
            default=defaults.get(CONF_LAYOUT, "home"),
        ): layout,
        vol.Required(
            CONF_PANEL_ENABLED,
            default=defaults.get(CONF_PANEL_ENABLED, True),
        ): bool,
    }
    return vol.Schema(schema)


def _section_schemas(defaults: dict[str, Any], hass) -> dict[str, vol.Schema]:
    """Build the smaller schemas used by the configuration menu."""
    indoor = EntitySelector(
        EntitySelectorConfig(domain=["sensor", "climate"], multiple=False)
    )
    outdoor = EntitySelector(EntitySelectorConfig(domain=["weather"], multiple=False))
    calendars = EntitySelector(
        EntitySelectorConfig(domain=["calendar"], multiple=True)
    )
    lights = EntitySelector(EntitySelectorConfig(domain=["light", "switch"], multiple=True))
    scenes = EntitySelector(
        EntitySelectorConfig(domain=["scene", "script"], multiple=True)
    )
    climates = EntitySelector(
        EntitySelectorConfig(domain=["climate"], multiple=True)
    )
    meal = SelectSelector(
        SelectSelectorConfig(
            options=_meal_entity_options(hass), mode=SelectSelectorMode.DROPDOWN
        )
    )
    background = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": key, "label": label} for key, label in BACKGROUNDS.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    layout = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": key, "label": label} for key, label in LAYOUTS.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    forecast = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": key, "label": label} for key, label in FORECAST_TYPES.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    access_mode = SelectSelector(
        SelectSelectorConfig(
            options=[{"value": key, "label": label} for key, label in ACCESS_MODES.items()],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )
    return {
        "access": vol.Schema(
            {
                vol.Required(
                    CONF_ACCESS_MODE,
                    default=defaults.get(CONF_ACCESS_MODE, "lan"),
                ): access_mode,
            }
        ),
        "home": vol.Schema(
            {
                vol.Required(
                    CONF_INDOOR_ENTITY,
                    default=defaults.get(CONF_INDOOR_ENTITY, vol.UNDEFINED),
                ): indoor,
                vol.Optional(
                    CONF_INDOOR_HUMIDITY_ENTITY,
                    default=defaults.get(CONF_INDOOR_HUMIDITY_ENTITY, vol.UNDEFINED),
                ): EntitySelector(
                    EntitySelectorConfig(domain=["sensor"], multiple=False)
                ),
            }
        ),
        "meals": vol.Schema(
            {
                vol.Required(
                    CONF_MEAL_ENTITY,
                    default=defaults.get(CONF_MEAL_ENTITY, MEAL_HELPER_ENTITY),
                ): meal,
                vol.Optional(CONF_MEAL_MONDAY, default=defaults.get(CONF_MEAL_MONDAY, "")): vol.Coerce(str),
                vol.Optional(CONF_MEAL_TUESDAY, default=defaults.get(CONF_MEAL_TUESDAY, "")): vol.Coerce(str),
                vol.Optional(CONF_MEAL_WEDNESDAY, default=defaults.get(CONF_MEAL_WEDNESDAY, "")): vol.Coerce(str),
                vol.Optional(CONF_MEAL_THURSDAY, default=defaults.get(CONF_MEAL_THURSDAY, "")): vol.Coerce(str),
                vol.Optional(CONF_MEAL_FRIDAY, default=defaults.get(CONF_MEAL_FRIDAY, "")): vol.Coerce(str),
                vol.Optional(CONF_MEAL_SATURDAY, default=defaults.get(CONF_MEAL_SATURDAY, "")): vol.Coerce(str),
                vol.Optional(CONF_MEAL_SUNDAY, default=defaults.get(CONF_MEAL_SUNDAY, "")): vol.Coerce(str),
            }
        ),
        "calendar": vol.Schema(
            {
                vol.Required(
                    CONF_CALENDAR_TAB_ENABLED,
                    default=defaults.get(CONF_CALENDAR_TAB_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_CALENDAR_ENTITIES,
                    default=defaults.get(CONF_CALENDAR_ENTITIES, vol.UNDEFINED),
                ): calendars,
                vol.Required(
                    CONF_CALENDAR_SCHEDULE_DAYS,
                    default=defaults.get(CONF_CALENDAR_SCHEDULE_DAYS, 7),
                ): vol.All(vol.Coerce(int), vol.Range(min=3, max=7)),
                vol.Required(
                    CONF_CALENDAR_EVENTS_PER_DAY,
                    default=defaults.get(CONF_CALENDAR_EVENTS_PER_DAY, 5),
                ): vol.All(vol.Coerce(int), vol.Range(min=2, max=6)),
                vol.Required(
                    CONF_US_HOLIDAYS_ENABLED,
                    default=defaults.get(CONF_US_HOLIDAYS_ENABLED, True),
                ): bool,
                vol.Required(
                    CONF_US_OBSERVANCES_ENABLED,
                    default=defaults.get(CONF_US_OBSERVANCES_ENABLED, True),
                ): bool,
            }
        ),
        "weather": vol.Schema(
            {
                vol.Required(
                    CONF_WEATHER_TAB_ENABLED,
                    default=defaults.get(CONF_WEATHER_TAB_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_OUTDOOR_ENTITY,
                    default=defaults.get(CONF_OUTDOOR_ENTITY, vol.UNDEFINED),
                ): outdoor,
                vol.Optional(
                    CONF_SECONDARY_WEATHER_ENTITY,
                    default=defaults.get(CONF_SECONDARY_WEATHER_ENTITY, vol.UNDEFINED),
                ): outdoor,
                vol.Required(
                    CONF_FORECAST_TYPE,
                    default=defaults.get(CONF_FORECAST_TYPE, "daily"),
                ): forecast,
                vol.Required(
                    CONF_FORECAST_COUNT,
                    default=defaults.get(CONF_FORECAST_COUNT, 5),
                ): vol.All(vol.Coerce(int), vol.Range(min=3, max=8)),
            }
        ),
        "lights": vol.Schema(
            {
                vol.Required(
                    CONF_LIGHTS_TAB_ENABLED,
                    default=defaults.get(CONF_LIGHTS_TAB_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_LIGHT_ENTITIES,
                    default=defaults.get(CONF_LIGHT_ENTITIES, vol.UNDEFINED),
                ): lights,
            }
        ),
        "scenes": vol.Schema(
            {
                vol.Required(
                    CONF_SCENES_TAB_ENABLED,
                    default=defaults.get(CONF_SCENES_TAB_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_SCENE_ENTITIES,
                    default=defaults.get(CONF_SCENE_ENTITIES, vol.UNDEFINED),
                ): scenes,
            }
        ),
        "climate": vol.Schema(
            {
                vol.Required(
                    CONF_CLIMATE_TAB_ENABLED,
                    default=defaults.get(CONF_CLIMATE_TAB_ENABLED, True),
                ): bool,
                vol.Optional(
                    CONF_CLIMATE_ENTITIES,
                    default=defaults.get(CONF_CLIMATE_ENTITIES, vol.UNDEFINED),
                ): climates,
            }
        ),
        "panel": vol.Schema(
            {
                vol.Required(
                    CONF_PANEL_ENABLED,
                    default=defaults.get(CONF_PANEL_ENABLED, True),
                ): bool,
            }
        ),
        "theme": vol.Schema(
            {
                vol.Required(
                    CONF_THEME_HEADER_TEXT,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_HEADER_TEXT),
                        THEME_DEFAULTS[CONF_THEME_HEADER_TEXT],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_ITEM_HEADER_TEXT,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_ITEM_HEADER_TEXT),
                        THEME_DEFAULTS[CONF_THEME_ITEM_HEADER_TEXT],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_BODY_TEXT,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_BODY_TEXT),
                        THEME_DEFAULTS[CONF_THEME_BODY_TEXT],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_MUTED_TEXT,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_MUTED_TEXT),
                        THEME_DEFAULTS[CONF_THEME_MUTED_TEXT],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_ACCENT,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_ACCENT),
                        THEME_DEFAULTS[CONF_THEME_ACCENT],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_BACKGROUND,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_BACKGROUND),
                        THEME_DEFAULTS[CONF_THEME_BACKGROUND],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_ITEM_BACKGROUND,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_ITEM_BACKGROUND),
                        THEME_DEFAULTS[CONF_THEME_ITEM_BACKGROUND],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_SELECTED_BACKGROUND,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_SELECTED_BACKGROUND),
                        THEME_DEFAULTS[CONF_THEME_SELECTED_BACKGROUND],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_SELECTED_BORDER,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_SELECTED_BORDER),
                        THEME_DEFAULTS[CONF_THEME_SELECTED_BORDER],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_ITEM_BORDER,
                    default=_theme_hex(
                        defaults.get(CONF_THEME_ITEM_BORDER),
                        THEME_DEFAULTS[CONF_THEME_ITEM_BORDER],
                    ),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
                vol.Required(
                    CONF_THEME_ITEM_OPACITY,
                    default=defaults.get(CONF_THEME_ITEM_OPACITY, THEME_DEFAULTS[CONF_THEME_ITEM_OPACITY]),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
                vol.Required(
                    CONF_THEME_BACKGROUND_OVERLAY,
                    default=defaults.get(CONF_THEME_BACKGROUND_OVERLAY, THEME_DEFAULTS[CONF_THEME_BACKGROUND_OVERLAY]),
                ): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }
        ),
        "appearance": vol.Schema(
            {
                vol.Required(
                    CONF_DASHBOARD_TITLE,
                    default=defaults.get(CONF_DASHBOARD_TITLE, "Family Dashboard"),
                ): vol.All(vol.Coerce(str), vol.Length(min=1, max=60)),
                vol.Required(
                    CONF_BACKGROUND,
                    default=defaults.get(CONF_BACKGROUND, "fall"),
                ): background,
                vol.Optional(CONF_BACKGROUND_FILE): FileSelector(
                    FileSelectorConfig(
                        accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
                    )
                ),
                vol.Required(
                    CONF_BACKGROUND_RESET,
                    default=defaults.get(CONF_BACKGROUND_RESET, False),
                ): bool,
                vol.Optional(
                    CONF_BACKGROUND_URL,
                    default=defaults.get(CONF_BACKGROUND_URL, vol.UNDEFINED),
                ): vol.Coerce(str),
                vol.Required(
                    CONF_LAYOUT, default=defaults.get(CONF_LAYOUT, "home")
                ): layout,
            }
        ),
    }


class RokuDashboardConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the setup form."""
        if user_input is not None:
            if user_input[CONF_MEAL_ENTITY] == CREATE_NEW_MEAL_HELPER:
                user_input[CONF_MEAL_ENTITY] = MEAL_HELPER_ENTITY
            await self.async_set_unique_id(DOMAIN)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="Family Dashboard", data={}, options=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_schema({}, self.hass)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "RokuDashboardOptionsFlow":
        """Create the options flow."""
        return RokuDashboardOptionsFlow()


class RokuDashboardOptionsFlow(OptionsFlow):
    """Sectioned Family Dashboard configurator."""

    _SECTION_KEYS = {
        "access": [CONF_ACCESS_MODE],
        "home": [
            CONF_INDOOR_ENTITY,
            CONF_INDOOR_HUMIDITY_ENTITY,
        ],
        "meals": [
            CONF_MEAL_ENTITY,
            CONF_MEAL_MONDAY,
            CONF_MEAL_TUESDAY,
            CONF_MEAL_WEDNESDAY,
            CONF_MEAL_THURSDAY,
            CONF_MEAL_FRIDAY,
            CONF_MEAL_SATURDAY,
            CONF_MEAL_SUNDAY,
        ],
        "calendar": [
            CONF_CALENDAR_TAB_ENABLED,
            CONF_CALENDAR_ENTITIES,
            CONF_CALENDAR_SCHEDULE_DAYS,
            CONF_CALENDAR_EVENTS_PER_DAY,
            CONF_US_HOLIDAYS_ENABLED,
            CONF_US_OBSERVANCES_ENABLED,
        ],
        "weather": [
            CONF_WEATHER_TAB_ENABLED,
            CONF_OUTDOOR_ENTITY,
            CONF_FORECAST_TYPE,
            CONF_FORECAST_COUNT,
        ],
        "lights": [CONF_LIGHTS_TAB_ENABLED, CONF_LIGHT_ENTITIES],
        "scenes": [CONF_SCENES_TAB_ENABLED, CONF_SCENE_ENTITIES],
        "climate": [CONF_CLIMATE_TAB_ENABLED, CONF_CLIMATE_ENTITIES],
        "panel": [CONF_PANEL_ENABLED],
        "theme": [
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
        ],
        "appearance": [
            CONF_DASHBOARD_TITLE,
            CONF_BACKGROUND,
            CONF_BACKGROUND_FILE,
            CONF_BACKGROUND_NAME,
            CONF_BACKGROUND_RESET,
            CONF_BACKGROUND_TYPE,
            CONF_BACKGROUND_URL,
            CONF_BACKGROUND_VERSION,
            CONF_LAYOUT,
        ],
    }

    def _async_menu(self, message: str = "") -> ConfigFlowResult:
        """Show the section menu, optionally with a status message."""
        return self.async_show_menu(
            step_id="init",
            menu_options=list(MENU_OPTIONS),
            description_placeholders={"message": message},
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the configuration section menu."""
        return self._async_menu()

    async def _async_section(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        if user_input is not None:
            options = dict(self.config_entry.options)
            for key in self._SECTION_KEYS[step_id]:
                options.pop(key, None)
            if user_input.get(CONF_MEAL_ENTITY) == CREATE_NEW_MEAL_HELPER:
                user_input[CONF_MEAL_ENTITY] = MEAL_HELPER_ENTITY
            if not user_input.get(CONF_BACKGROUND_URL):
                user_input.pop(CONF_BACKGROUND_URL, None)
            if step_id == "theme":
                errors = {
                    key: "invalid_color"
                    for key in THEME_COLOR_KEYS
                    if not _valid_theme_color(user_input.get(key))
                }
                if errors:
                    return self.async_show_form(
                        step_id=step_id,
                        data_schema=_section_schemas(
                            dict(self.config_entry.options), self.hass
                        )[step_id],
                        errors=errors,
                    )
                for key in THEME_COLOR_KEYS:
                    user_input[key] = _theme_hex(
                        user_input[key], THEME_DEFAULTS[key]
                    )
            options.update(user_input)
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=options
            )
            return self._async_menu(
                f"Saved the {SECTION_LABELS[step_id]} settings."
            )
        schema = _section_schemas(dict(self.config_entry.options), self.hass)[step_id]
        return self.async_show_form(step_id=step_id, data_schema=schema)

    async def async_step_home(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("home", user_input)

    async def async_step_meals(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("meals", user_input)

    async def async_step_access(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("access", user_input)

    async def async_step_calendar(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("calendar", user_input)

    async def async_step_weather(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("weather", user_input)

    async def async_step_lights(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("lights", user_input)

    async def async_step_scenes(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("scenes", user_input)

    async def async_step_climate(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("climate", user_input)

    async def async_step_panel(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("panel", user_input)

    async def async_step_theme(self, user_input=None) -> ConfigFlowResult:
        return await self._async_section("theme", user_input)

    async def async_step_appearance(self, user_input=None) -> ConfigFlowResult:
        schema = _section_schemas(dict(self.config_entry.options), self.hass)[
            "appearance"
        ]
        if user_input is None:
            return self.async_show_form(step_id="appearance", data_schema=schema)

        options = dict(self.config_entry.options)
        for key in self._SECTION_KEYS["appearance"]:
            options.pop(key, None)

        file_id = user_input.pop(CONF_BACKGROUND_FILE, None)
        reset = user_input.pop(CONF_BACKGROUND_RESET, False)
        if file_id:
            saved = await self._async_save_background(file_id)
            if saved is None:
                return self.async_show_form(
                    step_id="appearance",
                    data_schema=schema,
                    errors={"base": "upload_failed"},
                )
            user_input[CONF_BACKGROUND] = "uploaded"
            user_input[CONF_BACKGROUND_NAME] = saved["name"]
            user_input[CONF_BACKGROUND_TYPE] = saved["type"]
            user_input[CONF_BACKGROUND_VERSION] = saved["version"]
        elif reset:
            await self._async_delete_background()
            user_input[CONF_BACKGROUND] = "fall"
            user_input[CONF_BACKGROUND_FILE] = None
        else:
            # Preserve existing upload metadata when only other settings change.
            for key in (
                CONF_BACKGROUND_NAME,
                CONF_BACKGROUND_TYPE,
                CONF_BACKGROUND_VERSION,
            ):
                if key in self.config_entry.options:
                    user_input[key] = self.config_entry.options[key]

        if not user_input.get(CONF_BACKGROUND_URL):
            user_input.pop(CONF_BACKGROUND_URL, None)
        options.update(user_input)
        self.hass.config_entries.async_update_entry(
            self.config_entry, options=options
        )
        return self._async_menu(
            f"Saved the {SECTION_LABELS['appearance']} settings."
        )

    def _background_path(self) -> Path:
        return Path(self.hass.config.path("roku_dashboard", "background"))

    async def _async_save_background(self, file_id: str) -> dict[str, str] | None:
        destination = self._background_path()

        def _copy(source: Path) -> None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)

        try:
            with process_uploaded_file(self.hass, file_id) as source:
                name = source.name
                content_type = (
                    mimetypes.guess_type(name)[0]
                    or self.config_entry.options.get(CONF_BACKGROUND_TYPE)
                    or "image/jpeg"
                )
                await self.hass.async_add_executor_job(_copy, source)
        except Exception:
            _LOGGER.exception("Unable to save Roku background upload")
            return None
        return {
            "name": name,
            "type": content_type,
            "version": secrets.token_hex(6),
        }

    async def _async_delete_background(self) -> None:
        path = self._background_path()
        await self.hass.async_add_executor_job(
            lambda: path.unlink(missing_ok=True)
        )

    async def async_step_pairing(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            if user_input.get("reset_pairing", False):
                data = dict(self.config_entry.data)
                data[CONF_PAIRING_CODE] = secrets.token_hex(4).upper()
                data[CONF_DEVICE_TOKEN] = secrets.token_hex(32).upper()
                self.hass.config_entries.async_update_entry(
                    self.config_entry, data=data
                )
                return self._async_menu(
                    "Pairing was reset. Use the new pairing code on your device."
                )
            return self._async_menu(
                f"Saved the {SECTION_LABELS['pairing']} settings."
            )
        return self.async_show_form(
            step_id="pairing",
            data_schema=vol.Schema({vol.Required("reset_pairing", default=False): bool}),
            description_placeholders={
                "pairing_code": self.config_entry.data.get(CONF_PAIRING_CODE, "")
            },
        )
