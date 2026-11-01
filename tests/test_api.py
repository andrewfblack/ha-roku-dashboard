"""Tests for the client API: credentials, the payload contract and actions."""

from __future__ import annotations

import json

import pytest

from conftest import FakeRequest
from roku_dashboard import api, pairing


@pytest.mark.asyncio
async def test_bearer_header_resolves_a_device(hass):
    """A device is recognised by its Authorization header."""
    device = await pairing.async_add_device(hass, "iPhone", "ios")
    request = FakeRequest(headers={"Authorization": f"Bearer {device['token']}"})

    entry, resolved = await api._resolve_client(hass, request)

    assert entry is not None
    assert resolved["device_id"] == device["device_id"]


@pytest.mark.asyncio
async def test_path_token_resolves_a_device(hass):
    """A device is recognised by the token in the URL."""
    device = await pairing.async_add_device(hass, "Apple TV", "tvos")
    request = FakeRequest()

    entry, resolved = await api._resolve_client(hass, request, device["token"])

    assert entry is not None
    assert resolved["device_id"] == device["device_id"]


@pytest.mark.asyncio
async def test_unknown_credentials_are_rejected(hass):
    """A made up token resolves to nothing."""
    entry, resolved = await api._resolve_client(hass, FakeRequest(), "NOPE")

    assert entry is None
    assert resolved is None


@pytest.mark.asyncio
async def test_legacy_token_still_works(hass):
    """Installs that paired before per-device tokens keep working."""
    request = FakeRequest()

    entry, resolved = await api._resolve_client(hass, request, "LEGACYTOKEN")

    assert entry is not None
    assert resolved is None


@pytest.mark.asyncio
async def test_entry_for_code_finds_a_device_token(hass):
    """The legacy namespace accepts per-device credentials too."""
    device = await pairing.async_add_device(hass, "Roku", "roku")

    assert api.entry_for_code(hass, device["token"]) is not None
    assert api.entry_for_code(hass, "A1B2C3D4") is not None
    assert api.entry_for_code(hass, "") is None


@pytest.mark.asyncio
async def test_payload_declares_the_contract(hass, entry):
    """The payload tells a client which version and features it has."""
    entry.options = {"weather_tab_enabled": False}

    payload = await api.async_dashboard_payload(hass, entry)

    assert payload["ok"] is True
    assert payload["schema_version"] == 3
    assert payload["dashboard_id"] == entry.entry_id
    assert payload["server_time"]
    assert "light_toggle" in payload["capabilities"]["actions"]
    assert "remote_command" in payload["capabilities"]["actions"]
    assert payload["capabilities"]["stream"] is True


@pytest.mark.asyncio
async def test_payload_theme_colors_are_hex(hass, entry):
    """Colours arrive ready to use, so no client has to convert them."""
    entry.options = {"weather_tab_enabled": False}

    payload = await api.async_dashboard_payload(hass, entry)

    for key, value in payload["theme"].items():
        if isinstance(value, str):
            assert value.startswith("#")
            assert len(value) == 7


@pytest.mark.asyncio
async def test_payload_carries_the_configured_entities(hass, entry):
    """Only the entities the dashboard was configured with are sent."""
    entry.options = {
        "weather_tab_enabled": False,
        "indoor_entity": "sensor.inside",
        "light_entities": ["light.kitchen"],
    }
    hass.states.set("sensor.inside", "21.5", {"friendly_name": "Inside"})
    hass.states.set("light.kitchen", "on", {"friendly_name": "Kitchen"})
    hass.states.set("light.garage", "off", {"friendly_name": "Garage"})

    payload = await api.async_dashboard_payload(hass, entry)

    assert payload["resolved_entities"]["inside"] == "sensor.inside"
    assert [card["entity_id"] for card in payload["lights"]] == ["light.kitchen"]
    assert "light.garage" not in payload["states"]


