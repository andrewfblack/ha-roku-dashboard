"""Serve the Home Assistant Family Dashboard PWA."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

_ROOT = Path(__file__).parent / "www"
_FILES = {
    "app.css": "text/css",
    "app.js": "text/javascript",
    "manifest.webmanifest": "application/manifest+json",
    "sw.js": "text/javascript",
    "icons/icon-192.png": "image/png",
    "icons/icon-512.png": "image/png",
}


class FamilyDashboardWebView(HomeAssistantView):
    """Serve the PWA entry page."""

    url = "/family-dashboard"
    name = "family_dashboard:web"
    requires_auth = False

    async def get(self, request):
        return web.FileResponse(
            _ROOT / "index.html",
            headers={"Cache-Control": "no-cache", "Content-Type": "text/html"},
        )


class FamilyDashboardAssetView(HomeAssistantView):
    """Serve allowlisted PWA assets."""

    url = "/family-dashboard/{asset:.*}"
    name = "family_dashboard:assets"
    requires_auth = False

    async def get(self, request, asset: str):
        if asset in ("", "/"):
            asset = "index.html"
        if asset == "index.html":
            return web.FileResponse(
                _ROOT / asset,
                headers={"Cache-Control": "no-cache", "Content-Type": "text/html"},
            )
        content_type = _FILES.get(asset)
        if content_type is None:
            raise web.HTTPNotFound()
        return web.FileResponse(
            _ROOT / asset,
            headers={"Cache-Control": "public, max-age=3600", "Content-Type": content_type},
        )
