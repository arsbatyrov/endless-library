"""Refusing cookie-authenticated requests that come from another origin (AUTH-017).

`/auth/refresh` and `/auth/logout` are authenticated by a cookie, which a browser attaches to any request to our
address, also one made by a page of another site. `SameSite=Lax` already stops the browser from sending the cookie
with a cross-site POST; this is the second line (defence in depth): the server itself refuses such a request, before
anything is rotated, revoked or cleared.

What a browser tells us:
- `Sec-Fetch-Site` (all modern browsers): `same-origin` or `none` are fine, anything else (`cross-site`, `same-site`,
  an unknown value) is refused. It is the most reliable signal, so when it is present it alone decides.
- `Origin` (older browsers, and sent on cross-origin POSTs): refused unless its host is the host the request was
  addressed to (`X-Forwarded-Host` behind the proxy, otherwise `Host`). The port is not compared, because nginx
  passes `Host` without it.
A request with neither header does not come from a browser page (curl, the test clients, a mobile app): the attack
needs a victim's browser, so such a request is let through.
"""

from urllib.parse import urlsplit

from fastapi import HTTPException, Request, status

CROSS_ORIGIN_REFUSED = "Cross-origin request refused"


def _host_of(value: str) -> str | None:
    """The lower-cased host name without a port, or None if the value is not a usable origin."""
    try:
        host = urlsplit(value if "://" in value else f"//{value}").hostname
    except ValueError:
        return None
    return host.lower() if host else None


def _addressed_host(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-host")
    value = forwarded.split(",")[0].strip() if forwarded else request.headers.get("host", "")
    return _host_of(value)


def require_same_origin(request: Request) -> None:
    """Dependency: 403 for a browser request that does not come from this site's own pages."""
    site = request.headers.get("sec-fetch-site")
    if site is not None:
        if site.strip().lower() in ("same-origin", "none"):
            return
        raise _refused()

    origin = request.headers.get("origin")
    if origin is None:
        return
    origin_host = _host_of(origin) if origin.lower() != "null" and "://" in origin else None
    if origin_host is None or origin_host != _addressed_host(request):
        raise _refused()


def _refused() -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=CROSS_ORIGIN_REFUSED)