@pytest.mark.asyncio
async def test_actions_are_allowlisted(hass, entry):
    """A command for an entity that was never selected is refused."""
    entry.options = {"light_entities": ["light.kitchen"]}
    hass.states.set("light.kitchen", "off", {"friendly_name": "Kitchen"})

    result, status = await api.async_execute_action(
        hass, entry, {"action": "light_toggle", "entity_id": "light.garage"}
    )
    assert status == 403
    assert result["error"] == "not_allowed"

    result, status = await api.async_execute_action(
        hass, entry, {"action": "light_toggle", "entity_id": "light.kitchen"}
    )
    assert status == 200
    assert result["ok"] is True
    assert hass.services.calls[-1][:2] == ("light", "toggle")


@pytest.mark.asyncio
async def test_payload_builds_an_ios_remote(hass, entry):
    """Configured media players carry a player-specific command layout."""
    entry.options = {
        "remote_tab_enabled": True,
        "media_player_entities": ["media_player.living_room_roku"],
    }
    hass.states.set(
        "media_player.living_room_roku",
        "playing",
        {
            "friendly_name": "Living Room Roku",
            "media_title": "Family Movie",
            "volume_level": 0.35,
            "source_list": ["Home", "Netflix"],
            "supported_features": 19_849,
        },
    )
    hass.states.set("remote.living_room_roku", "on")

    payload = await api.async_dashboard_payload(hass, entry)

    assert payload["tabs"]["remote"] is True
    assert payload["remotes"][0]["kind"] == "roku"
    assert payload["remotes"][0]["remote_entity_id"] == "remote.living_room_roku"
    assert payload["remotes"][0]["room"] == "Other"
    assert "replay" in payload["remotes"][0]["commands"]
    assert "options" in payload["remotes"][0]["commands"]
    assert set(payload["remotes"][0]["capabilities"]) == {
        "turn_on",
        "turn_off",
        "volume_step",
        "volume_mute",
        "play_pause",
        "select_source",
    }


@pytest.mark.asyncio
async def test_apple_tv_remote_matches_registry_device_with_different_entity_id(
    hass, entry, monkeypatch
):
    """Apple TV remote entity ids need not match the media-player entity id."""
    class RegistryEntry:
        def __init__(self, entity_id, platform, device_id, config_entry_id):
            self.entity_id = entity_id
            self.platform = platform
            self.device_id = device_id
            self.config_entry_id = config_entry_id

    class Registry:
        entities = {
            "player": RegistryEntry("media_player.family_room", "apple_tv", "player_device", "apple_entry"),
            "remote": RegistryEntry("remote.family_room_remote", "apple_tv", "remote_device", "apple_entry"),
        }

        def async_get(self, entity_id):
            return next(
                (item for item in self.entities.values() if item.entity_id == entity_id),
                None,
            )

    monkeypatch.setattr(api.er, "async_get", lambda _hass: Registry())
    entry.options = {"media_player_entities": ["media_player.family_room"]}
    hass.states.set("media_player.family_room", "playing", {"friendly_name": "Family Room"})
    hass.states.set("remote.family_room_remote", "on")

    payload = await api.async_dashboard_payload(hass, entry)

    remote = payload["remotes"][0]
    assert remote["kind"] == "apple_tv"
    assert remote["remote_entity_id"] == "remote.family_room_remote"
    assert "up" in remote["commands"]
    assert "menu" in remote["commands"]

    result, status = await api.async_execute_action(
        hass,
        entry,
        {
            "action": "remote_command",
            "entity_id": "media_player.family_room",
            "command": "right",
        },
    )
    assert status == 200
    assert result["ok"] is True
    assert hass.services.calls[-1] == (
        "remote",
        "send_command",
        {"entity_id": "remote.family_room_remote", "command": "right"},
    )


