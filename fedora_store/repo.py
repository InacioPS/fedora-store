"""Real Fedora package-source integration through dnf5 and the Copr API.

All ``dnf`` queries run ``dnf -C`` (cache-only) so the interface never blocks
on the network; results come as plain dicts with the JSON keys dnf5 emits
(keys are locale-dependent, so we treat the top-level dict as a single unnamed
list).

COPR discovery uses the public Copr APIv3 (no authentication required):
projects are searched via ``/project/search`` and their packages/maintainer
data via ``/package/list`` and ``/project/``.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SEARCH_LINE = re.compile(r"^([\w.+-]+)\.([\w.]+)\t(.*)$")

COPR_API = "https://copr.fedorainfracloud.org/api_3"
COPR_AGENT = "fedora-store/1.0 (+https://github.com/fedastore)"
FLATHUB_API = "https://flathub.org/api/v2"
FLATHUB_REPO_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
GITHUB_RELEASES_URL = "https://api.github.com/repos/InacioPS/fedora-store/releases/latest"
TERRA_REPO_FILE = Path("/etc/yum.repos.d/terra.repo")
_APPSTREAM_CACHE_TTL = 300
_appstream_cache: dict[str, tuple[float, list[str]]] = {}


def available_on_system() -> bool:
    return Path("/etc/fedora-release").exists() and shutil.which("dnf") is not None


def terra_configured() -> bool:
    """Whether Terra's repository definition already exists on this system."""
    return TERRA_REPO_FILE.exists()


def _run(args: list[str], timeout: int = 180) -> list:
    process = subprocess_(["dnf", "-C", *args], timeout)
    return _list_from(process.stdout)


def subprocess_(args: list[str], timeout: int = 180):
    import subprocess

    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def _list_from(stdout: str) -> list:
    data = json.loads(stdout)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def installed() -> list[dict]:
    return _run(["list", "--installed", "--json"])


def upgrades() -> list[dict]:
    return _run(["list", "--upgrades", "--json"])


def refresh_upgrades() -> list[dict]:
    """Refresh DNF metadata and return currently available package upgrades."""
    process = subprocess_(["dnf", "--refresh", "list", "--upgrades", "--json"], timeout=300)
    rows = _list_from(process.stdout)
    if process.returncode not in (0, 100) and not rows:
        message = (process.stderr or process.stdout or "").strip()
        raise RuntimeError(message or f"dnf returned {process.returncode}")
    return rows


def available_all() -> list[dict]:
    return _run(["list", "--available", "--json"], timeout=300)


def repos() -> list[dict]:
    return _run(["repolist", "--json"])

def _local_rpm_icon(archive: Path) -> str:
    files = subprocess_(["rpm", "-qlp", str(archive)], timeout=30)
    candidates = [line.strip() for line in files.stdout.splitlines()
                  if re.search(r"/(?:icons/hicolor/.+/apps|pixmaps)/.+\.(?:png|svg)$", line, re.I)]
    if not candidates:
        return ""
    member = candidates[0]
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "fedora-store" / "rpm-icons"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{hashlib.sha256((str(archive) + member).encode()).hexdigest()}{Path(member).suffix}"
    if not target.exists():
        source = subprocess.Popen(["rpm2cpio", str(archive)], stdout=subprocess.PIPE)
        extracted = subprocess.run(["cpio", "--quiet", "-i", "--to-stdout", f".{member}"],
                                   stdin=source.stdout, capture_output=True, timeout=30)
        source.wait(timeout=30)
        if extracted.returncode or not extracted.stdout:
            return ""
        target.write_bytes(extracted.stdout)
    return str(target)


def local_rpm_metadata(path: str | Path) -> dict[str, str]:
    """Read non-installing metadata and an embedded icon from one RPM archive."""
    archive = Path(path).expanduser().resolve()
    if archive.suffix.casefold() != ".rpm" or not archive.is_file():
        raise ValueError("Selecione um arquivo .rpm existente.")
    fields = "%{NAME}\n%{VERSION}-%{RELEASE}\n%{ARCH}\n%{SIZE}\n%{SUMMARY}\n"
    result = subprocess_(["rpm", "-qp", "--qf", fields, str(archive)], timeout=30)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "RPM inválido.").strip())
    name, version, arch, size, summary = (result.stdout.splitlines() + [""] * 5)[:5]
    return {"path": str(archive), "name": name, "version": version, "arch": arch, "size": size,
            "summary": summary, "icon": _local_rpm_icon(archive)}


