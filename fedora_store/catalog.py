"""UI model for packages shown by the store, filled from real DNF data."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Package:
    name: str
    summary: str = ""
    description: str = ""
    icon: str = "application-x-executable-symbolic"
    source: str = "Fedora"
    repo_id: str = ""
    version: str = ""
    installed_version: Optional[str] = None
    update_version: Optional[str] = None
    arch: str = ""
    flatpak_id: str = ""
    icon_url: str = ""

    @property
    def installed(self) -> bool:
        return self.installed_version is not None

    @property
    def updatable(self) -> bool:
        return self.update_version is not None

    @property
    def origin(self) -> str:
        return {"Fedora": "DNF", "Terra": "Terra", "COPR": "COPR", "Flatpak": "Flatpak"}.get(self.source, "DNF")
