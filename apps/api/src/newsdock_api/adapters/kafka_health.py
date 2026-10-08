"""Cheap Kafka reachability probe for /api/health (no client library needed)."""

import socket


def kafka_reachable(bootstrap_servers: str, timeout_seconds: float) -> bool:
    host, _, port = bootstrap_servers.partition(",")[0].partition(":")
    try:
        with socket.create_connection((host, int(port or 9092)), timeout_seconds):
            return True
    except OSError:
        return False
