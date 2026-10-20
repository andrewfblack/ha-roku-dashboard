"""Config and options flow for Roku Dashboard."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

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
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    BACKGROUNDS,
    CONF_BACKGROUND,
    CONF_BACKGROUND_URL,
    CONF_CALENDAR_ENTITIES,
    CONF_INDOOR_ENTITY,
    CONF_LAYOUT,
    CONF_MEAL_ENTITY,
    CONF_OUTDOOR_ENTITY,
    CREATE_NEW_MEAL_HELPER,
    DOMAIN,
    LAYOUTS,
    MEAL_HELPER_ENTITY,
)


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

    schema: dict[Any, Any] = {
        vol.Required(
            CONF_INDOOR_ENTITY,
            default=defaults.get(CONF_INDOOR_ENTITY, vol.UNDEFINED),
        ): indoor,
        vol.Optional(
            CONF_OUTDOOR_ENTITY,
            default=defaults.get(CONF_OUTDOOR_ENTITY, vol.UNDEFINED),
        ): outdoor,
        vol.Optional(
            CONF_CALENDAR_ENTITIES,
            default=defaults.get(CONF_CALENDAR_ENTITIES, vol.UNDEFINED),
        ): calendars,
        vol.Required(
            CONF_MEAL_ENTITY,
            default=defaults.get(CONF_MEAL_ENTITY, CREATE_NEW_MEAL_HELPER),
        ): meal,
        vol.Required(
            CONF_BACKGROUND,
            default=defaults.get(CONF_BACKGROUND, "fall"),
        ): background,
        vol.Optional(
            CONF_BACKGROUND_URL,
            default=defaults.get(CONF_BACKGROUND_URL, vol.UNDEFINED),
        ): vol.Coerce(str),
        vol.Required(
            CONF_LAYOUT,
            default=defaults.get(CONF_LAYOUT, "home"),
        ): layout,
    }
    return vol.Schema(schema)


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
            return self.async_create_entry(title="Roku Dashboard", data={}, options=user_input)

        return self.async_show_form(
            step_id="user", data_schema=_schema({}, self.hass)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> "RokuDashboardOptionsFlow":
        """Create the options flow."""
        return RokuDashboardOptionsFlow()


class RokuDashboardOptionsFlow(OptionsFlow):
    """Let the user change sensors, helper, background and layout later."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            if not user_input.get(CONF_BACKGROUND_URL):
                user_input.pop(CONF_BACKGROUND_URL, None)
            if user_input.get(CONF_MEAL_ENTITY) == CREATE_NEW_MEAL_HELPER:
                user_input[CONF_MEAL_ENTITY] = MEAL_HELPER_ENTITY
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                _schema({}, self.hass), self.config_entry.options
            ),
        )
