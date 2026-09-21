from starlette.requests import Request

from app.client_identity import client_identity


def make_request(peer: str, **headers: str) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    scope = {
        "type": "http",
        "client": (peer, 443),
        "headers": raw_headers,
        "method": "POST",
        "path": "/api/jobs",
        "query_string": b"",
        "scheme": "https",
        "server": ("test", 443),
    }
    return Request(scope)


def test_direct_peer_ignores_spoofed_cloudflare_headers():
    request = make_request("203.0.113.10", **{"CF-Connecting-IP": "198.51.100.20"})
    assert client_identity(request) == "203.0.113.10"


def test_trusted_cloudflare_peer_accepts_public_connecting_ip():
    request = make_request("173.245.48.10", **{"CF-Connecting-IP": "8.8.8.8"})
    assert client_identity(request) == "8.8.8.8"


def test_trusted_peer_rejects_malformed_and_private_connecting_ip():
    for value in ("not-an-ip", "10.0.0.1", "127.0.0.1", "169.254.1.1"):
        request = make_request("173.245.48.10", **{"CF-Connecting-IP": value})
        assert client_identity(request) == "173.245.48.10"
