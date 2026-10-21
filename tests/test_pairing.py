"""Tests for the device credentials and the device-initiated pairing flow."""

from __future__ import annotations

import time

import pytest

from roku_dashboard import pairing


@pytest.mark.asyncio
async def test_pairing_code_is_readable_aloud(hass):
    """The code avoids the characters people mix up."""
    record = await pairing.async_create_request(hass, "Living Room TV", "tvos")
    code = record["device_code"]
    assert len(code) == 8
    assert all(character in pairing.CODE_ALPHABET for character in code)
    assert "0" not in code and "O" not in code
    assert "1" not in code and "I" not in code


@pytest.mark.asyncio
async def test_request_is_pending_until_approved(hass):
    """A request waits for an administrator."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    assert pairing.get_request(hass, record["device_code"])["status"] == "pending"
    assert pairing.list_requests(hass)


@pytest.mark.asyncio
async def test_approval_hands_out_a_token_once(hass):
    """The waiting client receives its credential exactly once."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    code = record["device_code"]

    approved = await pairing.async_approve(hass, code)
    assert approved["status"] == "approved"

    token = await pairing.async_claim_token(hass, code)
    assert token
    assert pairing.find_by_token(hass, token)["name"] == "Apple TV"

    # A second claim must not hand the token out again.
    assert await pairing.async_claim_token(hass, code) == ""


@pytest.mark.asyncio
async def test_denial_gives_no_token(hass):
    """A denied request never produces a credential."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    code = record["device_code"]
    assert await pairing.async_deny(hass, code)
    assert pairing.get_request(hass, code)["status"] == "denied"
    assert await pairing.async_claim_token(hass, code) == ""


@pytest.mark.asyncio
async def test_expired_requests_are_dropped(hass):
    """Requests disappear once they expire."""
    record = await pairing.async_create_request(hass, "Apple TV", "tvos")
    code = record["device_code"]
    pairing._data(hass)["requests"][code]["expires"] = time.time() - 1
    assert pairing.get_request(hass, code) is None


@pytest.mark.asyncio
async def test_unknown_tokens_do_not_resolve(hass):
    """A made up token matches no device."""
    assert pairing.find_by_token(hass, "NOTATOKEN") is None
    assert pairing.find_by_token(hass, "") is None


@pytest.mark.asyncio
async def test_revoking_removes_the_credential(hass):
    """A revoked device can no longer be resolved."""
    device = await pairing.async_add_device(hass, "iPhone", "ios")
    assert pairing.find_by_token(hass, device["token"])
    assert await pairing.async_revoke(hass, device["device_id"])
    assert pairing.find_by_token(hass, device["token"]) is None
    assert not await pairing.async_revoke(hass, device["device_id"])


@pytest.mark.asyncio
async def test_each_device_gets_its_own_token(hass):
    """Two devices never share a credential."""
    first = await pairing.async_add_device(hass, "iPhone", "ios")
    second = await pairing.async_add_device(hass, "Apple TV", "tvos")
    assert first["token"] != second["token"]
    assert len(pairing.list_devices(hass)) == 2


@pytest.mark.asyncio
async def test_last_seen_is_throttled(hass):
    """Recording a contact does not write on every request."""
    device = await pairing.async_add_device(hass, "iPhone", "ios")
    first = device["last_seen"]
    await pairing.async_touch(hass, device)
    assert device["last_seen"] == first


@pytest.mark.asyncio
async def test_public_records_hide_the_token(hass):
    """The panel never receives a credential."""
    device = await pairing.async_add_device(hass, "iPhone", "ios")
    public = pairing.public_record(device)
    assert "token" not in public
    assert public["device_id"] == device["device_id"]
