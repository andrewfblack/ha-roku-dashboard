"""Serve the Home Assistant Family Dashboard PWA."""
from __future__ import annotations

from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

_ROOT = Path(__file__).parent / "www"
_FILES = {
    "app.css": "text/css",
    "app.js": "text/javascript",
    "dashboard.js": "text/javascript",
    "panel.css": "text/css",
    "panel.js": "text/javascript",
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
        if (
            content_type is None
            and (asset.startswith("weather/") or asset.startswith("climate/"))
            and asset.endswith(".png")
            and Path(asset).name == asset.split("/")[-1]
        ):
            content_type = "image/png"
        if content_type is None:
            raise web.HTTPNotFound()
        # Scripts and styles are revalidated so a dashboard update is picked up
        # straight away instead of after the browser cache expires.
        cache = (
            "no-cache"
            if content_type in ("text/css", "text/javascript")
            else "public, max-age=3600"
        )
        return web.FileResponse(
            _ROOT / asset,
            headers={"Cache-Control": cache, "Content-Type": content_type},
        )
