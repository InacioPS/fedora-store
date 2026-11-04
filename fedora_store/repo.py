"""Real Fedora package-source integration through dnf5 and the Copr API.

All ``dnf`` queries run ``dnf -C`` (cache-only) so the interface never blocks
on the network; results come as plain dicts with the JSON keys dnf5 emits
(keys are locale-dependent, so we treat the top-level dict as a single unnamed
list).

COPR discovery uses the public Copr APIv3 (no authentication required):
projects are searched via ``/project/search`` and their packages/maintainer
data via ``/package/list`` and ``/project/``.
"""

import json
import re
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SEARCH_LINE = re.compile(r"^([\w.+-]+)\.([\w.]+)\t(.*)$")

COPR_API = "https://copr.fedorainfracloud.org/api_3"
COPR_AGENT = "fedora-store/1.0 (+https://github.com/fedastore)"


def available_on_system() -> bool:
    return Path("/etc/fedora-release").exists() and shutil.which("dnf") is not None


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


def available_all() -> list[dict]:
    return _run(["list", "--available", "--json"], timeout=300)


def repos() -> list[dict]:
    return _run(["repolist", "--json"])


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


def copr_packages(owner: str, name: str, limit: int = 60) -> list[dict]:
    """List the packages built in a project (``GET /package/list``)."""
    data = _copr_get("/package/list", {"ownername": owner, "projectname": name})
    items = data.get("items") if isinstance(data, dict) else None
    if items is None:
        items = data if isinstance(data, list) else []
    return [item for item in items if isinstance(item, dict)][:limit]


def copr_search(query: str, projects: int = 3, per_project: int = 40) -> dict:
    """Search COPR *packages* and projects through the Copr API.

    The API has no global package-search endpoint, so we search projects by
    keyword and then match package names inside the top hits. Results carry
    the project and maintainer context needed by the UI.
    """
    found_projects = copr_search_projects(query, limit=projects)
    packages: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for project in found_projects:
        owner = str(project.get("ownername") or "")
        project_name = str(project.get("name") or "")
        if not owner or not project_name:
            continue
        try:
            listed = copr_packages(owner, project_name, limit=per_project)
        except Exception:
            listed = []
        for package in listed:
            package_name = str(package.get("name") or "")
            if query.casefold() not in package_name.casefold():
                continue
            key = (owner, project_name, package_name)
            if not package_name or key in seen:
                continue
            seen.add(key)
            packages.append({
                "name": package_name,
                "ownername": owner,
                "projectname": project_name,
                "project_full_name": str(project.get("full_name") or f"{owner}/{project_name}"),
                "project_description": str(project.get("description") or ""),
                "contact": project.get("contact"),
                "homepage": project.get("homepage"),
                "source_type": package.get("source_type"),
            })
    return {"projects": found_projects, "packages": packages}


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


def fancy_app_filter(packages: list[dict], limit: int = 48) -> list[dict]:
    """Heuristic slice of available packages that look like end-user apps."""
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
    return list(grouped.values())[:limit]


def threading_worker(function, on_done) -> None:
    def runner():
        try:
            result = function()
            on_done(result, None)
        except Exception as error:
            on_done(None, error)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
