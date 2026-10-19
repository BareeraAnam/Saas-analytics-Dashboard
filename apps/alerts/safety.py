import ipaddress
import socket
from urllib.parse import urlparse

# Hosts that must never be fetched, even if DNS is skipped.
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.google.com",
}


def is_safe_webhook_url(url: str) -> bool:
    """True only for public http(s) URLs.

    Alert webhooks are fetched by the worker. A private or link-local address
    would let a tenant reach the cloud metadata service or other internal hosts.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    if parsed.username or parsed.password:
        return False
    host = parsed.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        return False
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or 80)
        except socket.gaierror:
            return False
        addresses = set()
        for info in infos:
            try:
                addresses.add(ipaddress.ip_address(info[4][0]))
            except ValueError:
                return False
    if not addresses:
        return False
    for ip in addresses:
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True
