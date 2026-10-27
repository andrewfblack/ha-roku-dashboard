"""Constants for the Family Dashboard integration."""

DOMAIN = "roku_dashboard"

# API namespaces. "family_dashboard" is the canonical namespace used by every
# client; "roku_dashboard" stays as an alias so already-sideloaded Roku
# channels keep working.
API_NAMESPACE = "family_dashboard"
LEGACY_API_NAMESPACE = "roku_dashboard"

# Per-device credential store (device id -> token, name, platform).
DEVICE_STORE_KEY = f"{DOMAIN}_devices"
DEVICE_STORE_VERSION = 1
DATA_DEVICES = "devices"
DATA_STREAM = "stream"

# Device-initiated pairing.
PAIRING_CODE_LENGTH = 8
PAIRING_CODE_TTL = 300
PAIRING_POLL_INTERVAL = 3
PAIRING_REQUEST_LIMIT = 10
DEVICE_TOUCH_INTERVAL = 300

# Platform identifiers a client can report when it asks to pair.
PLATFORMS = ("ios", "tvos", "roku", "web", "android", "legacy", "unknown")

# Version of the dashboard payload contract. Bump when the shape changes.
PAYLOAD_SCHEMA_VERSION = 3

CONF_INDOOR_ENTITY = "indoor_entity"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
CONF_SECONDARY_WEATHER_ENTITY = "secondary_weather_entity"
CONF_MEAL_ENTITY = "meal_entity"
CONF_BACKGROUND = "background"
CONF_LAYOUT = "layout"
CONF_CALENDAR_ENTITIES = "calendar_entities"
CONF_PAIRING_CODE = "pairing_code"
CONF_DEVICE_TOKEN = "device_token"
CONF_LEGACY_TOKEN_REVOKED = "legacy_token_revoked"
CONF_WEATHER_TAB_ENABLED = "weather_tab_enabled"
CONF_FORECAST_TYPE = "forecast_type"
CONF_FORECAST_COUNT = "forecast_count"
CONF_LIGHTS_TAB_ENABLED = "lights_tab_enabled"
CONF_LIGHT_ENTITIES = "light_entities"
CONF_SCENES_TAB_ENABLED = "scenes_tab_enabled"
CONF_SCENE_ENTITIES = "scene_entities"
CONF_CLIMATE_TAB_ENABLED = "climate_tab_enabled"
CONF_CLIMATE_ENTITIES = "climate_entities"
CONF_SECURITY_TAB_ENABLED = "security_tab_enabled"
CONF_SECURITY_COVER_ENTITIES = "security_cover_entities"
CONF_SECURITY_LOCK_ENTITIES = "security_lock_entities"
CONF_SECURITY_ALARM_ENTITY = "security_alarm_entity"
CONF_SECURITY_FAMILY_ENTITIES = "security_family_entities"
CONF_REMOTE_TAB_ENABLED = "remote_tab_enabled"
CONF_MEDIA_PLAYER_ENTITIES = "media_player_entities"
CONF_US_HOLIDAYS_ENABLED = "us_holidays_enabled"
CONF_US_OBSERVANCES_ENABLED = "us_observances_enabled"
CONF_BACKGROUND_FILE = "background_file"
CONF_BACKGROUND_NAME = "background_name"
CONF_BACKGROUND_TYPE = "background_type"
CONF_BACKGROUND_VERSION = "background_version"
CONF_CALENDAR_TAB_ENABLED = "calendar_tab_enabled"
CONF_CALENDAR_SCHEDULE_DAYS = "calendar_schedule_days"
CONF_CALENDAR_EVENTS_PER_DAY = "calendar_events_per_day"
CONF_NEXT_HOLIDAY_ENABLED = "next_holiday_enabled"
CONF_ACCESS_MODE = "access_mode"
CONF_DASHBOARD_TITLE = "dashboard_title"
CONF_INDOOR_HUMIDITY_ENTITY = "indoor_humidity_entity"
CONF_MEAL_MONDAY = "meal_monday"
CONF_MEAL_TUESDAY = "meal_tuesday"
CONF_MEAL_WEDNESDAY = "meal_wednesday"
CONF_MEAL_THURSDAY = "meal_thursday"
CONF_MEAL_FRIDAY = "meal_friday"
CONF_MEAL_SATURDAY = "meal_saturday"
CONF_MEAL_SUNDAY = "meal_sunday"
CONF_PANEL_ENABLED = "panel_enabled"
CONF_THEME_HEADER_TEXT = "theme_header_text"
CONF_THEME_ITEM_HEADER_TEXT = "theme_item_header_text"
CONF_THEME_BODY_TEXT = "theme_body_text"
CONF_THEME_MUTED_TEXT = "theme_muted_text"
CONF_THEME_ACCENT = "theme_accent"
CONF_THEME_BACKGROUND = "theme_background"
CONF_THEME_ITEM_BACKGROUND = "theme_item_background"
CONF_THEME_SELECTED_BACKGROUND = "theme_selected_background"
CONF_THEME_SELECTED_BORDER = "theme_selected_border"
CONF_THEME_ITEM_BORDER = "theme_item_border"
CONF_THEME_ITEM_OPACITY = "theme_item_opacity"
CONF_THEME_BACKGROUND_OVERLAY = "theme_background_overlay"

