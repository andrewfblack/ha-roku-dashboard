"""Constants for the Roku Dashboard integration."""

DOMAIN = "roku_dashboard"

CONF_INDOOR_ENTITY = "indoor_entity"
CONF_OUTDOOR_ENTITY = "outdoor_entity"
CONF_MEAL_ENTITY = "meal_entity"
CONF_BACKGROUND = "background"
CONF_LAYOUT = "layout"
CONF_CALENDAR_ENTITIES = "calendar_entities"
CONF_PAIRING_CODE = "pairing_code"
CONF_DEVICE_TOKEN = "device_token"
CONF_WEATHER_TAB_ENABLED = "weather_tab_enabled"
CONF_FORECAST_TYPE = "forecast_type"
CONF_FORECAST_COUNT = "forecast_count"
CONF_LIGHTS_TAB_ENABLED = "lights_tab_enabled"
CONF_LIGHT_ENTITIES = "light_entities"
CONF_SCENES_TAB_ENABLED = "scenes_tab_enabled"
CONF_SCENE_ENTITIES = "scene_entities"
CONF_CLIMATE_TAB_ENABLED = "climate_tab_enabled"
CONF_CLIMATE_ENTITIES = "climate_entities"
CONF_US_HOLIDAYS_ENABLED = "us_holidays_enabled"
CONF_US_OBSERVANCES_ENABLED = "us_observances_enabled"
CONF_BACKGROUND_FILE = "background_file"
CONF_BACKGROUND_NAME = "background_name"
CONF_BACKGROUND_TYPE = "background_type"
CONF_BACKGROUND_VERSION = "background_version"
CONF_CALENDAR_TAB_ENABLED = "calendar_tab_enabled"
CONF_CALENDAR_SCHEDULE_DAYS = "calendar_schedule_days"
CONF_CALENDAR_EVENTS_PER_DAY = "calendar_events_per_day"
CONF_ACCESS_MODE = "access_mode"

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
