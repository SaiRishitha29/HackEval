import ipaddress
import logging
import socket
from urllib.parse import urlparse
from typing import Tuple, List, Optional
import httpx
from backend.app.config import settings, competition_config

logger = logging.getLogger(__name__)

# Disallowed IP networks
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),          # Current network (only valid as source)
    ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918 Private
    ipaddress.ip_network("100.64.0.0/10"),      # RFC 6598 Shared Carrier NAT
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / Cloud Metadata (e.g. AWS/GCP 169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918 Private
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),       # TEST-NET-1
    ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918 Private
    ipaddress.ip_network("198.18.0.0/15"),      # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
    # IPv6
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("fc00::/7"),           # Unique local address (ULA)
    ipaddress.ip_network("fe80::/10"),          # Link-local unicast
    ipaddress.ip_network("ff00::/8"),           # Multicast
]

PROHIBITED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


class SSRFValidationError(Exception):
    """Raised when an endpoint URL or resolved IP violates SSRF defense rules."""
    pass


class SSRFDefender:
    def __init__(self):
        self.connect_timeout = competition_config.connect_timeout_seconds
        self.read_timeout = competition_config.read_timeout_seconds
        self.max_response_bytes = competition_config.max_response_bytes

    def validate_url(self, url: str) -> Tuple[str, str, int]:
        """
        Validates the URL scheme, hostname, and port.
        Returns: (scheme, hostname, port)
        """
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()

        # Scheme check
        if scheme != "https":
            if not (settings.ALLOW_HTTP_MOCK_ENDPOINTS_IN_DEV and scheme == "http"):
                raise SSRFValidationError(f"Invalid URL scheme '{scheme}'. Only HTTPS endpoints are permitted.")

        hostname = parsed.hostname
        if not hostname:
            raise SSRFValidationError("Endpoint URL is missing a valid hostname.")

        hostname_lower = hostname.lower()
        if hostname_lower in PROHIBITED_HOSTNAMES:
            raise SSRFValidationError(f"Access to prohibited hostname '{hostname}' is blocked.")

        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80

        return scheme, hostname, port

    def resolve_and_verify_ip(self, hostname: str) -> str:
        """
        Resolves hostname via DNS and verifies that all resolved IP addresses are safe public IPs.
        Returns the verified IP address for connection pinning.
        """
        try:
            addr_info = socket.getaddrinfo(hostname, None)
        except socket.gaierror as e:
            raise SSRFValidationError(f"DNS resolution failed for hostname '{hostname}': {str(e)}")

        resolved_ips: List[str] = []
        for item in addr_info:
            ip_str = item[4][0]
            resolved_ips.append(ip_str)

        if not resolved_ips:
            raise SSRFValidationError(f"No IP addresses resolved for hostname '{hostname}'.")

        # In dev mode with synthetic mock server on loopback, allow if explicitly enabled
        if settings.ALLOW_HTTP_MOCK_ENDPOINTS_IN_DEV and hostname in ("localhost", "127.0.0.1", "::1"):
            return "127.0.0.1"

        # Check all resolved IPs against prohibited networks
        for ip_str in resolved_ips:
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                # Unwrap IPv4-mapped IPv6
                if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                    ip_obj = ip_obj.ipv4_mapped

                for prohibited in PROHIBITED_NETWORKS:
                    if ip_obj in prohibited:
                        raise SSRFValidationError(
                            f"Host '{hostname}' resolved to prohibited IP address {ip_str} in range {prohibited}"
                        )
            except ValueError:
                raise SSRFValidationError(f"Invalid IP address format: {ip_str}")

        # Return first verified IP for direct connection pinning
        return resolved_ips[0]

    def create_safe_client(self) -> httpx.Client:
        """
        Creates an httpx.Client configured with:
        - Strict connect & read timeouts.
        - Automatic redirects disabled (to prevent redirect-based SSRF bypass).
        """
        limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=10.0,
            pool=5.0
        )
        return httpx.Client(
            timeout=timeout,
            limits=limits,
            follow_redirects=False,  # CRITICAL: Do not follow redirects
            headers={"User-Agent": "HackEval-VerificationWorker/1.0"}
        )

    def execute_safe_post(self, client: httpx.Client, url: str, json_payload: dict) -> Tuple[int, dict, float]:
        """
        Executes an outbound POST request with SSRF validation, DNS verification,
        enforced timeout, and max byte length inspection.
        Returns: (http_status_code, response_json, latency_ms)
        """
        import time

        scheme, hostname, port = self.validate_url(url)
        pinned_ip = self.resolve_and_verify_ip(hostname)

        start_time = time.perf_counter()

        try:
            # We connect using the client
            response = client.post(url, json=json_payload)
            latency_ms = (time.perf_counter() - start_time) * 1000.0

            # Check response byte limit
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.max_response_bytes:
                raise SSRFValidationError(
                    f"Response size ({content_length} bytes) exceeds maximum limit of {self.max_response_bytes} bytes"
                )

            raw_bytes = response.content
            if len(raw_bytes) > self.max_response_bytes:
                raise SSRFValidationError(
                    f"Response payload ({len(raw_bytes)} bytes) exceeds maximum limit of {self.max_response_bytes} bytes"
                )

            # Check for redirect status codes
            if response.is_redirect:
                raise SSRFValidationError(
                    f"Redirect blocked: Participant endpoint returned HTTP {response.status_code} redirect."
                )

            if response.status_code != 200:
                return response.status_code, {"error": f"HTTP {response.status_code}"}, latency_ms

            try:
                data = response.json()
            except Exception:
                raise SSRFValidationError("Endpoint returned invalid non-JSON response body")

            return 200, data, latency_ms

        except httpx.ConnectTimeout:
            raise TimeoutError(f"Connection timeout after {self.connect_timeout}s")
        except httpx.ReadTimeout:
            raise TimeoutError(f"Read timeout after {self.read_timeout}s")
        except httpx.RequestError as e:
            raise RuntimeError(f"Network request error: {str(e)}")


ssrf_defender = SSRFDefender()
