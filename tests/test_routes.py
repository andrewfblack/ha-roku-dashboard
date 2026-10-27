"""End to end tests over real HTTP.

The views are registered on a real aiohttp application in the same order as
the integration registers them, so a route that shadows another one shows up
here.
"""

from __future__ import annotations

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from roku_dashboard import api, panel, pairing

from conftest import FakeRequest


def _register(app, view) -> None:
    """Register a view the way Home Assistant does.

    Home Assistant wraps every handler and calls it with the path variables
    as keyword arguments, so the tests do the same.
    """
    for method in ("get", "post"):
        handler = getattr(view, method, None)
        if handler is None:
            continue

        async def wrapper(request, _handler=handler):
            return await _handler(request, **request.match_info)

        app.router.add_route(method.upper(), view.url, wrapper)


def _build_app(hass) -> web.Application:
    """Build the application with the routes in the integration's order."""
    app = web.Application()

    # Fixed routes first, the catch-all credential route last.
    _register(app, api.FamilyDashboardPairingRequestView(hass))
    _register(app, api.FamilyDashboardPairingStatusView(hass))
    _register(app, api.FamilyDashboardPairingCodeView(hass))
    _register(app, api.FamilyDashboardStreamView(hass))
    _register(app, api.FamilyDashboardDataView(hass))
    _register(app, api.FamilyDashboardActionView(hass))
    _register(app, api.FamilyDashboardBackgroundView(hass))
    _register(app, api.RokuDashboardView(hass))
    _register(app, api.RokuDashboardActionView(hass))
    _register(app, api.RokuDashboardBackgroundView(hass))
    _register(app, panel.FamilyDashboardPanelView(hass))
    _register(app, panel.FamilyDashboardPanelActionView(hass))
    _register(app, panel.FamilyDashboardPanelSettingsView(hass))
    _register(app, panel.FamilyDashboardPanelBackgroundView(hass))
    _register(app, panel.FamilyDashboardPanelPairingView(hass))
    _register(app, api.FamilyDashboardTokenDataView(hass))
    return app


