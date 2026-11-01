"""Tests for the pairing controls in the Home Assistant panel."""

from __future__ import annotations

import json

import pytest

from conftest import FakeRequest, FakeUser
from roku_dashboard import panel, pairing


@pytest.mark.asyncio
async def test_an_admin_sees_the_pending_requests(hass):
    """The panel lists what is waiting for approval."""
    await pairing.async_create_request(hass, "Apple TV", "tvos")
    view = panel.FamilyDashboardPanelPairingView(hass)

    response = await view.get(FakeRequest())
    assert response.status == 200
    body = json.loads(response.text)
    assert len(body["pending"]) == 1
    assert body["pending"][0]["name"] == "Apple TV"
    assert "token" not in body["pending"][0]


@pytest.mark.asyncio
async def test_a_normal_user_cannot_approve(hass):
    """Only an administrator may approve a device."""
    view = panel.FamilyDashboardPanelPairingView(hass)
    request = FakeRequest(user=FakeUser(is_admin=False), body={})

    response = await view.get(request)
    assert response.status == 403

    response = await view.post(request)
    assert response.status == 403


@pytest.mark.asyncio
async def test_approving_from_the_panel_mints_a_credential(hass):
    """Approving a request gives the waiting device its credential."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    view = panel.FamilyDashboardPanelPairingView(hass)
    request = FakeRequest(
        body={"action": "approve", "device_code": record["device_code"]}
    )

    response = await view.post(request)
    assert response.status == 200

    devices = pairing.list_devices(hass)
    assert len(devices) == 1
    assert devices[0]["platform"] == "tvos"


@pytest.mark.asyncio
async def test_denying_from_the_panel(hass):
    """Denying a request leaves no credential behind."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    view = panel.FamilyDashboardPanelPairingView(hass)
    request = FakeRequest(body={"action": "deny", "device_code": record["device_code"]})

    response = await view.post(request)
    assert response.status == 200
    assert not pairing.list_devices(hass)


@pytest.mark.asyncio
async def test_revoking_a_device(hass):
    """A revoked device can no longer read the dashboard."""
    device = await pairing.async_add_device(hass, "iPhone", "ios")
    view = panel.FamilyDashboardPanelPairingView(hass)
    request = FakeRequest(body={"action": "revoke", "device_id": device["device_id"]})

    response = await view.post(request)
    assert response.status == 200
    assert pairing.find_by_token(hass, device["token"]) is None

    response = await view.post(request)
    assert response.status == 404


@pytest.mark.asyncio
async def test_revoking_the_legacy_token_sticks(hass, entry):
    """Revoking the shared token is not undone by the next reload."""
    view = panel.FamilyDashboardPanelPairingView(hass)

    response = await view.post(FakeRequest(body={"action": "revoke_legacy"}))
    assert response.status == 200
    assert entry.data["device_token"] == ""
    assert entry.data["legacy_token_revoked"] is True


@pytest.mark.asyncio
async def test_an_unknown_action_is_refused(hass):
    """The panel only accepts the actions it knows."""
    view = panel.FamilyDashboardPanelPairingView(hass)

    response = await view.post(FakeRequest(body={"action": "explode"}))
    assert response.status == 400