@pytest.mark.asyncio
async def test_remote_room_and_device_type_can_be_configured(hass, entry):
    """Room and layout type overrides are included in the iOS payload."""
    entry.options = {
        "media_player_entities": ["media_player.screen"],
        "remote_device_config": {
            "media_player.screen": {"room": "Den", "kind": "apple_tv"}
        },
    }
    hass.states.set("media_player.screen", "playing", {"friendly_name": "Streamer"})
    hass.states.set("remote.screen", "on")

    payload = await api.async_dashboard_payload(hass, entry)

    assert payload["remotes"][0]["room"] == "Den"
    assert payload["remotes"][0]["kind"] == "apple_tv"

    result, status = await api.async_execute_action(
        hass,
        entry,
        {
            "action": "remote_command",
            "entity_id": "media_player.screen",
            "command": "back",
        },
    )
    assert status == 200
    assert result["ok"] is True
    assert hass.services.calls[-1] == (
        "remote",
        "send_command",
        {"entity_id": "remote.screen", "command": "menu"},
    )


@pytest.mark.asyncio
async def test_payload_includes_configured_remotes_without_order_preferences(hass, entry):
    """The server sends selected remotes; iOS orders them locally."""
    entry.options = {
        "media_player_entities": ["media_player.den", "media_player.bedroom"],
    }
    hass.states.set("media_player.den", "off", {"friendly_name": "Den"})
    hass.states.set("media_player.bedroom", "off", {"friendly_name": "Bedroom"})

    payload = await api.async_dashboard_payload(hass, entry)

    assert {item["entity_id"] for item in payload["remotes"]} == {
        "media_player.den",
        "media_player.bedroom",
    }
    assert "order" not in payload["tabs"]


@pytest.mark.asyncio
async def test_remote_actions_are_allowlisted_and_translated(hass, entry):
    """Only selected players receive semantic remote commands."""
    entry.options = {"media_player_entities": ["media_player.living_room_roku"]}
    hass.states.set(
        "media_player.living_room_roku",
        "playing",
        {
            "friendly_name": "Living Room Roku",
            "is_volume_muted": False,
            "supported_features": 1_025,
        },
    )
    hass.states.set("remote.living_room_roku", "on")

    result, status = await api.async_execute_action(
        hass,
        entry,
        {
            "action": "remote_command",
            "entity_id": "media_player.living_room_roku",
            "command": "select",
        },
    )
    assert status == 200
    assert result["ok"] is True
    assert hass.services.calls[-1] == (
        "remote",
        "send_command",
        {"entity_id": "remote.living_room_roku", "command": "select"},
    )

    result, status = await api.async_execute_action(
        hass,
        entry,
        {
            "action": "remote_command",
            "entity_id": "media_player.unselected",
            "command": "home",
        },
    )
    assert status == 403
    assert result["error"] == "not_allowed"


@pytest.mark.asyncio
async def test_remote_rejects_unsupported_media_controls(hass, entry):
    """Configured players cannot receive unsupported media-player services."""
    entry.options = {"media_player_entities": ["media_player.read_only"]}
    hass.states.set("media_player.read_only", "playing", {"supported_features": 0})

    result, status = await api.async_execute_action(
        hass,
        entry,
        {"action": "media_play_pause", "entity_id": "media_player.read_only"},
    )

    assert status == 400
    assert result["error"] == "unsupported_feature"
    assert not hass.services.calls


@pytest.mark.asyncio
async def test_power_control_checks_the_player_state_and_features(hass, entry):
    """Power only invokes a supported direction for the current state."""
    entry.options = {"media_player_entities": ["media_player.power_only"]}
    hass.states.set(
        "media_player.power_only",
        "off",
        {"supported_features": 128},  # turn_on only
    )

    result, status = await api.async_execute_action(
        hass,
        entry,
        {"action": "media_power", "entity_id": "media_player.power_only"},
    )
    assert status == 200
    assert result["ok"] is True
    assert hass.services.calls[-1][:2] == ("media_player", "turn_on")

    hass.states.set(
        "media_player.power_only",
        "on",
        {"supported_features": 128},  # turn_off is not supported
    )
    result, status = await api.async_execute_action(
        hass,
        entry,
        {"action": "media_power", "entity_id": "media_player.power_only"},
    )
    assert status == 400
    assert result["error"] == "unsupported_feature"


