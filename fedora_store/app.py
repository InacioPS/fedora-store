"""GTK4/libadwaita application for browsing real Fedora packages.

Interface follows the `loja-aplicativos-sidebars` design adapted for
responsiveness: the sidebar navigation moved to a horizontal, centered top
bar so every page can use the full window width (per-page header titles,
application card grid, installed list with batch selection, updates review,
COPR and package sources pages). All data comes from dnf5 at runtime;
operations run through polkit (pkexec).
"""

from __future__ import annotations

import gettext
import os
import sys
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

from fedora_store import repo  # noqa: E402
from fedora_store.catalog import Package  # noqa: E402

APP_ID = "io.github.fedorastore.FedoraStore"
_ = gettext.gettext

SIDEBAR_ITEMS = [
    ("explore", _("Explorar"), "applications-system-symbolic"),
    ("installed", _("Instalados"), "package-x-generic-symbolic"),
    ("updates", _("Atualizações"), "software-update-available-symbolic"),
    ("copr", _("COPR"), "folder-remote-symbolic"),
    ("sources", _("Fontes"), "folder-publicshare-symbolic"),
]

HEADER_TITLES = {
    "explore": _("Catálogo de aplicativos"),
    "installed": _("Instalados"),
    "updates": _("Atualizações"),
    "copr": _("COPR"),
    "sources": _("Fontes"),
}

CHIP_SOURCES = [
    ("Todos", None),
    ("Instalados", "installed"),
    ("DNF", "Fedora"),
    ("Terra", "Terra"),
    ("COPR", "COPR"),
]

SOURCES_DROPDOWN = ["Todas", "Fedora", "Terra", "COPR"]

STYLE = b"""
.fs-header-title { font-weight: 700; font-size: 16px; }
.fs-topbar { border-bottom: 1px solid rgba(0, 0, 0, 0.07); }
.fs-navbtn { font-weight: 600; border-width: 0px; background: none; color: #4A5158; padding: 8px 16px; min-height: 34px; border-radius: 999px; }
.fs-navbtn:hover:not(:checked) { background: rgba(0, 0, 0, 0.06); }
.fs-navbtn:checked { background: #D5E5FA; color: #205A9F; font-weight: 700; }
.fs-heading { font-size: 32px; font-weight: 800; }
.fs-page-title { font-size: 21px; font-weight: 700; }
.fs-name { font-weight: 700; font-size: 17px; }
.fs-search { min-height: 46px; font-size: 15px; }
.fs-chip { font-weight: 600; border-width: 0px; background: none; color: #555C63; padding: 5px 14px; border-radius: 8px; }
.fs-chip:hover:not(:checked) { background: rgba(0, 0, 0, 0.05); }
.fs-chip:checked { background: #D8E8FA; color: #245EA3; font-weight: 700; }
.fs-bold { font-weight: 700; }
.fs-softbtn { background: #ECEFF1; border-width: 0px; color: #444B52; font-weight: 700; min-height: 36px; padding: 0 16px; border-radius: 8px; }
.fs-softbtn:hover { background: #E3E7EA; }
.fs-softbtn:active { background: #DDE2E6; }
.fs-dangerbtn { background: #C94D49; border-width: 0px; color: #FFFFFF; font-weight: 700; min-height: 42px; padding: 0 22px; border-radius: 9px; }
.fs-dangerbtn:hover { background: #D4605C; }
.fs-dangerbtn:active { background: #BC4542; }
.fs-danger-softbtn { background: #F5E4E3; border-width: 0px; color: #A33A37; font-weight: 700; min-height: 36px; padding: 0 16px; border-radius: 8px; }
.fs-danger-softbtn:hover { background: #EDD5D3; }
.fs-dangerlink { background: none; border-width: 0px; color: #A33A37; font-weight: 700; }
.fs-pillbtn { border-radius: 8px; min-height: 36px; padding: 0 20px; }
.fs-linkbtn { background: none; border-width: 0px; color: #2769B4; font-weight: 700; min-height: 32px; padding: 0 10px; border-radius: 8px; }
.fs-linkbtn:hover { background: rgba(0, 0, 0, 0.05); }
.fs-kicker { font-size: 12px; font-weight: 700; color: #70777C; }
.fs-origin { font-size: 12px; font-weight: 700; }
.fs-origin-dnf { color: #577087; }
.fs-origin-terra { color: #577087; }
.fs-origin-copr { color: #8A6A3C; }
.fs-status-ok { color: #287253; font-weight: 600; }
.fs-status-off { color: #9BA0A5; font-weight: 600; }
.fs-banner { background: #FFF3D9; border-radius: 10px; }
.fs-banner-title { color: #795C24; font-weight: 700; font-size: 15px; }
.fs-banner-body { color: #8A6F3A; }
.fs-dialog-title { font-size: 22px; font-weight: 800; }
.fs-state { padding: 28px; }
.fs-dim-icon { color: #9BA0A5; }
.fs-progress trough { min-height: 8px; border-radius: 4px; }
.fs-note { font-size: 14px; }
"""

TILING_WM_MARKERS = (
    "NIRI_SOCKET",
    "SWAYSOCK",
    "HYPRLAND_INSTANCE_SIGNATURE",
    "I3SOCK",
    "WAYFIRE_SOCKET",
    "RIVER_SOCKET",
    "DWAYBAR",
)


def detail_target(name: str) -> str:
    return "win.open-detail::'" + name.replace("'", "''") + "'"


def uses_tiling_wm() -> bool:
    for marker in TILING_WM_MARKERS:
        if os.environ.get(marker):
            return True
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").casefold()
    return any(name in desktop for name in ("niri", "sway", "hyprland", "i3", "dwl", "river", "wayfire"))