def search(term: str, handle: dict | None = None) -> list[dict]:
    import subprocess

    process = subprocess.Popen(["dnf", "-C", "search", term], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if handle is not None:
        handle["process"] = process
    try:
        lines = process.stdout.readlines()
    except Exception:
        lines = []
    if process.poll() is None:
        process.kill()
    results: list[dict] = []
    seen: set[str] = set()
    for line in lines:
        match = SEARCH_LINE.match(line.strip())
        if not match:
            continue
        name, _arch, summary = match.groups()
        if name in seen:
            continue
        seen.add(name)
        results.append({"name": name, "summary": summary.strip()})
    return results


# ---------- Copr APIv3 (public, no authentication) ----------


def _copr_get(path: str, params: dict, timeout: int = 30):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{COPR_API}{path}?{query}",
        headers={"Accept": "application/json", "User-Agent": COPR_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _flathub_get(path: str, params: dict | None = None, timeout: int = 15):
    query = urllib.parse.urlencode(params or {})
    suffix = f"?{query}" if query else ""
    request = urllib.request.Request(
        f"{FLATHUB_API}{path}{suffix}",
        headers={"Accept": "application/json", "User-Agent": COPR_AGENT},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _flathub_metadata(app_ids: list[str], limit: int, locale: str) -> list[dict]:
    """Fetch display metadata for a bounded set of Flathub application IDs."""
    def fetch(app_id: str) -> dict | None:
        if not isinstance(app_id, str):
            return None
        try:
            metadata = _flathub_get(f"/appstream/{urllib.parse.quote(app_id, safe='.')}", {"locale": locale})
        except Exception:
            return None
        if not isinstance(metadata, dict) or metadata.get("is_eol"):
            return None
        release = next(iter(metadata.get("releases") or []), {})
        return {
            "flatpak_id": app_id,
            "name": str(metadata.get("name") or app_id),
            "summary": str(metadata.get("summary") or ""),
            "description": str(metadata.get("description") or ""),
            "version": str(release.get("version") or ""),
            "icon": str(metadata.get("icon") or "application-x-executable-symbolic"),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        return [row for row in executor.map(fetch, app_ids[:limit]) if row is not None]


def _flathub_appstream_ids(sort: str) -> list[str]:
    now = time.monotonic()
    cached = _appstream_cache.get(sort)
    if cached and now - cached[0] < _APPSTREAM_CACHE_TTL:
        return cached[1]
    data = _flathub_get("/appstream", {"filter": "apps", "sort": sort})
    app_ids = [item for item in data if isinstance(item, str)] if isinstance(data, list) else []
    _appstream_cache[sort] = (now, app_ids)
    return app_ids


def flathub_catalog(limit: int = 48, locale: str = "pt-BR") -> list[dict]:
    """Return a bounded, recently updated set of Flathub application metadata."""
    return _flathub_metadata(_flathub_appstream_ids("last-updated-at"), limit, locale)


def flathub_search(query: str, limit: int = 48, locale: str = "pt-BR") -> list[dict]:
    """Find Flathub apps by their canonical IDs, then fetch their display metadata."""
    app_ids = _flathub_appstream_ids("alphabetical")
    needle = query.casefold().strip()
    matches = [app_id for app_id in app_ids if isinstance(app_id, str) and needle in app_id.casefold()]
    return _flathub_metadata(matches, limit, locale)


def download_icon(url: str, timeout: int = 15) -> bytes:
    """Download one remote AppStream icon for display on the GTK main thread."""
    request = urllib.request.Request(url, headers={"User-Agent": COPR_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def flatpak_installed() -> dict[str, dict]:
    """Return installed Flatpak applications keyed by application ID."""
    try:
        process = subprocess_(["flatpak", "list", "--app", "--columns=application,version,origin"], timeout=30)
    except Exception:
        return {}
    rows = {}
    for line in (process.stdout or "").splitlines():
        app_id, *values = line.split("\t")
        if not app_id:
            continue
        rows[app_id] = {
            "version": values[0] if values else "",
            "origin": values[1] if len(values) > 1 else "",
        }
    return rows


def latest_release(timeout: int = 10) -> dict[str, str] | None:
    """Return the latest public GitHub release without blocking the GTK thread."""
    request = urllib.request.Request(
        GITHUB_RELEASES_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": COPR_AGENT},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return None
    tag = str(data.get("tag_name") or "").strip()
    if not tag or data.get("draft") or data.get("prerelease"):
        return None
    rpm_url = ""
    for asset in data.get("assets") or []:
        name = str(asset.get("name") or "")
        if not name.endswith(".rpm") or name.endswith(".src.rpm"):
            continue
        url = str(asset.get("browser_download_url") or "")
        if url and (name.endswith(".noarch.rpm") or not rpm_url):
            rpm_url = url
            if name.endswith(".noarch.rpm"):
                break
    return {
        "tag": tag,
        "version": tag.removeprefix("v"),
        "url": str(data.get("html_url") or ""),
        "rpm_url": rpm_url,
    }


def download_release_rpm(rpm_url: str, dest: Path, timeout: int = 300) -> Path:
    """Download a GitHub release RPM asset to ``dest`` and return its path."""
    request = urllib.request.Request(rpm_url, headers={"User-Agent": COPR_AGENT})
    with (
        urllib.request.urlopen(request, timeout=timeout) as response,
        dest.open("wb") as handle,
    ):
        shutil.copyfileobj(response, handle)
    return dest


def copr_search_projects(query: str, limit: int = 6) -> list[dict]:
    """Search COPR projects by keyword (``GET /project/search``)."""
    data = _copr_get("/project/search", {"query": query, "limit": limit})
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or []
    else:
        items = []
    return [item for item in items if isinstance(item, dict)][:limit]


def copr_project(owner: str, name: str) -> dict:
    """Fetch one project's metadata including maintainer contact (``GET /project/``)."""
    data = _copr_get("/project/", {"ownername": owner, "projectname": name})
    return data if isinstance(data, dict) else {}


def copr_packages(
    owner: str, name: str, limit: int = 60, include_builds: bool = False
) -> list[dict]:
    """List project packages, optionally enriched with their latest build."""
    data = _copr_get("/package/list", {"ownername": owner, "projectname": name})
    items = data.get("items") if isinstance(data, dict) else None
    if items is None:
        items = data if isinstance(data, list) else []
    packages = [item for item in items if isinstance(item, dict)][:limit]
    if not include_builds:
        return packages
    try:
        builds_data = _copr_get("/build/list", {"ownername": owner, "projectname": name})
    except Exception:
        return packages
    builds = builds_data.get("items") if isinstance(builds_data, dict) else builds_data
    latest: dict[str, dict] = {}
    for build in builds if isinstance(builds, list) else []:
        if not isinstance(build, dict):
            continue
        source = build.get("source_package")
        package_name = source.get("name") if isinstance(source, dict) else None
        if not package_name:
            continue
        if package_name not in latest or build.get("submitted_on", 0) > latest[package_name].get("submitted_on", 0):
            latest[package_name] = build
    for package in packages:
        build = latest.get(str(package.get("name") or ""))
        if build:
            package["latest_build"] = build
    return packages




def info_rows(name: str) -> list[tuple[str, str, str]]:
    """Return [(evr, repository, arch)] entries for a package via ``dnf info``."""
    process = subprocess_(["dnf", "-C", "info", name, "--json"])
    try:
        data = json.loads(process.stdout or "{}")
    except Exception:
        return []
    rows: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    if isinstance(data, dict):
        for value in data.values():
            if not isinstance(value, list):
                continue
            for row in value:
                if row.get("arch") == "src":
                    continue
                key = (row.get("evr", ""), row.get("repository", ""), row.get("arch", ""))
                if not key[0] or key in seen:
                    continue
                seen.add(key)
                rows.append(key)
    return rows


def repo_label(repo_id: str) -> str:
    if str(repo_id).startswith("copr"):
        return "COPR"
    if repo_id == "terra":
        return "Terra"
    if repo_id == "flathub":
        return "Flatpak"
    return "Fedora"


def source_from_repo(repo_id: str) -> str:
    return repo_label(repo_id)


def app_icon_candidates(name: str) -> list[str]:
    lowered = name.casefold()
    known = {
        "firefox": "web-browser",
        "kitty": "utilities-terminal",
        "gimp": "gimp",
        "vlc": "vlc",
        "obsidian": "obsidian",
        "code": "code",
        "inkscape": "inkscape",
        "blender": "blender",
        "thunderbird": "mail-client",
        "libreoffice": "libreoffice-main",
        "krita": "krita",
        "telegram": "org.telegram.TelegramDesktop",
        "steam": "steam",
        "dolphin": "system-file-manager",
        "alacritty": "org.alacritty.Alacritty",
        "audacity": "audacity",
        "obs-studio": "com.obsproject.Studio",
    }
    result = []
    if lowered in known:
        result.append(known[lowered])
    result.extend([name, f"{name.lower()}-symbolic", name.lower()])
    return result


def first_icon(theme_has_icon, name: str, fallback: str = "application-x-executable-symbolic") -> str:
    for candidate in app_icon_candidates(name):
        try:
            if theme_has_icon(candidate):
                return candidate
        except Exception:
            break
    return fallback


def fancy_app_filter(packages: list[dict], limit: int | None = 48) -> list[dict]:
    """Return end-user packages, optionally capped for incremental presentation."""
    bad_suffix = re.compile(r"(-devel|-static|-doc(s)?|-langpack|-libs\d*|-data|-plugins?|-lib|"
                            r"-selinux|-debug|-source|-gtest|-gobject|-arch|-wine)$")
    boring_names = ("fonts", "kernel", "python3", "golang", "perl-", "php", "ruby",
                    "nodejs", "mesa-", "debug", "i686", "headers", "javadoc", "warzone")
    grouped: dict[str, dict] = {}
    for package in packages:
        name = package["name"]
        if any(signal in name.casefold() for signal in boring_names):
            continue
        base = bad_suffix.sub("", name) or name
        slot = grouped.get(base)
        if slot is None:
            grouped[base] = {"name": base, "version": package["evr"], "arch": package["arch"], "repository": package["repository"]}
        elif package["arch"] == "x86_64":
            grouped[base]["arch"] = "x86_64"
        elif slot["arch"] != "x86_64":
            slot["arch"] = package["arch"]
    result = list(grouped.values())
    return result if limit is None else result[:limit]


def threading_worker(function, on_done) -> None:
    def runner():
        try:
            result = function()
            on_done(result, None)
        except Exception as error:
            on_done(None, error)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