@pytest.mark.asyncio
async def test_lg_remote_uses_the_webos_button_service(hass, entry):
    """LG navigation works without a separate remote entity."""
    entry.options = {"media_player_entities": ["media_player.lg_webos_tv"]}
    hass.states.set(
        "media_player.lg_webos_tv",
        "on",
        {"friendly_name": "LG webOS TV"},
    )

    payload = await api.async_dashboard_payload(hass, entry)
    assert payload["remotes"][0]["kind"] == "lg"
    assert "select" in payload["remotes"][0]["commands"]

    result, status = await api.async_execute_action(
        hass,
        entry,
        {
            "action": "remote_command",
            "entity_id": "media_player.lg_webos_tv",
            "command": "select",
        },
    )
    assert status == 200
    assert result["ok"] is True
    assert hass.services.calls[-1] == (
        "webostv",
        "button",
        {"entity_id": "media_player.lg_webos_tv", "button": "ENTER"},
    )


@pytest.mark.asyncio
async def test_roku_transport_buttons_use_remote_commands(hass, entry):
    """Backward and forward use the actual Roku remote keys."""
    entry.options = {"media_player_entities": ["media_player.den_roku"]}
    hass.states.set("media_player.den_roku", "playing", {"friendly_name": "Den Roku"})
    hass.states.set("remote.den_roku", "on")

    for semantic, command in (("reverse", "reverse"), ("forward", "forward")):
        result, status = await api.async_execute_action(
            hass,
            entry,
            {
                "action": "remote_command",
                "entity_id": "media_player.den_roku",
                "command": semantic,
            },
        )
        assert status == 200
        assert result["ok"] is True
        assert hass.services.calls[-1] == (
            "remote",
            "send_command",
            {"entity_id": "remote.den_roku", "command": command},
        )


@pytest.mark.asyncio
async def test_apple_tv_commands_use_home_assistant_command_names(hass, entry, monkeypatch):
    """Apple TV semantic keys map to the commands expected by its integration."""
    class RegistryEntry:
        entity_id = "remote.family_room"
        platform = "apple_tv"
        device_id = "device1"
        config_entry_id = "apple_entry"

    class Registry:
        entities = {"remote": RegistryEntry()}

        def async_get(self, entity_id):
            return None

    monkeypatch.setattr(api.er, "async_get", lambda _hass: Registry())
    entry.options = {"media_player_entities": ["media_player.family_room"]}
    hass.states.set("media_player.family_room", "playing", {"friendly_name": "Apple TV"})
    hass.states.set("remote.family_room", "on")

    for semantic, expected in (
        ("up", "up"),
        ("select", "select"),
        ("back", "menu"),
        ("home", "home"),
        ("menu", "top_menu"),
        ("reverse", "skip_backward"),
        ("forward", "skip_forward"),
    ):
        result, status = await api.async_execute_action(
            hass,
            entry,
            {
                "action": "remote_command",
                "entity_id": "media_player.family_room",
                "command": semantic,
            },
        )
        assert status == 200
        assert result["ok"] is True
        assert hass.services.calls[-1] == (
            "remote",
            "send_command",
            {"entity_id": "remote.family_room", "command": expected},
        )


@pytest.mark.asyncio
async def test_tracked_entities_follow_the_configuration(hass, entry):
    """The stream only pushes the entities the dashboard shows."""
    entry.options = {
        "indoor_entity": "sensor.inside",
        "light_entities": ["light.kitchen"],
        "scene_entities": ["script.movie"],
    }

    tracked = api.tracked_entities(entry)

    assert "sensor.inside" in tracked
    assert "light.kitchen" in tracked
    assert "script.movie" in tracked
    assert "light.garage" not in tracked