class FedoraStore(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.connect("activate", self.on_activate)
        self.page = "explore"
        self.detail_package: Package | None = None
        self.safe = False
        self.busy = False
        self._busy_summary = ""
        self.query = ""
        self.filter_source = "Todos"
        self.view_mode = "grid"
        self.sort_mode = 0
        self.query_installed = ""
        self.installed_source = 0
        self.copr_query = ""
        self.selected: set[str] = set()
        self.window: Adw.ApplicationWindow | None = None
        self.toast_overlay: Adw.ToastOverlay | None = None
        self.main_box: Gtk.Box | None = None
        self.sidebar_rows: dict[str, Gtk.ToggleButton] = {}
        self.updates_badge: Gtk.Label | None = None

        self.packages_installed: dict[str, dict] = {}
        self.packages_upgrades: list[dict] = []
        self.packages_featured: list[dict] = []
        self.repos: list[dict] = []
        self.ready = False
        self.featured_ready = False
        self.search_token = 0
        self.search_pending = False
        self.search_results: list[dict] | None = None
        self.summary_cache: dict[str, str] = {}
        self._search_handle: dict = {}
        self._active_search = ""
        self._icon_cache: dict[str, str] = {}
        self._focus_attr: str | None = None
        self._search_entries: dict[str, Gtk.SearchEntry] = {}
        self._detail_pending: set[str] = set()
        self._detail_info: dict[str, tuple] = {}
        self._detail_failed: set[str] = set()
        # Copr APIv3 search (public, no authentication)
        self.copr_search_token = 0
        self.copr_search_pending = False
        self.copr_search_data: dict | None = None
        self.copr_search_failed = False
        self.copr_projects_token = 0
        self.copr_projects_pending = False
        self.copr_projects_data: list[dict] | None = None
        self.copr_projects_failed = False
        self._copr_expanded: dict[str, dict] = {}
        self._copr_loading: set[str] = set()
        self._copr_rows: dict[str, Adw.ExpanderRow] = {}

    # ---------- boot ----------

    def on_activate(self, _app: Adw.Application) -> None:
        if self.window:
            self.window.present()
            return
        self.window = Adw.ApplicationWindow(application=self, title=_("Aplicativos"))
        self.window.set_default_size(1440, 900)
        self.window.set_size_request(780, 560)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)
        if uses_tiling_wm() and (settings := Gtk.Settings.get_default()):
            settings.set_property("gtk-decoration-layout", ":close")
        self.toast_overlay = Adw.ToastOverlay()
        self.window.set_content(self.toast_overlay)

        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        display = self.window.get_display()
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.toast_overlay.set_child(root)
        self._build_topnav(root)
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.set_hexpand(True)
        self.main_box.set_vexpand(True)
        root.append(self.main_box)

        self._register_actions()
        self.render_page()
        self.window.present()
        self._load_initial()

    def _icon_available(self, name: str) -> bool:
        if not self.window:
            return False
        theme = Gtk.IconTheme.get_for_display(self.window.get_display())
        try:
            return bool(theme.has_icon(name))
        except Exception:
            return False

    def _icon_for(self, name: str) -> str:
        cached = self._icon_cache.get(name)
        if cached:
            return cached
        icon = repo.first_icon(self._icon_available, name)
        self._icon_cache[name] = icon
        return icon

    # ---------- data loading ----------

    def _load_initial(self) -> None:
        def core_worker():
            try:
                installed_rows = repo.installed()
                upgrade_rows = repo.upgrades()
                repos_rows = repo.repos()
                GLib.idle_add(self._apply_core, installed_rows, upgrade_rows, repos_rows)
            except Exception as error:
                GLib.idle_add(self._core_failed, error)

        def featured_worker():
            try:
                rows = repo.available_all()
            except Exception:
                rows = []
            for summary in []:
                pass
            results = repo.fancy_app_filter(rows) if rows else []
            GLib.idle_add(self._apply_featured, results)

        threading.Thread(target=core_worker, daemon=True).start()
        threading.Thread(target=featured_worker, daemon=True).start()

    def _apply_core(self, installed_rows, upgrade_rows, repos_rows) -> bool:
        if installed_rows or not self.packages_installed:
            self.packages_installed = {row["name"]: row for row in installed_rows}
        if upgrade_rows or not self.packages_upgrades:
            self.packages_upgrades = list(upgrade_rows)
        if repos_rows or not self.repos:
            self.repos = list(repos_rows)
        self.ready = True
        self._update_badge()
        self.render_page()
        return False

    def _core_failed(self, error) -> bool:
        self.ready = True
        self._update_badge()
        self.render_page()
        self._toast(_("Não foi possível ler o DNF: {0}").format(str(error)[:120]))
        return False

    def _apply_featured(self, results) -> bool:
        self.packages_featured = results
        self.featured_ready = True
        if self.page == "explore" and not self.detail_package:
            self.render_page()
        return False

    def _update_badge(self) -> None:
        count = self._updates_count()
        if self.updates_badge:
            self.updates_badge.set_text(str(count))
            self.updates_badge.set_visible(count > 0)

    def _updates_count(self) -> int:
        return len(self.packages_upgrades)

    def _build_pkg(self, name: str, **overrides) -> Package | None:
        installed_row = self.packages_installed.get(name)
        upgrade_row = next((u for u in self.packages_upgrades if u["name"] == name), None)
        featured_row = next((f for f in self.packages_featured if f["name"] == name), None)
        found = installed_row or upgrade_row or featured_row
        if not found and not overrides:
            return None
        repo_id = (found or {}).get("repository", "")
        source = repo.repo_label(repo_id) if repo_id else overrides.get("source", "Fedora")
        package = Package(
            name=name,
            summary=overrides.get("summary", self.summary_cache.get(name, "")),
            description=overrides.get("description", ""),
            icon=self._icon_for(name),
            source=source,
            repo_id=repo_id,
            version=overrides.get("version", (found or {}).get("evr", "")),
            arch=(found or {}).get("arch", overrides.get("arch", "")),
        )
        if installed_row:
            package.installed_version = installed_row.get("evr")
        if upgrade_row:
            package.update_version = upgrade_row.get("evr")
            package.repo_id = upgrade_row.get("repository", repo_id)
        return package

    def _pkg(self, name: str, summary: str = "") -> Package | None:
        package = self._build_pkg(name, summary=summary)
        if not package:
            package = Package(name=name, summary=summary, icon=self._icon_for(name))
        return package

    # ---------- Sidebar ----------

    def _build_topnav(self, root: Gtk.Box) -> None:
        topbar = Gtk.CenterBox()
        topbar.add_css_class("fs-topbar")
        topbar.set_margin_top(10)
        topbar.set_margin_bottom(8)
        topbar.set_margin_start(16)
        topbar.set_margin_end(16)
        root.append(topbar)

        brand = Gtk.Box(spacing=10)
        brand.set_margin_start(6)
        icon = "preferences-desktop-apps-symbolic" if self._icon_available("preferences-desktop-apps-symbolic") else "application-x-executable-symbolic"
        brand.append(Gtk.Image(icon_name=icon, pixel_size=20))
        brand_label = Gtk.Label(label=_("Aplicativos"), xalign=0)
        brand_label.add_css_class("title-4")
        brand.append(brand_label)
        topbar.set_start_widget(brand)

        # Invisible mirror of the brand keeps the centered nav optically centered.
        mirror = Gtk.Box(spacing=10)
        mirror.set_margin_start(6)
        mirror.append(Gtk.Image(icon_name=icon, pixel_size=20))
        mirror_label = Gtk.Label(label=_("Aplicativos"), xalign=0)
        mirror_label.add_css_class("title-4")
        mirror.append(mirror_label)
        mirror.set_opacity(0.0)
        topbar.set_end_widget(mirror)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        topbar.set_center_widget(nav)

        first: Gtk.ToggleButton | None = None
        for key, label, ic in SIDEBAR_ITEMS:
            btn = Gtk.ToggleButton()
            btn.set_name(key)
            btn.set_tooltip_text(label)
            content = Gtk.Box(spacing=8)
            content.append(Gtk.Image(
                icon_name=ic if self._icon_available(ic) else "application-x-executable-symbolic",
                pixel_size=16))
            content.append(Gtk.Label(label=label))
            if key == "updates":
                badge = Gtk.Label(label=str(self._updates_count()))
                badge.add_css_class("dim-label")
                badge.set_visible(self._updates_count() > 0)
                content.append(badge)
                self.updates_badge = badge
            btn.set_child(content)
            btn.add_css_class("fs-navbtn")
            if first:
                btn.set_group(first)
            else:
                first = btn
            btn.connect("clicked", self._nav_clicked, key)
            nav.append(btn)
            self.sidebar_rows[key] = btn
        self._select_sidebar_row()

    def _select_sidebar_row(self) -> None:
        btn = self.sidebar_rows.get(self.page)
        if btn and not btn.get_active():
            btn.set_active(True)

    def _nav_clicked(self, btn: Gtk.ToggleButton, key: str) -> None:
        if not btn.get_active():
            return
        if self.page == key and not self.detail_package:
            return
        self.navigate(key)

    def navigate(self, page: str) -> None:
        self.page = page
        self.detail_package = None
        self.selected.clear()
        self._select_sidebar_row()
        self.render_page()

    # ---------- Page shell ----------

    def _clear(self, box: Gtk.Widget) -> None:
        child = box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            box.remove(child)
            child = next_child

    def render_page(self) -> None:
        if not self.main_box:
            return
        self._focus_attr = self._focus_attr_now()
        self.safe = True
        self._clear(self.main_box)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        if self.detail_package:
            title = _("Detalhes do aplicativo")
            back = Gtk.Button()
            row = Gtk.Box(spacing=6)
            row.append(Gtk.Image(icon_name="go-previous-symbolic"))
            row.append(Gtk.Label(label=_("Voltar")))
            back.set_child(row)
            back.add_css_class("flat")
            back.add_css_class("fs-linkbtn")
            back.connect("clicked", self._back_to_catalog)
            header.pack_start(back)
        else:
            title = HEADER_TITLES[self.page]
        title_label = Gtk.Label(label=title)
        title_label.add_css_class("fs-header-title")
        header.set_title_widget(title_label)
        view.add_top_bar(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        clamp = Adw.Clamp(tightening_threshold=900, maximum_size=1100)
        scroller.set_child(clamp)
        view.set_content(scroller)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        body.set_margin_top(34)
        body.set_margin_bottom(40)
        body.set_margin_start(32)
        body.set_margin_end(32)
        clamp.set_child(body)
        self.main_box.append(view)
        renderers = {
            "explore": self._explore,
            "installed": self._installed,
            "updates": self._updates,
            "copr": self._copr_page,
            "sources": self._sources,
        }
        self.safe = False
        if self.detail_package:
            self._render_detail(body)
        else:
            renderers.get(self.page, self._explore)(body)

    def _back_to_catalog(self, *_args: object) -> None:
        self.detail_package = None
        self.render_page()

    def _page_block(self, body: Gtk.Box, title: str, subtitle: str) -> Gtk.Box:
        block = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("fs-heading")
        block.append(heading)
        desc = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        desc.add_css_class("dim-label")
        block.append(desc)
        body.append(block)
        return block

    def _search_entry(self, placeholder: str, attr: str) -> Gtk.SearchEntry:
        entry = Gtk.SearchEntry(placeholder_text=placeholder)
        entry.add_css_class("fs-search")
        self.safe = True
        entry.set_text(getattr(self, attr) or "")
        self.safe = False
        entry.connect("activate", self._entry_activate, attr)
        entry.connect("stop-search", self._entry_stop, attr)
        self._search_entries[attr] = entry
        if self._focus_attr == attr:
            GLib.idle_add(self._refocus, entry)
        return entry

    @staticmethod
    def _refocus(entry: Gtk.SearchEntry) -> bool:
        entry.grab_focus()
        return False

    def _focus_attr_now(self) -> str | None:
        """Attribute of the search entry that currently holds the focus, if any.

        Gtk.SearchEntry is composite: focus lands on its internal GtkText, so
        ``has_focus()`` on the entry itself is unreliable. Walk the focus
        widget's parents instead.
        """
        if not self.window:
            return None
        focus = self.window.get_focus()
        while focus is not None:
            for attr, entry in self._search_entries.items():
                if focus == entry:
                    return attr
            focus = focus.get_parent()
        return None

    def _entry_activate(self, entry: Gtk.SearchEntry, attr: str) -> None:
        if self.safe:
            return
        text = entry.get_text().strip()
        setattr(self, attr, text.casefold())
        if attr == "copr_query":
            if text:
                self._begin_copr_projects(text)
            else:
                self.copr_projects_token += 1
                self.copr_projects_pending = False
                self.copr_projects_data = None
                self.copr_projects_failed = False
                self.render_page()
            return
        if attr != "query":
            self.render_page()
            return
        if not text:
            self.query = ""
            self.search_results = None
            self._active_search = ""
            self.search_token += 1
            self._clear_copr_search()
            self.render_page()
            return
        if text.casefold() == self._active_search and self.search_results is not None:
            if self.copr_search_data is None and not self.copr_search_pending:
                self._begin_copr_search(text)
            else:
                self.render_page()
            return
        self._begin_search(text)

    def _entry_stop(self, entry: Gtk.SearchEntry, attr: str) -> None:
        if self.safe:
            return
        setattr(self, attr, "")
        if attr == "query":
            self.search_results = None
            self._active_search = ""
            self.search_token += 1
            self._clear_copr_search()
        if attr == "copr_query":
            self.copr_projects_token += 1
            self.copr_projects_pending = False
            self.copr_projects_data = None
            self.copr_projects_failed = False
        self.render_page()

    def _state_card(self, title: str, message: str, icon: str | None = None,
                    action_label: str | None = None, callback=None, spinner: bool = False) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        card.add_css_class("card")
        card.add_css_class("fs-state")
        card.set_valign(Gtk.Align.START)
        if spinner:
            spin = Gtk.Spinner()
            spin.set_spinning(True)
            spin.set_halign(Gtk.Align.START)
            card.append(spin)
        elif icon:
            image = Gtk.Image(icon_name=icon if self._icon_available(icon) else "application-x-executable-symbolic", pixel_size=36)
            image.add_css_class("fs-dim-icon")
            image.set_halign(Gtk.Align.START)
            card.append(image)
        heading = Gtk.Label(label=title, xalign=0, wrap=True)
        heading.add_css_class("fs-name")
        card.append(heading)
        detail = Gtk.Label(label=message, xalign=0, wrap=True)
        detail.add_css_class("dim-label")
        card.append(detail)
        if action_label and callback:
            action = Gtk.Button(label=action_label)
            row = Gtk.Box(spacing=6)
            row.append(Gtk.Image(icon_name="view-refresh-symbolic"))
            row.append(Gtk.Label(label=action_label))
            action.set_child(row)
            action.add_css_class("flat")
            action.add_css_class("fs-linkbtn")
            action.set_halign(Gtk.Align.START)
            action.connect("clicked", callback)
            card.append(action)
        return card

    def _origin_label(self, package: Package) -> Gtk.Label:
        origin = package.origin
        label = Gtk.Label(label=origin, xalign=0)
        label.add_css_class("fs-origin")
        key = {"DNF": "dnf", "Terra": "terra"}.get(origin, "copr")
        label.add_css_class(f"fs-origin-{key}")
        return label

    # ---------- Search ----------

    def _begin_search(self, query: str) -> None:
        self._active_search = query.casefold()
        self.search_token += 1
        token = self.search_token
        stale = self._search_handle.get("process")
        if stale is not None and stale.poll() is None:
            try:
                stale.kill()
            except Exception:
                pass
        self.search_pending = True
        self.search_results = None
        if self.page == "explore":
            self.render_page()

        def worker():
            rows = []
            try:
                rows = repo.search(query, handle=self._search_handle)
            except Exception:
                rows = []
            GLib.idle_add(self._finish_search, token, query.casefold(), rows)

        threading.Thread(target=worker, daemon=True).start()
        self._begin_copr_search(query)

    def _clear_copr_search(self) -> None:
        self.copr_search_token += 1
        self.copr_search_pending = False
        self.copr_search_data = None
        self.copr_search_failed = False

    def _begin_copr_search(self, query: str) -> None:
        """Kick a Copr APIv3 search (projects + packages) in the background."""
        self.copr_search_token += 1
        token = self.copr_search_token
        self.copr_search_pending = True
        self.copr_search_data = None
        self.copr_search_failed = False

        def worker() -> None:
            data: dict | None = None
            try:
                data = repo.copr_search(query)
            except Exception:
                data = None
            GLib.idle_add(self._finish_copr_search, token, data)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_copr_search(self, token: int, data: dict | None) -> bool:
        if token != self.copr_search_token:
            return False
        self.copr_search_pending = False
        if data is None:
            self.copr_search_failed = True
            self.copr_search_data = None
        else:
            self.copr_search_data = data
        if self.page == "explore" and not self.detail_package:
            self.render_page()
        return False

    def _begin_copr_projects(self, query: str) -> None:
        """Search COPR projects through the API (sources page)."""
        self.copr_projects_token += 1
        token = self.copr_projects_token
        self.copr_projects_pending = True
        self.copr_projects_data = None
        self.copr_projects_failed = False

        def worker() -> None:
            data: list[dict] | None = None
            try:
                data = repo.copr_search_projects(query, limit=8)
            except Exception:
                data = None
            GLib.idle_add(self._finish_copr_projects, token, data)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_copr_projects(self, token: int, data: list[dict] | None) -> bool:
        if token != self.copr_projects_token:
            return False
        self.copr_projects_pending = False
        if data is None:
            self.copr_projects_failed = True
            self.copr_projects_data = None
        else:
            self.copr_projects_data = data
        if self.page == "copr" and not self.detail_package:
            self.render_page()
        return False

    def _finish_search(self, token: int, query: str, rows: list[dict]) -> bool:
        if token != self.search_token:
            return False
        self.search_pending = False
        self.search_results = rows
        for row in rows:
            self.summary_cache[row["name"]] = row["summary"]
        if self.page == "explore":
            self.render_page()
        return False

    # ---------- Explorar ----------

    def _explore(self, body: Gtk.Box) -> None:
        self._page_block(body, _("Explore aplicativos"), _("Catálogo real do Fedora e das fontes habilitadas neste sistema."))
        body.append(self._search_entry(_("Buscar pacotes nos repositórios"), "query"))

        controls = Gtk.Box(spacing=8)
        first: Gtk.ToggleButton | None = None
        for source, _key in CHIP_SOURCES:
            chip = Gtk.ToggleButton(label=_(source))
            chip.add_css_class("fs-chip")
            if source == self.filter_source:
                chip.set_active(True)
            if first:
                chip.set_group(first)
            else:
                first = chip
            chip.connect("toggled", self._filter_toggled, source)
            controls.append(chip)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        controls.append(spacer)
        dropdown = Gtk.DropDown.new_from_strings([_("Nome (A–Z)"), _("Origem")])
        dropdown.add_css_class("flat")
        dropdown.set_selected(self.sort_mode)
        dropdown.connect("notify::selected", self._sort_changed)
        controls.append(dropdown)
        grid_btn = Gtk.ToggleButton()
        grid_btn.set_icon_name("view-grid-symbolic")
        grid_btn.add_css_class("flat")
        list_btn = Gtk.ToggleButton()
        list_btn.set_icon_name("view-list-symbolic")
        list_btn.add_css_class("flat")
        grid_btn.set_group(list_btn)
        (grid_btn if self.view_mode == "grid" else list_btn).set_active(True)
        grid_btn.connect("toggled", self._view_toggled, "grid")
        list_btn.connect("toggled", self._view_toggled, "list")
        linked = Gtk.Box(spacing=0)
        linked.append(grid_btn)
        linked.append(list_btn)
        controls.append(linked)
        body.append(controls)

        if not self.ready:
            body.append(self._state_card(_("Carregando catálogo"), _("Lendo os repositórios do sistema…"), spinner=True))
            return

        if self.query:
            self._explore_search(body)
            return

        if not self.featured_ready:
            body.append(self._state_card(_("Carregando catálogo"), _("Consultando os repositórios do sistema…"), spinner=True))
            return

        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        heading = Gtk.Label(label=_("Aplicativos para você"), xalign=0)
        heading.add_css_class("fs-page-title")
        section.append(heading)
        caption = Gtk.Label(label=_("Pacotes disponíveis nos repositórios habilitados"), xalign=0)
        caption.add_css_class("dim-label")
        section.append(caption)
        body.append(section)

        if self.selected and self.page == "explore":
            body.append(self._bulk_bar(_("Aplicar selecionados")))
        rows = self._featured_rows()
        if not rows:
            message = _("Ainda não há dados dos repositórios; aguarde ou tente novamente.")
            body.append(self._state_card(
                _("Nenhum resultado encontrado"), message,
                icon="system-search-symbolic", action_label=_("Recarregar"),
                callback=self._reload_data))
            return
        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_homogeneous(True)
        grid.set_min_children_per_line(1)
        grid.set_max_children_per_line(3)
        grid.set_column_spacing(16)
        grid.set_row_spacing(16)
        grid.set_valign(Gtk.Align.START)
        for package in rows:
            grid.append(self._package_card(package))
        body.append(grid)

    def _explore_search(self, body: Gtk.Box) -> None:
        if self.search_pending and self.search_results is None:
            body.append(self._state_card(_("Buscando"), _("Consultando o DNF por “{0}”…").format(self.query), spinner=True))
            body.append(self._copr_results_section())
            return
        rows = self.search_results or []
        cards = []
        for row in rows:
            summary = row.get("summary", "")
            package = self._pkg(row["name"], summary=summary)
            if package is None:
                continue
            if self.filter_source == "Instalados" and not package.installed:
                continue
            if self.filter_source not in ("Todos", "Instalados") and package.source != self.filter_source:
                continue
            cards.append(package)
        if self.search_pending:
            body.append(self._state_card(_("Buscando"), _("Consultando o DNF por “{0}”…").format(self.query), spinner=True))
        if not self.search_pending and not cards:
            body.append(self._state_card(
                _("Nenhum resultado no DNF"),
                _("Nada nos repositórios habilitados corresponde a “{0}”.").format(self.query),
                icon="system-search-symbolic",
            ))
        else:
            if self.selected:
                body.append(self._bulk_bar(_("Aplicar selecionados")))
            total = len(cards)
            if total > 80:
                cards = cards[:80]
            if cards:
                body.append(self._package_list(cards))
            if total > 80:
                note = Gtk.Label(label=_("Mostrando os {0} primeiros de {1} resultados — refine a busca.").format(len(cards), total), xalign=0, wrap=True)
                note.add_css_class("dim-label")
                body.append(note)
        body.append(self._copr_results_section())

    # ---------- COPR via API ----------

    def _enabled_copr_projects(self) -> set[str]:
        projects = set()
        for row in self.repos:
            identifier = str(row["id"])
            if identifier.startswith(("copr:", "coprdep:")):
                project = self.copr_owner_project(identifier)
                if project:
                    projects.add(project)
        return projects

    def _copr_results_section(self) -> Gtk.Widget:
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        heading = Gtk.Label(label=_("COPR  ·  Descoberta pela API comunitária"), xalign=0)
        heading.add_css_class("fs-page-title")
        section.append(heading)
        caption = Gtk.Label(label=_("Projetos e pacotes de copr.fedorainfracloud.org, mesmo sem estar habilitado."), xalign=0, wrap=True)
        caption.add_css_class("dim-label")
        section.append(caption)

        if self.copr_search_pending:
            section.append(self._state_card(
                _("Buscando no COPR"),
                _("Pesquisando projetos e pacotes na API do Fedora…"),
                spinner=True,
            ))
            return section
        if self.copr_search_failed:
            section.append(self._state_card(
                _("API do COPR indisponível"),
                _("Não foi possível consultar copr.fedorainfracloud.org. Verifique a conexão."),
                icon="network-offline-symbolic",
                action_label=_("Tentar novamente"),
                callback=lambda *_: self._begin_copr_search(self.query),
            ))
            return section
        data = self.copr_search_data
        if not data:
            return section
        packages = list(data.get("packages") or [])
        projects = list(data.get("projects") or [])
        if not packages and not projects:
            section.append(self._state_card(
                _("Nenhum resultado no COPR"),
                _("A API comunitária não encontrou projetos ou pacotes para “{0}”.").format(self.query),
                icon="system-search-symbolic",
            ))
            return section
        enabled = self._enabled_copr_projects()
        if packages:
            listbox = Gtk.ListBox()
            listbox.set_selection_mode(Gtk.SelectionMode.NONE)
            listbox.add_css_class("card")
            listbox.add_css_class("boxed-list")
            for pkg in packages[:8]:
                listbox.append(self._copr_package_row(pkg, enabled))
            section.append(listbox)
        else:
            cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            for project in projects[:4]:
                cards.append(self._copr_project_card(project, enabled))
            section.append(cards)
        return section

    def _copr_package_row(self, pkg: dict, enabled: set[str]) -> Gtk.Widget:
        row = Gtk.Box(spacing=14)
        row.set_margin_top(12)
        row.set_margin_bottom(12)
        row.set_margin_start(16)
        row.set_margin_end(16)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        texts.set_hexpand(True)
        title = Gtk.Label(label=str(pkg.get("name") or ""), xalign=0, wrap=True)
        title.add_css_class("fs-name")
        texts.append(title)
        owner = str(pkg.get("ownername") or "")
        project_name = str(pkg.get("projectname") or "")
        maintainer = str(pkg.get("contact") or owner)
        sub = Gtk.Label(
            label=_("{0} · mantenedor {1}").format(pkg.get("project_full_name") or f"{owner}/{project_name}", maintainer),
            xalign=0, wrap=True,
        )
        sub.add_css_class("dim-label")
        sub.add_css_class("fs-note")
        texts.append(sub)
        if pkg.get("project_description"):
            desc_text = str(pkg["project_description"]).strip().replace("\n", " ")
            if len(desc_text) > 160:
                desc_text = desc_text[:157] + "…"
            desc = Gtk.Label(label=desc_text, xalign=0, wrap=True)
            desc.add_css_class("dim-label")
            texts.append(desc)
        row.append(texts)
        project = f"{owner}/{project_name}"
        if project in enabled:
            status = Gtk.Label(label="●  " + _("Habilitado"), xalign=0)
            status.add_css_class("fs-status-ok")
            status.set_valign(Gtk.Align.CENTER)
            row.append(status)
        else:
            enable = Gtk.Button()
            side = Gtk.Box(spacing=6)
            side.append(Gtk.Label(label=_("Habilitar")))
            side.append(Gtk.Image(icon_name="go-next-symbolic"))
            enable.set_child(side)
            enable.add_css_class("flat")
            enable.add_css_class("fs-linkbtn")
            enable.set_valign(Gtk.Align.CENTER)
            enable.connect("clicked", self._enable_copr_project, project)
            row.append(enable)
        return row

    def _copr_project_card(self, project: dict, enabled: set[str]) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        card.set_margin_top(4)
        card.set_margin_bottom(4)
        name = Gtk.Label(label=str(project.get("full_name") or project.get("name") or ""), xalign=0, wrap=True)
        name.add_css_class("fs-name")
        card.append(name)
        description = str(project.get("description") or "").strip().replace("\n", " ")
        if len(description) > 220:
            description = description[:217] + "…"
        if description:
            desc = Gtk.Label(label=description, xalign=0, wrap=True)
            desc.add_css_class("dim-label")
            card.append(desc)
        contact = project.get("contact")
        footer = Gtk.Box(spacing=10)
        maintainer = Gtk.Label(
            label=_("Mantenedor: {0}").format(contact or project.get("ownername") or "—"),
            xalign=0,
        )
        maintainer.add_css_class("dim-label")
        maintainer.set_hexpand(True)
        footer.append(maintainer)
        full_name = str(project.get("full_name") or "")
        if full_name in enabled:
            status = Gtk.Label(label="●  " + _("Habilitado"))
            status.add_css_class("fs-status-ok")
            footer.append(status)
        else:
            enable = Gtk.Button(label=_("Habilitar"))
            enable.add_css_class("suggested-action")
            enable.add_css_class("fs-pillbtn")
            enable.connect("clicked", self._enable_copr_project, full_name)
            footer.append(enable)
        card.append(footer)
        return card

    def _enable_copr_project(self, _button: Gtk.Widget, project: str) -> None:
        if not project or "/" not in project:
            self._toast(_("Projeto COPR inválido."))
            return
        GLib.idle_add(self._run_copr_toggle, project, True)

    def _reload_data(self, *_args: object) -> None:
        self.featured_ready = False
        self.render_page()
        self._load_initial()

    def _featured_rows(self) -> list[Package]:
        rows: list[Package] = []
        for row in self.packages_featured:
            name = row["name"]
            if self.filter_source == "Instalados" and name not in self.packages_installed:
                continue
            if self.filter_source not in ("Todos", "Instalados"):
                if repo.repo_label(row.get("repository", "")) != self.filter_source:
                    continue
            package = self._pkg(name)
            if package:
                package.version = row.get("version", package.version)
                package.arch = row.get("arch", package.arch)
                repo_id = row.get("repository", "")
                package.repo_id = repo_id
                package.source = repo.repo_label(repo_id)
                if not package.installed and name in self.packages_installed:
                    package.installed_version = self.packages_installed[name].get("evr")
                rows.append(package)
        if self.sort_mode == 0:
            rows.sort(key=lambda package: package.name.casefold())
        else:
            rows.sort(key=lambda package: (package.source, package.name.casefold()))
        return rows

    def _filter_toggled(self, button: Gtk.ToggleButton, source: str) -> None:
        if self.safe or not button.get_active() or source == self.filter_source:
            return
        self.filter_source = source
        self.render_page()

    def _sort_changed(self, dropdown: Gtk.DropDown, _param: object) -> None:
        if self.safe:
            return
        self.sort_mode = dropdown.get_selected()
        self.render_page()

    def _view_toggled(self, button: Gtk.ToggleButton, mode: str) -> None:
        if self.safe or not button.get_active() or mode == self.view_mode:
            return
        self.view_mode = mode
        self.render_page()

    def _package_card(self, package: Package) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("card")
        card.set_size_request(300, 190)
        card.set_margin_top(2)
        card.set_margin_bottom(2)
        card.set_margin_start(2)
        card.set_margin_end(2)

        top = Gtk.Box(spacing=14)
        top.set_valign(Gtk.Align.START)
        top.set_margin_top(18)
        top.set_margin_start(18)
        top.set_margin_end(18)
        intro = Gtk.Box(spacing=14)
        intro.set_hexpand(True)
        intro.append(Gtk.Image(icon_name=package.icon, pixel_size=44))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        name = Gtk.Label(label=package.name, xalign=0, wrap=True)
        name.add_css_class("fs-name")
        texts.append(name)
        summary = Gtk.Label(label=package.summary or _("Versão {0}").format(package.version or package.origin), xalign=0, wrap=True, max_width_chars=26)
        summary.add_css_class("dim-label")
        texts.append(summary)
        intro.append(texts)
        top.append(intro)
        card.append(top)
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        card.append(spacer)
        detail = Gtk.GestureClick()
        detail.connect("released", self._open_detail, package)
        intro.add_controller(detail)

        actions = Gtk.Box(spacing=8)
        actions.set_margin_top(4)
        actions.set_margin_bottom(16)
        actions.set_margin_start(18)
        actions.set_margin_end(18)
        origin = self._origin_label(package)
        origin.set_halign(Gtk.Align.START)
        origin.set_valign(Gtk.Align.CENTER)
        origin.set_hexpand(True)
        actions.append(origin)
        op = self._operation(package)
        action = Gtk.Button(label=op)
        if op == _("Remover"):
            action.add_css_class("fs-softbtn")
        else:
            action.add_css_class("suggested-action")
            action.add_css_class("fs-bold")
        action.add_css_class("fs-pillbtn")
        action.set_valign(Gtk.Align.CENTER)
        action.connect("clicked", self._package_action, package)
        actions.append(action)
        menu = Gio.Menu()
        menu.append(_("Abrir detalhes"), detail_target(package.name))
        menu.append(_("Selecionar"), "win.toggle-select::'" + package.name.replace("'", "''") + "'")
        more = Gtk.MenuButton(menu_model=menu)
        more.set_icon_name("view-more-symbolic")
        more.add_css_class("flat")
        more.set_valign(Gtk.Align.CENTER)
        actions.append(more)
        card.append(actions)
        return card

    def _package_list(self, packages: list[Package]) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.add_css_class("card")
        for package in packages:
            row = Gtk.Box(spacing=14)
            row.set_margin_top(12)
            row.set_margin_bottom(12)
            row.set_margin_start(16)
            row.set_margin_end(16)
            row.append(Gtk.Image(icon_name=package.icon, pixel_size=32))
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            texts.set_hexpand(True)
            name = Gtk.Label(label=package.name, xalign=0)
            name.add_css_class("fs-name")
            texts.append(name)
            summary = Gtk.Label(label=package.summary or package.version, xalign=0, wrap=True)
            summary.add_css_class("dim-label")
            texts.append(summary)
            row.append(texts)
            row.append(self._origin_label(package))
            op = self._operation(package)
            action = Gtk.Button(label=op)
            if op == _("Remover"):
                action.add_css_class("fs-softbtn")
            else:
                action.add_css_class("suggested-action")
                action.add_css_class("fs-bold")
            action.add_css_class("fs-pillbtn")
            action.set_margin_start(10)
            action.connect("clicked", self._package_action, package)
            row.append(action)
            card.append(row)
            click = Gtk.GestureClick()
            click.connect("released", self._open_detail, package)
            texts.add_controller(click)
        return card

    # ---------- Operations ----------

    @staticmethod
    def _operation(package: Package) -> str:
        if package.updatable:
            return _("Atualizar")
        if package.installed:
            return _("Remover")
        return _("Instalar")

    def _open_detail(self, _controller: Gtk.GestureClick, _presses: int, _x: float, _y: float, package: Package) -> None:
        self.detail_package = package
        self.render_page()

    def _package_action(self, _button: Gtk.Widget, package: Package) -> None:
        self._apply([package])

    def _selection_changed(self, check: Gtk.CheckButton, name: str) -> None:
        if check.get_active():
            self.selected.add(name)
        else:
            self.selected.discard(name)
        self.render_page()

    def _bulk_bar(self, action_label: str) -> Gtk.Widget:
        bar = Gtk.Box(spacing=12)
        label = Gtk.Label(label=_("{0} selecionados").format(len(self.selected)), xalign=0)
        label.add_css_class("fs-name")
        bar.append(label)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)
        button = Gtk.Button(label=_(action_label))
        button.add_css_class("fs-danger-softbtn")
        button.connect("clicked", self._bulk_apply)
        bar.append(button)
        return bar

    def _bulk_apply(self, *_args: object) -> None:
        packages = [self._pkg(name) for name in self.selected]
        packages = [p for p in packages if p is not None]
        self._apply(packages)

    # ---------- Instalados ----------

    def _installed(self, body: Gtk.Box) -> None:
        self._page_block(body, _("Aplicativos instalados"), _("Gerencie os pacotes presentes neste computador."))
        body.append(self._search_entry(_("Buscar aplicativos instalados"), "query_installed"))

        controls = Gtk.Box(spacing=10)
        sources = ["Todas", "Fedora", "Terra", "COPR"]
        dropdown_src = Gtk.DropDown.new_from_strings([_(s) for s in sources])
        dropdown_src.set_selected(min(self.installed_source, len(sources) - 1))
        dropdown_src.connect("notify::selected", self._installed_source_changed)
        controls.append(dropdown_src)
        body.append(controls)

        if not self.ready:
            body.append(self._state_card(_("Carregando lista"), _("Lendo os pacotes instalados…"), spinner=True))
            return
        if self.selected:
            body.append(self._bulk_bar(_("Aplicar selecionados")))
        packages = self._installed_packages()
        if not packages:
            body.append(self._state_card(
                _("Nenhum resultado encontrado"),
                _("Tente outra busca ou altere os filtros selecionados."),
                icon="system-search-symbolic",
            ))
            return
        total = len(packages)
        capped = total > 200
        if capped:
            packages = packages[:200]
        for package in packages:
            package.icon = self._icon_for(package.name)
        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        self.safe = True
        for package in packages:
            row = Gtk.Box(spacing=14)
            row.set_margin_top(14)
            row.set_margin_bottom(14)
            row.set_margin_start(16)
            row.set_margin_end(16)
            select = Gtk.CheckButton()
            select.set_active(package.name in self.selected)
            select.set_valign(Gtk.Align.CENTER)
            select.connect("toggled", self._selection_changed, package.name)
            row.append(select)
            row.append(Gtk.Image(icon_name=package.icon, pixel_size=36))
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            texts.set_hexpand(True)
            name = Gtk.Label(label=package.name, xalign=0)
            name.add_css_class("fs-name")
            texts.append(name)
            detail = Gtk.Label(label=_("{0}  ·  Versão {1}").format(package.origin, package.installed_version), xalign=0)
            detail.add_css_class("dim-label")
            texts.append(detail)
            row.append(texts)
            remove = Gtk.Button(label=_("Remover"))
            remove.add_css_class("flat")
            remove.add_css_class("fs-dangerlink")
            remove.set_valign(Gtk.Align.CENTER)
            remove.connect("clicked", self._package_action, package)
            row.append(remove)
            listbox.append(row)
        body.append(listbox)
        if capped:
            note = Gtk.Label(label=_("Mostrando os {0} primeiros de {1} pacotes — use a busca ou os filtros para refinar.").format(len(packages), total), xalign=0, wrap=True)
            note.add_css_class("dim-label")
            body.append(note)
        self.safe = False

    def _installed_packages(self) -> list[Package]:
        packages: list[Package] = []
        upgrade_map = {u["name"]: u for u in self.packages_upgrades}
        for name, row in self.packages_installed.items():
            source = repo.repo_label(row.get("repository", "fedora"))
            if self.installed_source and source != SOURCES_DROPDOWN[self.installed_source]:
                continue
            if self.query_installed and self.query_installed not in name.casefold():
                continue
            package = Package(
                name=name,
                summary=self.summary_cache.get(name, ""),
                source=source,
                repo_id=row.get("repository", ""),
                arch=row.get("arch", ""),
                installed_version=row.get("evr"),
            )
            upgrade_row = upgrade_map.get(name)
            if upgrade_row:
                package.update_version = upgrade_row.get("evr")
            packages.append(package)
        packages.sort(key=lambda p: p.name.casefold())
        return packages

    def _installed_source_changed(self, dropdown: Gtk.DropDown, _param: object) -> None:
        if self.safe:
            return
        self.installed_source = dropdown.get_selected()
        self.render_page()

    # ---------- Atualizações ----------

    def _updates(self, body: Gtk.Box) -> None:
        if not self.ready:
            self._page_block(body, _("Verificando atualizações"), _("Consultando o sistema por pacotes desatualizados."))
            body.append(self._state_card(_("Verificando atualizações"), _("Consultando o DNF…"), spinner=True))
            return
        packages = self._update_packages()
        block = Gtk.Box(spacing=16)
        block.set_hexpand(True)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = Gtk.Label(label=_("Atualizações disponíveis"), xalign=0)
        heading.add_css_class("fs-heading")
        texts.append(heading)
        count = len(packages)
        sub = Gtk.Label(label=_("{0} pacotes podem ser atualizados. Revise as alterações antes de continuar.").format(count), xalign=0, wrap=True)
        sub.add_css_class("dim-label")
        texts.append(sub)
        block.append(texts)
        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        block.append(spacer)
        update_all = Gtk.Button(label=_("Atualizar tudo"))
        update_all.add_css_class("suggested-action")
        update_all.add_css_class("fs-bold")
        update_all.add_css_class("fs-pillbtn")
        update_all.set_valign(Gtk.Align.CENTER)
        update_all.set_sensitive(bool(packages))
        update_all.connect("clicked", self._update_all)
        block.append(update_all)
        body.append(block)

        if not packages:
            body.append(self._state_card(_("Tudo em dia"), _("Não há itens para mostrar."), icon="emblem-ok-symbolic"))
            return

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("card")
        listbox.add_css_class("boxed-list")
        for package in packages:
            row = Gtk.Box(spacing=14)
            row.set_margin_top(14)
            row.set_margin_bottom(14)
            row.set_margin_start(16)
            row.set_margin_end(16)
            row.append(Gtk.Image(icon_name=package.icon, pixel_size=36))
            texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            texts.set_hexpand(True)
            name = Gtk.Label(label=package.name, xalign=0)
            name.add_css_class("fs-name")
            texts.append(name)
            detail = Gtk.Label(label=_("{0}  ·  {1}  →  {2}").format(package.origin, package.installed_version, package.update_version), xalign=0)
            detail.add_css_class("dim-label")
            texts.append(detail)
            row.append(texts)
            update = Gtk.Button(label=_("Atualizar"))
            update.add_css_class("flat")
            update.add_css_class("fs-linkbtn")
            update.set_valign(Gtk.Align.CENTER)
            update.connect("clicked", self._package_action, package)
            row.append(update)
            listbox.append(row)
        body.append(listbox)

    def _update_packages(self) -> list[Package]:
        packages: list[Package] = []
        seen: set[str] = set()
        for upgrade_row in self.packages_upgrades:
            name = upgrade_row["name"]
            if name in seen:
                continue
            seen.add(name)
            name = upgrade_row["name"]
            installed_row = self.packages_installed.get(name)
            package = Package(
                name=name,
                summary=self.summary_cache.get(name, ""),
                icon=self._icon_for(name),
                source=repo.repo_label(upgrade_row.get("repository", "")),
                repo_id=upgrade_row.get("repository", ""),
                arch=upgrade_row.get("arch", ""),
                version=upgrade_row.get("evr"),
                installed_version=installed_row.get("evr") if installed_row else upgrade_row.get("evr"),
                update_version=upgrade_row.get("evr"),
            )
            packages.append(package)
        packages.sort(key=lambda p: p.name.casefold())
        return packages

    def _update_all(self, *_args: object) -> None:
        self._apply(self._update_packages())

    # ---------- Fontes ----------

    def _sources(self, body: Gtk.Box) -> None:
        self._page_block(body, _("Fontes de aplicativos"), _("Repositórios configurados no DNF neste computador."))
        if not self.ready:
            body.append(self._state_card(_("Carregando fontes"), _("Lendo a lista de repositórios…"), spinner=True))
            return

        heading = Gtk.Label(label=_("Repositórios do sistema"), xalign=0)
        heading.add_css_class("fs-page-title")
        body.append(heading)
        system_repos = [r for r in self.repos if not str(r["id"]).startswith(("copr:", "coprdep:"))]
        if not system_repos:
            body.append(self._state_card(
                _("Nenhum repositório encontrado"),
                _("O DNF não retornou repositórios do sistema. Verifique a conexão e recarregue."),
                icon="folder-publicshare-symbolic",
                action_label=_("Recarregar"),
                callback=self._reload_data,
            ))
            return
        cart = Gtk.ListBox()
        cart.set_selection_mode(Gtk.SelectionMode.NONE)
        cart.add_css_class("card")
        cart.add_css_class("boxed-list")
        for repository in system_repos:
            cart.append(self._repo_row(repository, copr=False))
        body.append(cart)

    # ---------- COPR ----------

    def _copr_page(self, body: Gtk.Box) -> None:
        self._page_block(
            body,
            _("Projetos COPR"),
            _("Habilite ou desabilite projetos comunitários e veja mantenedor, "
              "descrição e pacotes — dados da API pública de copr.fedorainfracloud.org."),
        )
        if not self.ready:
            body.append(self._state_card(_("Carregando fontes"), _("Lendo a lista de repositórios…"), spinner=True))
            return
        body.append(self._search_entry(_("Buscar projetos COPR na API"), "copr_query"))
        all_copr = [r for r in self.repos if str(r["id"]).startswith("copr:")]
        copr_repos = [r for r in all_copr if not self.copr_query or self.copr_query in f"{r['id']} {r['name']}".casefold()]
        enabled = self._enabled_copr_projects()
        self._copr_rows = {}

        if self.copr_query:
            api_heading = Gtk.Label(label=_("Resultados na API do COPR"), xalign=0)
            api_heading.add_css_class("fs-page-title")
            body.append(api_heading)
            if self.copr_projects_failed:
                body.append(self._state_card(
                    _("API do COPR indisponível"),
                    _("Não foi possível consultar copr.fedorainfracloud.org. Verifique a conexão."),
                    icon="network-offline-symbolic",
                    action_label=_("Tentar novamente"),
                    callback=lambda *_: self._begin_copr_projects(self.copr_query),
                ))
            elif self.copr_projects_data is None:
                body.append(self._state_card(
                    _("Buscando no COPR"),
                    _("Pesquisando projetos na API do Fedora…"),
                    spinner=True,
                ))
            elif not self.copr_projects_data:
                body.append(self._state_card(
                    _("Nenhum projeto encontrado"),
                    _("A API comunitária não retornou projetos para “{0}”.").format(self.copr_query),
                    icon="system-search-symbolic",
                ))
            else:
                cards = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
                for project in self.copr_projects_data:
                    cards.append(self._copr_project_card(project, enabled))
                body.append(cards)
            if copr_repos:
                local_heading = Gtk.Label(label=_("Habilitados neste sistema"), xalign=0)
                local_heading.add_css_class("fs-page-title")
                body.append(local_heading)
                self._append_copr_expanders(body, copr_repos)
            return

        local_heading = Gtk.Label(label=_("Habilitados neste sistema"), xalign=0)
        local_heading.add_css_class("fs-page-title")
        body.append(local_heading)
        if not copr_repos:
            body.append(self._state_card(
                _("Nenhum projeto COPR habilitado"),
                _("Use a busca acima para encontrar projetos na API comunitária e habilitar."),
                icon="folder-remote-symbolic",
            ))
            return
        self._append_copr_expanders(body, copr_repos)

    def _append_copr_expanders(self, body: Gtk.Box, repositories: list[dict]) -> None:
        cart = Gtk.ListBox()
        cart.set_selection_mode(Gtk.SelectionMode.NONE)
        cart.add_css_class("card")
        cart.add_css_class("boxed-list")
        for repository in repositories:
            cart.append(self._copr_repo_expander(repository))
        body.append(cart)

    def _copr_repo_expander(self, repository: dict) -> Gtk.Widget:
        identifier = str(repository["id"])
        project = self.copr_owner_project(identifier) or identifier
        row = Adw.ExpanderRow(title=str(repository["name"]), subtitle=project)
        status = Gtk.Label(label="●  " + _("Habilitado"))
        status.add_css_class("fs-status-ok")
        status.set_valign(Gtk.Align.CENTER)
        row.add_suffix(status)
        disable = Gtk.Button(label=_("Desabilitar"))
        disable.add_css_class("flat")
        disable.add_css_class("fs-dangerlink")
        disable.set_valign(Gtk.Align.CENTER)
        disable.connect("clicked", self._toggle_repo_action, repository, False)
        row.add_suffix(disable)
        cached = self._copr_expanded.get(project)
        if cached:
            self._fill_copr_expander(row, project, cached)
        row.connect("notify::expanded", self._on_copr_expanded, project)
        self._copr_rows[project] = row
        return row

    def _on_copr_expanded(self, row: Adw.ExpanderRow, _pspec: object, project: str) -> None:
        if not row.get_expanded() or "/" not in project:
            return
        if project in self._copr_expanded or project in self._copr_loading:
            return
        self._copr_loading.add(project)

        def worker() -> None:
            data: dict = {"error": True}
            try:
                owner, name = project.split("/", 1)
                data = {
                    "project": repo.copr_project(owner, name),
                    "packages": repo.copr_packages(owner, name, limit=50),
                }
            except Exception:
                data = {"error": True}
            GLib.idle_add(self._copr_loaded, project, data)

        threading.Thread(target=worker, daemon=True).start()

    def _copr_loaded(self, project: str, data: dict) -> bool:
        self._copr_loading.discard(project)
        self._copr_expanded[project] = data
        row = self._copr_rows.get(project)
        if row is not None:
            try:
                self._fill_copr_expander(row, project, data)
            except Exception:
                pass
        return False

    @staticmethod
    def _fill_copr_expander(row: Adw.ExpanderRow, project: str, data: dict) -> None:
        if getattr(row, "_fs_filled", False):
            return
        row._fs_filled = True
        if data.get("error"):
            error = Gtk.Label(label=_("Falha ao consultar a API do COPR para {0}.").format(project), xalign=0, wrap=True)
            error.add_css_class("dim-label")
            error.set_margin_top(6)
            error.set_margin_bottom(6)
            row.add_row(error)
            return
        info = data.get("project") or {}
        packages = list(data.get("packages") or [])
        owner = str(info.get("ownername") or project.split("/")[0])
        contact = str(info.get("contact") or "")

        def info_row(title: str, value: str) -> Adw.ActionRow:
            item = Adw.ActionRow(title=title)
            item.set_subtitle(value or "—")
            return item

        row.add_row(info_row(_("Mantenedor"), contact or owner))
        homepage = str(info.get("homepage") or "")
        row.add_row(info_row(_("Homepage"), homepage))
        description = str(info.get("description") or "").strip()
        if description:
            label = Gtk.Label(label=description, xalign=0, wrap=True)
            label.add_css_class("dim-label")
            label.set_margin_top(6)
            label.set_margin_bottom(6)
            label.set_margin_start(12)
            label.set_margin_end(12)
            row.add_row(label)
        packages_count = len(packages)
        package_word = _("1 pacote") if packages_count == 1 else _("{0} pacotes").format(packages_count)
        row.add_row(info_row(
            _("Pacotes"),
            _("{0} construídos neste projeto").format(package_word),
        ))
        for package in packages[:40]:
            item = Adw.ActionRow(title=str(package.get("name") or ""))
            source_type = str(package.get("source_type") or "")
            if source_type:
                item.set_subtitle(source_type)
            row.add_row(item)
        if len(packages) > 40:
            more = Gtk.Label(label=_("… e mais {0} pacotes").format(len(packages) - 40), xalign=0)
            more.add_css_class("dim-label")
            more.set_margin_top(4)
            more.set_margin_bottom(8)
            row.add_row(more)
        row.set_subtitle("{0} · {1} · {2}".format(project, package_word, contact or owner))

    def _repo_row(self, repository: dict, copr: bool) -> Gtk.Widget:
        row = Gtk.Box(spacing=14)
        row.set_margin_top(14)
        row.set_margin_bottom(14)
        row.set_margin_start(16)
        row.set_margin_end(16)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        texts.set_hexpand(True)
        title = Gtk.Label(label=repository["name"], xalign=0, wrap=True)
        title.add_css_class("fs-name")
        texts.append(title)
        identifier = str(repository["id"])
        extra = self.copr_owner_project(identifier)
        sub = Gtk.Label(label=_("{0}").format(extra or identifier), xalign=0, wrap=True)
        sub.add_css_class("dim-label")
        sub.add_css_class("fs-note")
        texts.append(sub)
        row.append(texts)
        if repository.get("is_enabled", False):
            status = Gtk.Label(label="●  " + _("Habilitado"), xalign=0)
            status.add_css_class("fs-status-ok")
            status.set_valign(Gtk.Align.CENTER)
            row.append(status)
        else:
            status = Gtk.Label(label=_("Desabilitado"), xalign=0)
            status.add_css_class("fs-status-off")
            status.set_valign(Gtk.Align.CENTER)
            row.append(status)
            if copr:
                enable = Gtk.Button()
                side = Gtk.Box(spacing=6)
                side.append(Gtk.Label(label=_("Habilitar")))
                side.append(Gtk.Image(icon_name="go-next-symbolic"))
                enable.set_child(side)
                enable.add_css_class("flat")
                enable.add_css_class("fs-linkbtn")
                enable.set_valign(Gtk.Align.CENTER)
                enable.connect("clicked", self._toggle_repo_action, repository, True)
                row.append(enable)
        if copr and repository.get("is_enabled", False):
            disable = Gtk.Button()
            side = Gtk.Box(spacing=6)
            side.append(Gtk.Label(label=_("Desabilitar")))
            disable.set_child(side)
            disable.add_css_class("flat")
            disable.add_css_class("fs-dangerlink")
            disable.set_valign(Gtk.Align.CENTER)
            disable.connect("clicked", self._toggle_repo_action, repository, False)
            row.append(disable)
        return row

    @staticmethod
    def copr_owner_project(identifier: str) -> str:
        parts = identifier.split(":")
        if len(parts) >= 3:
            return "/".join(parts[-2:])
        return ""

    def _toggle_repo_action(self, _button: Gtk.Widget, repository: dict, enable: bool) -> None:
        identifier = str(repository["id"])
        project = self.copr_owner_project(identifier)
        if not project:
            self._toast(_("Apenas repositórios COPR podem ser alternados por aqui."))
            return
        GLib.idle_add(self._run_copr_toggle, project, enable)

    def _run_copr_toggle(self, project: str, enable: bool) -> bool:
        args = ["pkexec", "dnf", "copr", "enable" if enable else "disable", "-y", project]
        self._run_root(args, toast_success=_("Fonte comunitária {0}").format(_("habilitada") if enable else _("desabilitada")),
                       reload_fn="repos")
        return False

    # ---------- Detalhes ----------

    def _kick_detail_info(self, package: Package) -> None:
        self._detail_pending.add(package.name)
        name = package.name

        def worker() -> None:
            rows: list[tuple[str, str, str]] = []
            try:
                rows = repo.info_rows(name)
            except Exception:
                rows = []
            GLib.idle_add(self._detail_loaded, name, rows)

        threading.Thread(target=worker, daemon=True).start()

    def _detail_loaded(self, name: str, rows: list) -> bool:
        self._detail_pending.discard(name)
        if rows:
            self._detail_info[name] = rows
            self._detail_failed.discard(name)
        else:
            self._detail_failed.add(name)
        if self.detail_package is not None and self.detail_package.name == name:
            if rows:
                self._hydrate_from_info(self.detail_package, rows)
            self.render_page()
        return False

    @staticmethod
    def _hydrate_from_info(package: Package, rows: list[tuple[str, str, str]]) -> None:
        if not rows:
            return
        installed_evr = package.installed_version
        if installed_evr is None:
            evr, repo_id, arch = rows[0]
        else:
            evr, repo_id, arch = next((r for r in rows if r[0] != installed_evr), rows[0])
        package.version = evr
        package.repo_id = repo_id
        package.arch = arch
        package.source = repo.repo_label(repo_id)

    def _render_detail(self, body: Gtk.Box) -> None:
        package = self.detail_package
        if not package:
            return
        if not package.installed_version:
            row = self.packages_installed.get(package.name)
            if row:
                package.installed_version = row.get("evr")
        if not package.update_version:
            upgrade_row = next((u for u in self.packages_upgrades if u["name"] == package.name), None)
            if upgrade_row:
                package.update_version = upgrade_row.get("evr")
        cached = self._detail_info.get(package.name)
        if cached and not package.version:
            self._hydrate_from_info(package, cached)
        if not package.version and package.name not in self._detail_pending and package.name not in self._detail_failed:
            self._kick_detail_info(package)
        has_data = bool(package.version or package.installed_version or package.repo_id)
        hero = Gtk.Box(spacing=22)
        hero.set_hexpand(True)
        hero.append(Gtk.Image(icon_name=package.icon, pixel_size=72))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        texts.set_hexpand(True)
        name = Gtk.Label(label=package.name, xalign=0, wrap=True)
        name.add_css_class("fs-heading")
        texts.append(name)
        summary = Gtk.Label(label=package.summary or _("Pacote do repositório {0}").format(package.origin), xalign=0, wrap=True)
        summary.add_css_class("dim-label")
        texts.append(summary)
        origin = Gtk.Box(spacing=8)
        origin.append(self._origin_label(package))
        role = _("Projeto comunitário") if package.source == "COPR" else package.source
        role_label = Gtk.Label(label=role, xalign=0)
        role_label.add_css_class("dim-label")
        origin.append(role_label)
        texts.append(origin)
        hero.append(texts)
        op = self._operation(package)
        action = Gtk.Button(label=op)
        if op == _("Remover"):
            action.add_css_class("fs-dangerbtn")
        else:
            action.add_css_class("suggested-action")
            action.add_css_class("fs-bold")
            action.add_css_class("fs-pillbtn")
        action.set_valign(Gtk.Align.CENTER)
        action.connect("clicked", self._package_action, package)
        hero.append(action)
        body.append(hero)

        if not has_data:
            if package.name in self._detail_failed:
                body.append(self._state_card(
                    _("Informações indisponíveis"),
                    _("O DNF não retornou dados para {0}. Tente novamente mais tarde.").format(package.name),
                    icon="dialog-information-symbolic",
                ))
            else:
                body.append(self._state_card(
                    _("Consultando o DNF"),
                    _("Buscando informações de {0}…").format(package.name),
                    spinner=True,
                ))
            return

        if package.source == "COPR":
            banner = Gtk.Box(spacing=10)
            banner.add_css_class("card")
            banner.add_css_class("fs-banner")
            banner_icon = Gtk.Image(icon_name="dialog-information-symbolic")
            banner_icon.add_css_class("fs-banner-title")
            banner.append(banner_icon)
            banner_texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            banner_title = Gtk.Label(label=_("Fonte comunitária COPR"), xalign=0)
            banner_title.add_css_class("fs-banner-title")
            banner_texts.append(banner_title)
            maintainer = self.copr_owner_project(package.repo_id) or "a comunidade"
            description = Gtk.Label(label=_("Este pacote é mantido por {0}. Confira o projeto antes de instalar.").format(maintainer), xalign=0, wrap=True)
            description.add_css_class("fs-banner-body")
            banner_texts.append(description)
            banner.append(banner_texts)
            body.append(banner)

        about_heading = Gtk.Label(label=_("Sobre"), xalign=0)
        about_heading.add_css_class("fs-page-title")
        body.append(about_heading)
        about = Gtk.Label(label=package.summary or _("Sem descrição mestre; veja “dnf info {0}” para detalhes.").format(package.name), xalign=0, wrap=True)
        about.set_hexpand(True)
        body.append(about)

        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(12)
        info_grid.set_column_spacing(40)
        info_grid.set_margin_top(18)
        info_grid.set_margin_bottom(18)
        info_grid.set_margin_start(20)
        info_grid.set_margin_end(20)
        rows = [
            (_("Versão instalada"), package.installed_version or _("Não instalado")),
            (_("Versão disponível"), package.update_version or package.version or _("—")),
            (_("Repositório"), package.repo_id or package.origin),
        ]
        if package.arch:
            rows.append((_("Arquitetura"), package.arch))
        for index, (label, value) in enumerate(rows):
            key = Gtk.Label(label=label, xalign=0)
            key.add_css_class("fs-note")
            info_grid.attach(key, 0, index, 1, 1)
            value_label = Gtk.Label(label=value, xalign=0, wrap=True)
            value_label.add_css_class("fs-note")
            info_grid.attach(value_label, 1, index, 1, 1)
        info = Gtk.Box()
        info.add_css_class("card")
        info.append(info_grid)
        body.append(info)

    # ---------- Aplicação real ----------

    def _apply(self, packages: list[Package]) -> None:
        if not packages or self.busy:
            return
        self.busy = True
        self.selected.clear()
        commands: list[list[str]] = []
        # dnf5's ``install`` is a no-op on already-installed packages, so
        # updates must go through ``upgrade`` (verified: install → "Nada
        # para fazer", upgrade → transaction planned).
        upgrades = [p.name for p in packages if p.updatable]
        installs = [p.name for p in packages if not p.installed and not p.updatable]
        removes = [p.name for p in packages if p.installed and not p.updatable]
        if upgrades:
            commands.append(["pkexec", "dnf", "upgrade", "-y", *upgrades])
        if installs:
            commands.append(["pkexec", "dnf", "install", "-y", *installs])
        if removes:
            commands.append(["pkexec", "dnf", "remove", "-y", *removes])
        ops = {self._operation(p) for p in packages}
        if ops == {_("Atualizar")}:
            self._busy_summary = _("Atualização")
        elif ops == {_("Instalar")}:
            self._busy_summary = _("Instalação")
        elif ops == {_("Remover")}:
            self._busy_summary = _("Remoção")
        else:
            self._busy_summary = ""
        self._show_progress(packages)
        self._busy_worker(commands)

    def _refresh_background(self, then_idle) -> None:
        def worker():
            try:
                installed_rows = repo.installed()
                upgrade_rows = repo.upgrades()
                repos_rows = repo.repos()
            except Exception:
                installed_rows, upgrade_rows, repos_rows = self._rows_snapshot()
            GLib.idle_add(then_idle, installed_rows, upgrade_rows, repos_rows)

        threading.Thread(target=worker, daemon=True).start()

    def _rows_snapshot(self) -> tuple[list, list, list]:
        return (list(self.packages_installed.values()), list(self.packages_upgrades), list(self.repos))

    def _busy_worker(self, commands: list[list[str]]) -> None:
        def worker():
            errors: list[str] = []
            for command in commands:
                try:
                    result = repo.subprocess_(command, timeout=1800)
                    if result.returncode == 126:
                        errors.append("__auth_cancelled__")
                        break
                    if result.returncode == 127:
                        errors.append("__auth_failed__")
                        break
                    if result.returncode != 0:
                        tail = (result.stderr or result.stdout).strip().splitlines()[-1] if (result.stderr or result.stdout) else ""
                        if tail:
                            errors.append(tail)
                except Exception as error:
                    errors.append(str(error)[:160])
            self._refresh_background(lambda *snap: self._finish_busy(errors, *snap))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_busy(self, errors: list[str], installed_rows, upgrade_rows, repos_rows) -> bool:
        self.busy = False
        summary = self._busy_summary
        self._busy_summary = ""
        if installed_rows or not self.packages_installed:
            self.packages_installed = {row["name"]: row for row in installed_rows}
        if upgrade_rows or not self.packages_upgrades:
            self.packages_upgrades = list(upgrade_rows)
        if repos_rows or not self.repos:
            self.repos = list(repos_rows)
        self.selected.clear()
        self.detail_package = None
        self._update_badge()
        self.render_page()
        if errors:
            if errors[0] == "__auth_cancelled__":
                self._toast(_("Autenticação cancelada — nada foi alterado"))
            elif errors[0] == "__auth_failed__":
                self._toast(_("Falha de autenticação — nada foi alterado"))
            else:
                self._toast(_("A operação falhou: {0}").format(errors[0][:130]))
        elif summary:
            self._toast(_("{0} concluída com sucesso").format(summary))
        else:
            self._toast(_("Concluído com sucesso"))
        return False

    def _show_progress(self, packages: list[Package]) -> None:
        if not self.main_box:
            return
        self._clear(self.main_box)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        title_label = Gtk.Label(label=HEADER_TITLES[self.page])
        title_label.add_css_class("fs-header-title")
        header.set_title_widget(title_label)
        view.add_top_bar(header)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_halign(Gtk.Align.CENTER)
        body.set_valign(Gtk.Align.CENTER)
        body.set_vexpand(True)
        removing = all(self._operation(p) == _("Remover") for p in packages)
        heading_text = _("Removendo aplicativos") if removing else _("Aplicando alterações com o DNF")
        heading = Gtk.Label(label=heading_text, xalign=0.5)
        heading.add_css_class("fs-name")
        body.append(heading)
        sub = Gtk.Label(label=_("{0} pacotes. O polkit pode pedir sua senha…").format(len(packages)), xalign=0.5)
        sub.add_css_class("dim-label")
        body.append(sub)
        progress = Gtk.ProgressBar()
        progress.set_size_request(440, -1)
        progress.add_css_class("fs-progress")
        progress.set_pulse_step(0.12)
        body.append(progress)
        view.set_content(body)
        self.main_box.append(view)

        def pulse():
            progress.pulse()
            return self.busy

        GLib.timeout_add(220, pulse)

    def _run_root(self, args: list[str], toast_success: str, reload_fn: str) -> None:
        def worker():
            errors: list[str] = []
            try:
                result = repo.subprocess_(args, timeout=900)
                if result.returncode != 0:
                    tail = (result.stderr or result.stdout or "").strip().splitlines()[-1:]
                    errors = tail if tail else [f"exit {result.returncode}"]
            except Exception as error:
                errors.append(str(error)[:160])
            GLib.idle_add(self._finish_root, errors, toast_success, reload_fn)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_root(self, errors: list[str], toast_success: str, reload_fn: str) -> bool:
        if errors:
            self._toast(_("A operação falhou: {0}").format(errors[0][:130]))
        else:
            self._toast(toast_success)
        if reload_fn == "repos":
            self._load_initial()
        return False

    def _toast(self, message: str) -> None:
        if self.toast_overlay:
            self.toast_overlay.add_toast(Adw.Toast.new(message))

    def _register_actions(self) -> None:
        if not self.window:
            return
        open_detail = Gio.SimpleAction.new("open-detail", GLib.VariantType.new("s"))
        open_detail.connect("activate", self._act_open_detail)
        self.window.add_action(open_detail)
        toggle_select = Gio.SimpleAction.new("toggle-select", GLib.VariantType.new("s"))
        toggle_select.connect("activate", self._act_toggle_select)
        self.window.add_action(toggle_select)

    def _act_open_detail(self, _action: Gio.SimpleAction, variant: GLib.Variant) -> None:
        name = variant.unpack()
        package = self._pkg(name)
        if package:
            self.detail_package = package
            self.render_page()

    def _act_toggle_select(self, _action: Gio.SimpleAction, variant: GLib.Variant) -> None:
        name = variant.unpack()
        if name in self.selected:
            self.selected.discard(name)
        else:
            self.selected.add(name)
        self.render_page()


def main() -> None:
    app = FedoraStore()
    raise SystemExit(app.run(sys.argv))