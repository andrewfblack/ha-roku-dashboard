# Roku Dashboard (Home Assistant + HACS)

A Home Assistant **custom integration** that configures the Roku "HA Home
Dashboard" channel from inside Home Assistant:

- 🍽️ **Creates and owns the meal-planner helper** — an `input_text`
  (`input_text.roku_dashboard_meal_plan`) is created for you, editable from
  the HA UI (Helpers), automations, or the `roku_dashboard.set_meal_plan`
  service. Its value is restored across restarts.
- 🌡️ **Pick the indoor sensor** — choose which temperature sensor (or
  climate entity) the TV shows as "Inside".
- 🌤️ **Pick the outdoor weather entity** (optional — auto-detects `weather.*`).
- 🌦️ **Configure the Weather tab** — enable/disable it, choose daily or
  hourly forecasts, and show 3–8 forecast periods.
- 💡 **Lights tab** — explicitly select which lights Roku may toggle and dim.
- 🎬 **Scenes tab** — explicitly select scenes/scripts Roku may activate.
- 🌡️ **Climate tab** — explicitly select thermostats Roku may adjust.
- 📅 **Pick which calendars to display** — select one or more calendar
  entities; only their events show on the Home tab. Leave empty to show all.
  The API provides today's agenda plus a full current-month overview.
- 🎨 **Backgrounds** — fall, winter, spring, summer presets, or your own
  image URL (served from `/local/...`).
- 🧱 **Layout presets** — `home`, `compact`, `meals_first` (and room for more
  later).
- 📡 **Everything is published on `sensor.roku_dashboard_config`** — a single
  JSON state the Roku channel reads, so future dashboard tweaks are made in
  HA instead of rebuilding the channel.
- 🔗 **Short-code pairing** — the TV uses an 8-character code instead of a
  long-lived Home Assistant access token. The local pairing endpoint exposes
  only the entities and calendars selected for this dashboard.

## Installation (HACS)

### As a custom repository
1. HACS → **Integrations** → ⋮ → **Custom repositories**.
2. Repository URL: `https://github.com/andrewfblack/ha-roku-dashboard`, category
   **Integration**.
3. Install **Roku Dashboard**, restart Home Assistant.

### Manual
Copy `custom_components/roku_dashboard/` into your HA config directory's
`custom_components/` folder and restart.

## Configuration

1. **Settings → Devices & services → Add integration → Roku Dashboard**.
2. In the setup form:
   - **Indoor temperature entity** (required) — e.g. `sensor.living_room_temperature`
     or a `climate.*` entity.
   - **Outdoor weather entity** (optional) — your `weather.*` entity.
   - **Calendars to display** (optional) — multi-select your calendar
     entities (Google/Outlook/etc. synced into HA). Empty = show all.
   - **Meal plan helper** — "Create new helper" (default) or pick an
     existing `input_text`/`text` helper.
   - **Background** / **Layout** — presets for the Roku channel.
3. Change anything later via the integration's **Configure** (options) flow —
   the config sensor updates immediately after reload.

## Entities & services

| Entity | Purpose |
|---|---|
| `sensor.roku_dashboard_config` | JSON with `indoor_entity`, `outdoor_entity`, `meal_entity`, `calendar_entities`, `background`, `background_url`, `layout` |
| `input_text.roku_dashboard_meal_plan` | The meal plan text (if using the managed helper) |

| Service | Example |
|---|---|
| `roku_dashboard.set_meal_plan` | `value: "Mon: Tacos\nTue: Pasta"` |
| `roku_dashboard.set_background` | `value: winter` |
| `roku_dashboard.set_layout` | `value: meals_first` |

Automate it — set Sunday's meals from a calendar, switch backgrounds with
the seasons:

```yaml
automation:
  - alias: Seasonal Roku background
    trigger:
      - platform: template
        value_template: "{{ now().month in [12, 1, 2] }}"
    action:
      - action: roku_dashboard.set_background
        data:
          value: "{{ 'winter' if now().month in [12,1,2] else 'fall' }}"
```

## How the Roku channel uses this

The companion Roku channel lives at
[andrewfblack/roku-ha-dashboard](https://github.com/andrewfblack/roku-ha-dashboard).
It connects using the `pairing_code` attribute shown on
`sensor.roku_dashboard_config`; no long-lived HA token is required on the TV.
The integration's local endpoint returns only the configured dashboard data.
Control requests are allowlisted: commands targeting an entity that was not
selected in the integration options are rejected.

- queries **only the selected calendars**,
- uses the configured **meal entity**,
- (v2) will apply **background** and **layout** presets and the configured
  indoor/outdoor entities.

Until the integration is installed, the channel falls back to its own
setup-screen settings and all-calendars behavior.

## Repository layout

```
hacs.json
custom_components/roku_dashboard/
  manifest.json          integration metadata (version, dependencies)
  const.py               option keys, presets, defaults
  __init__.py            entry setup, helper creation, value persistence
  config_flow.py         setup form + options flow (with reload)
  sensor.py              sensor.roku_dashboard_config
  services.py / .yaml    set_meal_plan, set_background, set_layout
  strings.json           UI strings (source)
  translations/en.json   UI strings (English)
```

## Notes & limits

- Requires Home Assistant **2024.12+** (uses modern options-flow APIs).
- The managed meal helper is created through the `input_text` integration;
  on HA versions without `input_text.async_create` the integration logs an
  error and you should create a text helper manually and select it in
  options (everything else keeps working).
- Background images must be reachable by the Roku device (e.g. served from
  HA's `/local/` folder or any LAN URL).