@pytest.mark.asyncio
async def test_stream_publishes_state_changes(hass, entry):
    """A change to a displayed entity reaches the connected clients."""
    entry.options = {"light_entities": ["light.kitchen"]}
    hub = api.stream_hub(hass)
    queue = hub.subscribe()

    await api.setup_state_stream(hass, entry)
    hass.bus.fire(
        "state_changed",
        {
            "entity_id": "light.kitchen",
            "new_state": type(
                "State", (), {"state": "on", "attributes": {"brightness": 128}}
            )(),
        },
    )

    event, data = await queue.get()
    assert event == "state"
    assert data["entity_id"] == "light.kitchen"
    assert data["state"] == "on"


@pytest.mark.asyncio
async def test_pairing_flow_through_the_api(hass):
    """A device asks, waits, and receives its credential."""
    request_view = api.FamilyDashboardPairingRequestView(hass)
    response = await request_view.post(
        FakeRequest(body={"device_name": "Apple TV", "platform": "tvos"})
    )
    assert response.status == 200
    body = json.loads(response.text)
    code = body["device_code"]
    assert body["expires_in"] == 300

    status_view = api.FamilyDashboardPairingStatusView(hass)
    response = await status_view.get(FakeRequest(query={"device_code": code}))
    assert json.loads(response.text)["status"] == "pending"

    await pairing.async_approve(hass, code)
    response = await status_view.get(FakeRequest(query={"device_code": code}))
    body = json.loads(response.text)
    assert body["status"] == "approved"
    assert body["device_token"]

    # The credential is only handed over once.
    response = await status_view.get(FakeRequest(query={"device_code": code}))
    assert json.loads(response.text)["status"] == "consumed"


@pytest.mark.asyncio
async def test_pairing_request_is_refused_outside_the_local_network(hass):
    """Pairing only happens from the local network or over Tailscale."""
    request_view = api.FamilyDashboardPairingRequestView(hass)
    response = await request_view.post(
        FakeRequest(remote="8.8.8.8", body={"device_name": "Apple TV"})
    )
    assert response.status == 403


@pytest.mark.asyncio
async def test_device_endpoint_needs_a_credential(hass, entry):
    """The dashboard is not readable without one."""
    view = api.FamilyDashboardDataView(hass)

    response = await view.get(FakeRequest())
    assert response.status == 401

    device = await pairing.async_add_device(hass, "iPhone", "ios")
    response = await view.get(
        FakeRequest(headers={"Authorization": f"Bearer {device['token']}"})
    )
    assert response.status == 200
    assert json.loads(response.text)["device_id"] == device["device_id"]


@pytest.mark.asyncio
async def test_action_endpoint_needs_a_credential(hass, entry):
    """A command without a credential is refused."""
    view = api.FamilyDashboardActionView(hass)

    response = await view.post(FakeRequest(body={"action": "light_toggle"}))
    assert response.status == 401

    device = await pairing.async_add_device(hass, "iPhone", "ios")
    response = await view.post(
        FakeRequest(
            headers={"Authorization": f"Bearer {device['token']}"},
            body={"action": "light_toggle", "entity_id": "light.kitchen"},
        )
    )
    assert response.status == 403  # the entity is not part of the dashboard


@pytest.mark.asyncio
async def test_legacy_code_exchange_returns_a_credential(hass, entry):
    """The short pairing code still works for clients with a keyboard."""
    view = api.FamilyDashboardPairingCodeView(hass)

    response = await view.post(FakeRequest(body={"code": "a1b2c3d4"}))
    assert response.status == 200
    body = json.loads(response.text)
    assert body["device_token"]

    # The short code is rotated as soon as it has been used.
    assert entry.data["pairing_code"] != "A1B2C3D4"
    response = await view.post(FakeRequest(body={"code": "a1b2c3d4"}))
    assert response.status == 401
