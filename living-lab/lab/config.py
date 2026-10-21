import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

INDICATORS = {"cycle_minutes": "min", "delivery_pct": "%"}


def load(path):
    cfg = json.loads(Path(path).read_text())
    if cfg["mode"] not in ("offline", "controlled", "live"):
        raise ValueError("invalid_mode")
    if not 10 <= cfg["interval_seconds"] <= 3600:
        raise ValueError("invalid_interval")
    companies = cfg["companies"]
    if len(companies) != 2 or len({c["id"] for c in companies}) != 2:
        raise ValueError("exactly_two_distinct_companies_required")
    if len({c["source"] for c in companies}) != 2:
        raise ValueError("independent_sources_required")
    if len({c["credential_file"] for c in companies}) != 2:
        raise ValueError("independent_credential_files_required")
    for c in companies:
        if (
            type(c["send_enabled"]) is not bool
            or type(c["seed"]) is not int
            or type(c["clients"]) is not int
        ):
            raise ValueError("typed_company_configuration_required")
        if not re.fullmatch("[a-z][a-z0-9-]{1,30}", c["id"]):
            raise ValueError("invalid_company_id")
        if not 12 <= c["clients"] <= 200:
            raise ValueError("invalid_client_count")
        UUID(c["profile_id"])
        if (
            not c["source"]
            or c["source"].strip() != c["source"]
            or len(c["source"]) > 100
        ):
            raise ValueError("invalid_source")
        endpoint = urlsplit(c["endpoint"])
        if (
            endpoint.username
            or endpoint.password
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("unsafe_endpoint")
        if endpoint.path != "/functions/v1/ingest-v1/observations":
            raise ValueError("invalid_c01_path")
        if cfg["mode"] == "controlled":
            if endpoint.scheme != "http" or endpoint.hostname != "127.0.0.1":
                raise ValueError("controlled_receiver_must_be_literal_loopback")
        elif endpoint.scheme != "https" or not endpoint.hostname:
            raise ValueError("https_required")
        if cfg["mode"] == "live" and endpoint.hostname.endswith(".invalid"):
            raise ValueError("configure_real_endpoint_manually")
    return cfg