THEME_DEFAULTS = {
    CONF_THEME_HEADER_TEXT: [255, 247, 234],
    CONF_THEME_ITEM_HEADER_TEXT: [239, 178, 108],
    CONF_THEME_BODY_TEXT: [255, 247, 234],
    CONF_THEME_MUTED_TEXT: [205, 189, 169],
    CONF_THEME_ACCENT: [225, 138, 69],
    CONF_THEME_BACKGROUND: [23, 16, 11],
    CONF_THEME_ITEM_BACKGROUND: [31, 23, 17],
    CONF_THEME_SELECTED_BACKGROUND: [155, 84, 43],
    CONF_THEME_SELECTED_BORDER: [255, 210, 140],
    CONF_THEME_ITEM_BORDER: [89, 72, 60],
    CONF_THEME_ITEM_OPACITY: 90,
    CONF_THEME_BACKGROUND_OVERLAY: 48,
}

# The theme options that hold a colour.
THEME_COLOR_KEYS = [
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
]

# Home Assistant frontend panel (shown in the hamburger/sidebar menu).
PANEL_URL_PATH = "family-dashboard-panel"
PANEL_ELEMENT_NAME = "roku-dashboard-panel"
PANEL_JS_URL = "/family-dashboard/panel.js"
PANEL_ICON = "mdi:family-tree"

MEAL_DAY_KEYS = [
    CONF_MEAL_MONDAY,
    CONF_MEAL_TUESDAY,
    CONF_MEAL_WEDNESDAY,
    CONF_MEAL_THURSDAY,
    CONF_MEAL_FRIDAY,
    CONF_MEAL_SATURDAY,
    CONF_MEAL_SUNDAY,
]

ACCESS_MODES = {
    "lan": "LAN only",
    "tailscale": "LAN and Tailscale",
    "external": "LAN, Tailscale, and external HTTPS",
}
CONF_BACKGROUND_RESET = "background_reset"

FORECAST_TYPES = {
    "daily": "Daily forecast",
    "hourly": "Hourly forecast",
}

# Config-flow value meaning "create and use our own helper"
CREATE_NEW_MEAL_HELPER = "create_new"

# The helper this integration creates when you pick "Create new helper"
MEAL_HELPER_KEY = "roku_dashboard_meal_plan"
MEAL_HELPER_ENTITY = f"input_text.{MEAL_HELPER_KEY}"

# Presets the Roku channel understands (v2 reads them from
# sensor.roku_dashboard_config). "custom_url" lets you point at any image.
BACKGROUNDS = {
    "fall": "Fall",
    "winter": "Winter",
    "spring": "Spring",
    "summer": "Summer",
    "uploaded": "Uploaded image",
    "custom_url": "Custom image URL",
}
CONF_BACKGROUND_URL = "background_url"

LAYOUTS = {
    "home": "Home (calendar, meals, climate)",
    "compact": "Compact (climate first)",
    "meals_first": "Meals first",
}
CONF_MODULES = "modules"

STORAGE_KEY = f"{DOMAIN}_meal_plan"
STORAGE_VERSION = 1

CONFIG_SENSOR = f"sensor.{DOMAIN}_config"
