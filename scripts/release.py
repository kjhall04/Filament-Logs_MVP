import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUI_DIR = os.path.join(ROOT_DIR, "GUI")
if GUI_DIR not in sys.path:
    sys.path.insert(0, GUI_DIR)

from backend import app_release  # noqa: E402


def utc_now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path, payload):
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def bump_semver(version, level):
    parsed = app_release.parse_semver(version)
    if parsed is None:
        raise ValueError(f"Cannot bump invalid semantic version: {version}")

    major, minor, patch = parsed[0], parsed[1], parsed[2]
    if level == "major":
        major += 1
        minor = 0
        patch = 0
    elif level == "minor":
        minor += 1
        patch = 0
    elif level == "patch":
        patch += 1
    else:
        raise ValueError(f"Unsupported bump level: {level}")
    return f"{major}.{minor}.{patch}"


def build_manifest_payload(manifest, channel, release_info):
    payload = manifest if isinstance(manifest, dict) else {}
    channels = payload.get("channels")
    if not isinstance(channels, dict):
        channels = {}
        payload["channels"] = channels

    channels[channel] = {
        "version": release_info["version"],
        "released_at": release_info.get("released_at", ""),
        "download_url": release_info.get("download_url", ""),
        "notes_url": release_info.get("notes_url", ""),
    }
    return payload


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Bump/set Filament Logs app version, update local release metadata, "
            "and optionally write a remote update manifest."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--set", dest="set_version", help="Set an exact semantic version (for example: 1.2.3).")
    mode.add_argument(
        "--bump",
        choices=("major", "minor", "patch"),
        help="Increment semantic version level from current app_release.json.",
    )

    parser.add_argument(
        "--channel",
        help="Release channel to write (default: current channel from app_release.json).",
    )
    parser.add_argument(
        "--released-at",
        help="Release timestamp (ISO-8601). Defaults to current UTC time when version changes.",
    )
    parser.add_argument(
        "--download-url",
        help="Public download URL for this release.",
    )
    parser.add_argument(
        "--notes-url",
        help="Release notes URL for this release.",
    )
    parser.add_argument(
        "--manifest-url",
        help="URL your app should query for updates (saved in app_release.json).",
    )
    parser.add_argument(
        "--release-file",
        default=app_release.get_release_file_path(),
        help="Path to app_release.json (default: GUI/data/app_release.json).",
    )
    parser.add_argument(
        "--manifest-output",
        help=(
            "Optional local JSON file to update with the latest channel manifest "
            "(can be uploaded to your static host/CDN)."
        ),
    )
    parser.add_argument(
        "--print-manifest",
        action="store_true",
        help="Print final manifest payload to stdout.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    current = app_release.load_local_release_info()
    base_version = current.get("version", app_release.DEFAULT_RELEASE_INFO["version"])

    if args.set_version:
        target_version = app_release.normalize_semver(args.set_version, None)
        if target_version is None:
            raise ValueError(f"Invalid semantic version: {args.set_version}")
    else:
        target_version = bump_semver(base_version, args.bump)

    release_channel = (
        str(args.channel).strip().lower()
        if args.channel is not None
        else str(current.get("release_channel", "stable")).strip().lower()
    )
    release_channel = release_channel or "stable"

    release_info = dict(current)
    release_info["version"] = target_version
    release_info["release_channel"] = release_channel
    release_info["released_at"] = (
        str(args.released_at).strip() if args.released_at is not None else utc_now_iso()
    )

    if args.download_url is not None:
        release_info["download_url"] = str(args.download_url).strip()
    if args.notes_url is not None:
        release_info["notes_url"] = str(args.notes_url).strip()
    if args.manifest_url is not None:
        release_info["update_manifest_url"] = str(args.manifest_url).strip()

    saved = app_release.save_local_release_info(release_info, release_path=args.release_file)

    manifest_payload = None
    if args.manifest_output:
        existing_manifest = read_json(args.manifest_output)
        manifest_payload = build_manifest_payload(existing_manifest, release_channel, saved)
        write_json(args.manifest_output, manifest_payload)

    print(f"Updated release file: {os.path.abspath(args.release_file)}")
    print(f"Version: {saved['version']}")
    print(f"Channel: {saved['release_channel']}")
    print(f"Released at: {saved.get('released_at', '')}")
    if saved.get("download_url"):
        print(f"Download URL: {saved['download_url']}")
    if saved.get("notes_url"):
        print(f"Notes URL: {saved['notes_url']}")
    if saved.get("update_manifest_url"):
        print(f"Update manifest URL: {saved['update_manifest_url']}")
    if args.manifest_output:
        print(f"Updated manifest file: {os.path.abspath(args.manifest_output)}")

    if args.print_manifest:
        if manifest_payload is None:
            manifest_payload = build_manifest_payload({}, release_channel, saved)
        print(json.dumps(manifest_payload, indent=2))


if __name__ == "__main__":
    main()
