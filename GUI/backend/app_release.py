import json
import os
import re
from datetime import datetime, timezone
from urllib import error, request

from backend.config import DATA_DIR

DEFAULT_APP_RELEASE_PATH = os.path.join(DATA_DIR, "app_release.json")
DEFAULT_RELEASE_INFO = {
    "version": "0.1.0",
    "release_channel": "stable",
    "released_at": "",
    "notes_url": "",
    "download_url": "",
    "update_manifest_url": "",
}

_SEMVER_PATTERN = re.compile(
    r"^v?"
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)


def _utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_prerelease_identifiers(raw):
    if not raw:
        return ()

    parsed = []
    for item in raw.split("."):
        if not item:
            return None
        if item.isdigit():
            if len(item) > 1 and item.startswith("0"):
                return None
            parsed.append(("num", int(item)))
        else:
            if not re.match(r"^[0-9A-Za-z-]+$", item):
                return None
            parsed.append(("str", item))
    return tuple(parsed)


def parse_semver(value):
    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    match = _SEMVER_PATTERN.fullmatch(text)
    if not match:
        return None

    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3))
    prerelease_text = match.group(4) or ""
    prerelease_identifiers = _parse_prerelease_identifiers(prerelease_text)
    if prerelease_identifiers is None:
        return None

    canonical = f"{major}.{minor}.{patch}"
    if prerelease_text:
        canonical += f"-{prerelease_text}"

    return major, minor, patch, prerelease_identifiers, canonical


def normalize_semver(value, default=None):
    parsed = parse_semver(value)
    if parsed is None:
        return default
    return parsed[4]


def is_valid_semver(value):
    return parse_semver(value) is not None


def compare_semver(version_a, version_b):
    parsed_a = parse_semver(version_a)
    parsed_b = parse_semver(version_b)
    if parsed_a is None or parsed_b is None:
        return None

    core_a = parsed_a[:3]
    core_b = parsed_b[:3]
    if core_a < core_b:
        return -1
    if core_a > core_b:
        return 1

    prerelease_a = parsed_a[3]
    prerelease_b = parsed_b[3]
    if prerelease_a == prerelease_b:
        return 0
    if not prerelease_a:
        return 1
    if not prerelease_b:
        return -1

    for item_a, item_b in zip(prerelease_a, prerelease_b):
        type_a, value_a = item_a
        type_b, value_b = item_b
        if type_a == type_b:
            if value_a < value_b:
                return -1
            if value_a > value_b:
                return 1
        else:
            if type_a == "num":
                return -1
            return 1

    if len(prerelease_a) < len(prerelease_b):
        return -1
    if len(prerelease_a) > len(prerelease_b):
        return 1
    return 0


def _sanitize_release_info(raw):
    release = dict(DEFAULT_RELEASE_INFO)
    if isinstance(raw, dict):
        release.update(raw)

    env_version = normalize_semver(os.getenv("APP_VERSION"), None)
    if env_version:
        release["version"] = env_version
    else:
        release["version"] = normalize_semver(
            release.get("version"), DEFAULT_RELEASE_INFO["version"]
        )

    channel = os.getenv("APP_RELEASE_CHANNEL", release.get("release_channel", "stable"))
    release["release_channel"] = str(channel).strip().lower() or "stable"

    released_at = str(release.get("released_at", "")).strip()
    release["released_at"] = released_at

    notes_url = str(release.get("notes_url", "")).strip()
    download_url = str(release.get("download_url", "")).strip()
    release["notes_url"] = notes_url
    release["download_url"] = download_url

    manifest_url = os.getenv(
        "UPDATE_MANIFEST_URL", str(release.get("update_manifest_url", "")).strip()
    )
    release["update_manifest_url"] = manifest_url

    return release


def get_release_file_path():
    configured = os.getenv("APP_RELEASE_PATH", "").strip()
    if configured:
        return configured
    return DEFAULT_APP_RELEASE_PATH


def load_local_release_info():
    release_path = get_release_file_path()
    raw = {}
    try:
        with open(release_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except Exception:
        raw = {}

    release = _sanitize_release_info(raw)
    release["release_file_path"] = release_path
    return release


def save_local_release_info(payload, release_path=None):
    target_path = release_path or get_release_file_path()
    parent = os.path.dirname(target_path) or "."
    os.makedirs(parent, exist_ok=True)

    sanitized = _sanitize_release_info(payload)
    with open(target_path, "w", encoding="utf-8") as handle:
        json.dump(sanitized, handle, indent=2)
    return sanitized


def _extract_manifest_release(raw_payload, release_channel):
    if not isinstance(raw_payload, dict):
        return None

    payload = raw_payload
    channels = raw_payload.get("channels")
    if isinstance(channels, dict):
        selected = channels.get(release_channel) or channels.get("stable")
        if not isinstance(selected, dict):
            return None
        payload = selected

    version = payload.get("version")
    if version is None:
        version = payload.get("latest_version")
    normalized = normalize_semver(version, None)
    if normalized is None:
        return None

    return {
        "version": normalized,
        "released_at": str(payload.get("released_at", "")).strip(),
        "download_url": str(payload.get("download_url", "")).strip(),
        "notes_url": str(payload.get("notes_url", "")).strip(),
    }


def fetch_remote_release_info(manifest_url, release_channel="stable", timeout_sec=4):
    if not manifest_url:
        return None, "Update manifest URL is not configured."

    try:
        timeout = max(1, int(timeout_sec))
    except (TypeError, ValueError):
        timeout = 4

    req = request.Request(
        manifest_url,
        headers={"User-Agent": "filament-logs-update-checker/1.0"},
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw_body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        return None, f"Update server returned HTTP {exc.code}."
    except error.URLError as exc:
        reason = exc.reason if getattr(exc, "reason", None) else "network error"
        return None, f"Failed to reach update server: {reason}."
    except TimeoutError:
        return None, "Update check timed out."
    except Exception:
        return None, "Failed to fetch update manifest."

    try:
        payload = json.loads(raw_body)
    except Exception:
        return None, "Update manifest returned invalid JSON."

    release = _extract_manifest_release(payload, release_channel=release_channel)
    if release is None:
        return None, "Update manifest did not include a valid version."

    return release, ""


def check_for_updates(timeout_sec=4):
    local = load_local_release_info()
    current_version = local["version"]
    release_channel = local.get("release_channel", "stable")
    manifest_url = local.get("update_manifest_url", "")

    status = {
        "checked_at": _utc_now_iso(),
        "current_version": current_version,
        "release_channel": release_channel,
        "update_manifest_url": manifest_url,
        "latest_version": current_version,
        "released_at": local.get("released_at", ""),
        "download_url": local.get("download_url", ""),
        "notes_url": local.get("notes_url", ""),
        "update_available": False,
        "error": "",
    }

    remote, err = fetch_remote_release_info(
        manifest_url=manifest_url,
        release_channel=release_channel,
        timeout_sec=timeout_sec,
    )
    if err:
        status["error"] = err
        return status

    status["latest_version"] = remote["version"]
    status["released_at"] = remote.get("released_at", status["released_at"])
    status["download_url"] = remote.get("download_url", status["download_url"])
    status["notes_url"] = remote.get("notes_url", status["notes_url"])

    comparison = compare_semver(current_version, remote["version"])
    if comparison is None:
        status["error"] = "Cannot compare local version with remote manifest version."
        return status

    status["update_available"] = comparison < 0
    return status
