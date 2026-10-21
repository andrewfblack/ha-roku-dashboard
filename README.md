# Family Dashboard (Home Assistant + HACS)

![Family Dashboard logo](custom_components/roku_dashboard/brand/logo.png)

A Home Assistant **custom integration** that configures the Roku "HA Home
Dashboard" channel from inside Home Assistant:

It also includes an interactive, installable web app at `/family-dashboard`
with the same Home, Calendar, Weather, Lights, Scenes, and Climate experience.

- 🍽️ **Creates and owns the meal-planner helper** — an `input_text`
  (`input_text.roku_dashboard_meal_plan`) is created for you, editable from
  the HA UI (Helpers), automations, or the `roku_dashboard.set_meal_plan`
  service. Its value is restored across restarts.
- 📋 **Weekly meals** — configure Monday–Sunday meals; Home shows today and
  opens an editable complete week when selected. Changes from web or Roku are
  saved back to Home Assistant. The legacy helper remains a fallback.
- 🌡️ **Pick the indoor sensor** — choose which temperature sensor (or
  climate entity) the TV shows as "Inside".
- 💧 **Separate indoor humidity** — optionally select a dedicated humidity
  sensor instead of relying on the climate entity.
- 🌤️ **Pick the outdoor weather entity** (optional — auto-detects `weather.*`).
- 🌦️ **Configure the Weather tab** — enable/disable it, choose daily or
  hourly forecasts, and show 3–8 forecast periods.
- 💡 **Lights tab** — explicitly select which lights Roku may toggle and dim.
- 🎬 **Scenes tab** — explicitly select scenes/scripts Roku may activate.
- 🌡️ **Climate tab** — explicitly select thermostats Roku may adjust.
- 📅 **Pick which calendars to display** — select one or more calendar
  entities; only their events show on the Home tab. Leave empty to show all.
  The API provides today's agenda, a month grid, and every current-month event
  for the Roku's scrollable agenda.
- 🗓️ **Skylight-style schedule** — configure a dedicated rolling Calendar tab
  with 3–7 color-coded day columns and 2–6 visible events per day.
- 🇺🇸 **US federal holidays** — optionally adds federal holidays and weekend
  observed dates locally, without another calendar account or cloud API.
- 💝 **Common US observances** — optionally adds Groundhog Day, Valentine's
  Day, Mardi Gras, St. Patrick's Day, April Fools' Day, Easter, Mother's Day,
  Flag Day, Father's Day, Halloween, and New Year's Eve.
- 🎨 **Backgrounds** — fall, winter, spring, summer presets, an uploaded image
  from your device, or your own image URL (served from `/local/...`). Uploads
  are stored by Home Assistant and served only to paired Roku devices.
- 🧱 **Layout presets** — `home`, `compact`, `meals_first` (and room for more
  later).
- 📡 **Everything is published on `sensor.roku_dashboard_config`** — a single
  JSON state the Roku channel reads, so future dashboard tweaks are made in
  HA instead of rebuilding the channel.
- 🔗 **Short-code pairing** — the TV uses an 8-character code instead of a
  long-lived Home Assistant access token. The local pairing endpoint exposes
  only the entities and calendars selected for this dashboard.
- 🌐 **Interactive PWA** — mouse/touch controls, fullscreen display, screen
  wake lock, automatic refresh, and install-to-home-screen support.
- 🍔 **Home Assistant panel** — optional entry in the Home Assistant
  (hamburger) menu that shows the dashboard and lets you change the dashboard
  configuration without leaving Home Assistant.
- ↩️ **Settings you can walk back out of** — every section of the configurator
  has a "back to the options menu" toggle, and saving a section returns to the
  section list instead of closing the dialog.
- 🔒 **Network policy** — LAN-only by default, with explicit LAN + Tailscale
  and external HTTPS modes. Short-code pairing remains local/Tailscale only.

## Installation (HACS)

### As a custom repository
1. HACS → **Integrations** → ⋮ → **Custom repositories**.
2. Repository URL: `https://github.com/andrewfblack/ha-roku-dashboard`, category
   **Integration**.
3. Install **Family Dashboard**, restart Home Assistant.

