"""Read local interface addresses without contacting an external server."""

from dataclasses import dataclass
from ipaddress import IPv4Address
import json
import subprocess


WLAN_INTERFACE = "wlan0"


def select_ipv4(interfaces: list[dict], interface: str) -> str | None:
    for item in interfaces:
        if item.get("ifname") != interface or item.get("operstate") != "UP":
            continue
        # Prefer the primary address if an interface temporarily has several.
        addresses = sorted(item.get("addr_info", []), key=lambda entry: entry.get("secondary", False))
        for entry in addresses:
            if entry.get("family") != "inet" or entry.get("scope") != "global":
                continue
            flags = set(entry.get("flags", []))
            if flags.intersection({"tentative", "dadfailed", "deprecated"}):
                continue
            if any(entry.get(flag, False) for flag in ("tentative", "dadfailed", "deprecated")):
                continue
            if entry.get("valid_life_time") == 0 or entry.get("preferred_life_time") == 0:
                continue
            try:
                address = IPv4Address(entry["local"])
            except (KeyError, ValueError):
                continue
            if not (address.is_loopback or address.is_link_local or address.is_unspecified
                    or address.is_multicast or address.is_reserved):
                return str(address)
    return None


def read_ipv4(interface: str = WLAN_INTERFACE) -> str | None:
    result = subprocess.run(
        ["ip", "-j", "-4", "address", "show"],
        check=True, capture_output=True, text=True, timeout=5,
    )
    return select_ipv4(json.loads(result.stdout), interface)


@dataclass
class StableAddress:
    stable_seconds: float
    address: str | None = None
    since: float = 0.0

    def observe(self, address: str | None, now: float) -> str | None:
        if address != self.address:
            self.address, self.since = address, now
        if address is not None and now - self.since >= self.stable_seconds:
            return address
        return None