@pytest.mark.asyncio
async def test_a_client_can_pair_and_read_the_dashboard(hass, entry):
    """The whole flow works over HTTP."""
    entry.options = {"weather_tab_enabled": False}
    async with TestClient(TestServer(_build_app(hass))) as client:
        response = await client.post(
            "/api/family_dashboard/pairing/request",
            json={"device_name": "Apple TV", "platform": "tvos"},
        )
        assert response.status == 200
        body = await response.json()
        code = body["device_code"]

        # The device waits while the request is pending.
        response = await client.get(
            "/api/family_dashboard/pairing/status", params={"device_code": code}
        )
        assert (await response.json())["status"] == "pending"

        # An administrator approves it.
        await pairing.async_approve(hass, code)

        response = await client.get(
            "/api/family_dashboard/pairing/status", params={"device_code": code}
        )
        body = await response.json()
        assert body["status"] == "approved"
        token = body["device_token"]

        # The device reads the dashboard with its credential.
        response = await client.get(
            "/api/family_dashboard/device", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status == 200
        payload = await response.json()
        assert payload["ok"] is True
        assert payload["schema_version"] == 3


@pytest.mark.asyncio
async def test_the_dashboard_route_is_not_shadowed(hass, entry):
    """The catch-all credential route does not swallow the fixed routes."""
    entry.options = {"weather_tab_enabled": False}
    async with TestClient(TestServer(_build_app(hass))) as client:
        device = await pairing.async_add_device(hass, "iPhone", "ios")

        response = await client.get(
            "/api/family_dashboard/device",
            headers={"Authorization": f"Bearer {device['token']}"},
        )
        assert response.status == 200
        assert (await response.json())["ok"] is True

        # The panel keeps its own route.
        response = await client.get("/api/family_dashboard/panel")
        assert response.status in (200, 401, 403)

        # The stream keeps its own route.
        response = await client.get("/api/family_dashboard/stream")
        assert response.status == 401


@pytest.mark.asyncio
async def test_a_token_in_the_path_also_works(hass, entry):
    """Clients that cannot set a header can still read the dashboard."""
    entry.options = {"weather_tab_enabled": False}
    async with TestClient(TestServer(_build_app(hass))) as client:
        device = await pairing.async_add_device(hass, "Roku", "roku")

        response = await client.get(f"/api/family_dashboard/{device['token']}")
        assert response.status == 200
        assert (await response.json())["ok"] is True


@pytest.mark.asyncio
async def test_the_legacy_route_still_works(hass, entry):
    """An already sideloaded Roku channel keeps working."""
    entry.options = {"weather_tab_enabled": False}
    async with TestClient(TestServer(_build_app(hass))) as client:
        response = await client.get("/api/roku_dashboard/A1B2C3D4")
        assert response.status == 200
        payload = await response.json()
        assert payload["ok"] is True
        assert payload["device_token"]

        # The short code is rotated, so it cannot be used twice.
        response = await client.get("/api/roku_dashboard/A1B2C3D4")
        assert response.status == 401


@pytest.mark.asyncio
async def test_the_stream_sends_the_dashboard_first(hass, entry):
    """A client opens the stream and receives the dashboard right away."""
    entry.options = {"weather_tab_enabled": False}
    async with TestClient(TestServer(_build_app(hass))) as client:
        device = await pairing.async_add_device(hass, "Apple TV", "tvos")

        response = await client.get(
            "/api/family_dashboard/stream",
            headers={"Authorization": f"Bearer {device['token']}"},
        )
        assert response.status == 200

        chunk = await response.content.readuntil(b"\n\n")
        text = chunk.decode()
        assert "event: dashboard" in text
        data_line = [
            line for line in text.splitlines() if line.startswith("data: ")
        ][0]
        payload = json.loads(data_line[len("data: ") :])
        assert payload["ok"] is True

        response.close()


@pytest.mark.asyncio
async def test_the_stream_pushes_a_state_change(hass, entry):
    """A change to a displayed entity reaches a connected client."""
    entry.options = {"weather_tab_enabled": False, "light_entities": ["light.kitchen"]}
    hass.states.set("light.kitchen", "on", {"friendly_name": "Kitchen"})

    async with TestClient(TestServer(_build_app(hass))) as client:
        device = await pairing.async_add_device(hass, "Apple TV", "tvos")

        response = await client.get(
            "/api/family_dashboard/stream",
            headers={"Authorization": f"Bearer {device['token']}"},
        )
        assert response.status == 200
        await response.content.readuntil(b"\n\n")

        await api.setup_state_stream(hass, entry)
        hass.bus.fire(
            "state_changed",
            {
                "entity_id": "light.kitchen",
                "new_state": type(
                    "State", (), {"state": "off", "attributes": {}}
                )(),
            },
        )

        chunk = await response.content.readuntil(b"\n\n")
        text = chunk.decode()
        assert "event: state" in text
        assert "light.kitchen" in text

        response.close()


@pytest.mark.asyncio
async def test_the_pairing_status_is_not_polled_from_outside_the_lan(hass, entry):
    """The status poll hands out a credential, so it follows the LAN policy."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    code = record["device_code"]
    await pairing.async_approve(hass, code)

    view = api.FamilyDashboardPairingStatusView(hass)

    # A client on the LAN may collect the credential.
    request = FakeRequest(remote="192.168.1.10", query={"device_code": code})
    response = await view.get(request)
    assert response.status == 200
    assert json.loads(response.text)["device_token"]

    # A client from the public internet may not.
    request = FakeRequest(remote="8.8.8.8", query={"device_code": code})
    response = await view.get(request)
    assert response.status == 403
    assert json.loads(response.text)["error"] == "network_access_denied"