### Manual
Copy `custom_components/roku_dashboard/` into your HA config directory's
`custom_components/` folder and restart.

## Configuration

1. **Settings → Devices & services → Add integration → Family Dashboard**.
2. In the setup form:
   - **Indoor temperature entity** (required) — e.g. `sensor.living_room_temperature`
     or a `climate.*` entity.
   - **Outdoor weather entity** (optional) — your `weather.*` entity.
   - **Calendars to display** (optional) — multi-select your calendar
     entities (Google/Outlook/etc. synced into HA). Empty = show all.
   - **Meal plan helper** — "Create new helper" (default) or pick an
     existing `input_text`/`text` helper.
   - **Background** / **Layout** — presets for the Roku channel.
3. Change anything later via the integration's **Configure** button. It opens
   a sectioned configurator for Network Access, Home, Calendar, Weather, Lights,
   Scenes/Scripts, Climate, Appearance, Home Assistant menu, and
   Pairing/Security. The config sensor and Roku endpoint update immediately
   after each saved section.

   Every section form ends with a **"Go back to the options menu (changes are
   discarded)"** toggle: turn it on and submit to leave the section without
   saving. Saving a section keeps the dialog open and returns to the section
   list, so you can continue with another section (or close the dialog when
   you are done).

The Pairing/Security screen displays the current short pairing code and can
revoke paired Roku credentials. Reset pairing only when you intend to reconnect
the TV with a newly generated code.

## Home Assistant panel

**Configure → Home Assistant menu → Show Family Dashboard in the Home
Assistant menu** adds a *Family Dashboard* entry to the Home Assistant sidebar
(hamburger) menu.

- The panel shows the same dashboard as the web app — Home, Calendar, Weather,
  Lights, Scenes and Climate tabs — without a pairing code, because it uses
  your Home Assistant session.
- Administrators get a **⚙ Settings** button that opens the dashboard
  configuration (name, background, layout, tabs, entities and the weekly meal
  plan) right inside the panel. Changes are written back to the integration
  options and reach the Roku and the web app immediately.
- Turning the option off removes the menu entry again.

The panel lives at `/family-dashboard-panel`; the standalone web app stays at
`/family-dashboard`.

## Web app

After restarting Home Assistant, open:

```text
http://<home-assistant-ip>:8123/family-dashboard
```

Enter the current short pairing code once. The browser stores the exchanged
device credential locally. Use the browser's install action to add it as a PWA.

Network modes under **Configure → Network access**:

- **LAN only** (default): private/local addresses only.
- **LAN and Tailscale**: also permits the `100.64.0.0/10` Tailscale range.
- **External HTTPS**: permits an already-paired client through Nabu Casa or a
  trusted HTTPS reverse proxy. Pairing codes are still rejected publicly.

On **Appearance**, use **Upload background image** to select a JPEG, PNG, or
WebP from your device. Uploading selects it automatically; **Remove uploaded
background** deletes it and restores Fall. The file is stored under the Home
Assistant config directory and is not added to any public media folder.
Appearance also controls the dashboard name displayed by web and Roku clients.

Both the web and Roku clients return to Home after five minutes without input.
The Climate interfaces use matching generated artwork for Heat, Cool, Auto,
Heat/Cool, Dry, Fan, and Off modes.

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
  config_flow.py         setup form + options flow (with reload, back button)
  sensor.py              sensor.roku_dashboard_config
  panel.py               Home Assistant menu panel + panel REST API
  api.py                 paired Roku API (data + control commands)
  web.py                 serves the web app (/family-dashboard)
  services.py / .yaml    set_meal_plan, set_background, set_layout
  strings.json           UI strings (source)
  translations/en.json   UI strings (English)
  www/                   web app, shared rendering and the panel frontend
```

## Notes & limits

- Requires Home Assistant **2024.12+** (uses modern options-flow APIs).
- The managed meal helper is created through the `input_text` integration;
  on HA versions without `input_text.async_create` the integration logs an
  error and you should create a text helper manually and select it in
  options (everything else keeps working).
- Background images must be reachable by the Roku device (e.g. served from
  HA's `/local/` folder or any LAN URL).
