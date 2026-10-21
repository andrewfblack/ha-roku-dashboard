"""Test setup for the Family Dashboard integration.

The tests run without Home Assistant installed. The small surface the
integration imports is stubbed below, and a fake Home Assistant object
supplies states, services and config entries.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

PACKAGE_DIR = (
    Path(__file__).parent.parent / "custom_components" / "roku_dashboard"
)


def _install_home_assistant_stubs() -> None:
    """Register minimal stand-ins for the Home Assistant modules."""
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    homeassistant.__path__ = []
    sys.modules["homeassistant"] = homeassistant

    core = types.ModuleType("homeassistant.core")

    class HomeAssistant:  # noqa: D401 - test double
        """Stand-in for the Home Assistant core object."""

    def callback(func):
        """Return the function unchanged, like the real decorator."""
        return func

    core.HomeAssistant = HomeAssistant
    core.callback = callback
    sys.modules["homeassistant.core"] = core

    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    sys.modules["homeassistant.helpers"] = helpers

    entity_registry = types.ModuleType("homeassistant.helpers.entity_registry")

    class FakeEntityRegistry:
        """Stand-in for the entity registry."""

        def async_get(self, entity_id):
            """Return None: no entity is registered in the tests."""
            return None

    def async_get(hass):
        """Return the entity registry."""
        return FakeEntityRegistry()

    entity_registry.async_get = async_get
    sys.modules["homeassistant.helpers.entity_registry"] = entity_registry

    storage = types.ModuleType("homeassistant.helpers.storage")

    class Store:
        """In-memory stand-in for the Home Assistant storage helper."""

        def __init__(self, hass, version, key):
            self.hass = hass
            self.version = version
            self.key = key
            self._storage = hass.data.setdefault("__storage__", {})

        async def async_load(self):
            """Return the stored data."""
            return self._storage.get(self.key)

        async def async_save(self, data):
            """Store the data."""
            self._storage[self.key] = data

    storage.Store = Store
    sys.modules["homeassistant.helpers.storage"] = storage

    const = types.ModuleType("homeassistant.const")
    const.STATE_UNAVAILABLE = "unavailable"
    const.STATE_UNKNOWN = "unknown"
    const.EVENT_STATE_CHANGED = "state_changed"
    sys.modules["homeassistant.const"] = const

    components = types.ModuleType("homeassistant.components")
    components.__path__ = []
    sys.modules["homeassistant.components"] = components

    http = types.ModuleType("homeassistant.components.http")

    class HomeAssistantView:
        """Minimal stand-in for the Home Assistant view base class."""

        url = None
        name = None
        requires_auth = True

        def __init__(self, hass=None):
            self.hass = hass

        def json(self, data, status_code=200):
            """Return the data as a JSON response."""
            from aiohttp import web

            return web.json_response(data, status=status_code)

    http.HomeAssistantView = HomeAssistantView
    sys.modules["homeassistant.components.http"] = http

    util = types.ModuleType("homeassistant.util")
    util.__path__ = []
    sys.modules["homeassistant.util"] = util

    dt = types.ModuleType("homeassistant.util.dt")
    dt.now = lambda: datetime.now(timezone.utc)
    dt.parse_datetime = lambda value: datetime.fromisoformat(value)
    dt.as_local = lambda value: value
    sys.modules["homeassistant.util.dt"] = dt


def _register_package() -> types.ModuleType:
    """Register the integration as an importable package.

    The real ``__init__.py`` pulls in the whole Home Assistant server, so the
    package is registered by hand and only the modules under test are loaded.
    """
    package = types.ModuleType("roku_dashboard")
    package.__path__ = [str(PACKAGE_DIR)]
    sys.modules["roku_dashboard"] = package
    return package


_install_home_assistant_stubs()
_register_package()


class FakeState:
    """A single entity state."""

    def __init__(self, entity_id: str, state: str, attributes: dict | None = None):
        """Store the state and its attributes."""
        self.entity_id = entity_id
        self.state = state
        self.attributes = attributes or {}


class FakeStates:
    """The entity state machine."""

    def __init__(self):
        """Start with no states."""
        self._states: dict[str, FakeState] = {}

    def set(self, entity_id: str, state: str, attributes: dict | None = None) -> None:
        """Add or replace an entity state."""
        self._states[entity_id] = FakeState(entity_id, state, attributes)

    def get(self, entity_id: str) -> FakeState | None:
        """Return one entity state."""
        return self._states.get(entity_id)

    def async_all(self, domains: list[str] | None = None) -> list[FakeState]:
        """Return the states, optionally limited to some domains."""
        return [
            state
            for state in self._states.values()
            if not domains or state.entity_id.split(".", 1)[0] in domains
        ]


class FakeServices:
    """The service call registry."""

    def __init__(self, responses: dict | None = None):
        """Store the canned responses and record the calls."""
        self.responses = responses or {}
        self.calls: list[tuple] = []

    async def async_call(
        self,
        domain,
        service,
        service_data=None,
        blocking=False,
        return_response=False,
    ):
        """Return the canned response for a service call."""
        self.calls.append((domain, service, service_data))
        handler = self.responses.get((domain, service))
        if callable(handler):
            return handler(service_data)
        return handler if handler is not None else {}


class FakeConfigEntry:
    """A config entry."""

    def __init__(self, entry_id="entry1", data=None, options=None):
        """Store the entry data and options."""
        self.entry_id = entry_id
        self.data = data or {}
        self.options = options or {}

    def async_on_unload(self, func):
        """Ignore the unload callback."""
        return func


class FakeConfigEntries:
    """The config entry registry."""

    def __init__(self, entries=None):
        """Store the entries."""
        self._entries = list(entries or [])

    def async_entries(self, domain=None):
        """Return the entries."""
        return list(self._entries)

    def async_update_entry(self, entry, data=None, options=None):
        """Update the entry data or options."""
        if data is not None:
            entry.data = data
        if options is not None:
            entry.options = options


class FakeConfig:
    """The Home Assistant configuration directory."""

    def __init__(self, root="/tmp/family-dashboard-test"):
        """Store the root of the configuration directory."""
        self.root = root

    def path(self, *parts) -> str:
        """Return a path inside the configuration directory."""
        return "/".join([self.root, *parts])


class FakeBus:
    """The event bus."""

    def __init__(self):
        """Start with no listeners."""
        self.listeners: list = []

    def async_listen(self, event_type, callback):
        """Record a listener."""
        self.listeners.append((event_type, callback))
        return lambda: self.listeners.remove((event_type, callback))

    def fire(self, event_type, data=None):
        """Fire an event at every listener."""
        for listener_type, listener in list(self.listeners):
            if listener_type == event_type:
                listener(types.SimpleNamespace(data=data or {}))


class FakeUser:
    """A Home Assistant user."""

    def __init__(self, is_admin: bool = True):
        """Store whether the user is an administrator."""
        self.is_admin = is_admin
        self.id = "user1"


class FakeRequest:
    """A request with just the parts the API looks at."""

    def __init__(
        self,
        headers=None,
        remote="192.168.1.10",
        query=None,
        body=None,
        user=None,
    ):
        """Store the headers, the remote address, the query and the body."""
        self.headers = headers or {}
        self.remote = remote
        self.query = query or {}
        self.body = body if body is not None else {}
        self.secure = False
        self._user = user if user is not None else FakeUser()

    async def json(self):
        """Return the request body."""
        return self.body

    def get(self, key, default=None):
        """Return a value from the request context."""
        if key == "hass_user":
            return self._user
        return default


class FakeHass:
    """A Home Assistant object with just enough behaviour for the tests."""

    def __init__(self, entries=None):
        """Create the empty fake."""
        self.data: dict = {}
        self.states = FakeStates()
        self.services = FakeServices()
        self.config_entries = FakeConfigEntries(entries)
        self.config = FakeConfig()
        self.bus = FakeBus()


@pytest.fixture
def hass():
    """Return a Home Assistant fake with one config entry."""
    entry = FakeConfigEntry(
        data={"pairing_code": "A1B2C3D4", "device_token": "LEGACYTOKEN"},
        options={},
    )
    return FakeHass([entry])


@pytest.fixture
def entry(hass):
    """Return the single config entry."""
    return hass.config_entries.async_entries()[0]
