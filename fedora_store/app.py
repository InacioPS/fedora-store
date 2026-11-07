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
from datetime import datetime
import json
import os
import shlex
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

LOGO_PATH = Path(__file__).with_name("assets") / "fedora-store-logo.png"
TRAY_ICON_NAME = "io.github.fedorastore.FedoraStore"
TRAY_OBJECT_PATH = "/StatusNotifierItem"
TRAY_MENU_PATH = "/StatusNotifierMenu"
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, Gtk, Pango  # noqa: E402

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
    ("local", _("RPM local"), "package-x-generic-symbolic"),
]

HEADER_TITLES = {
    "explore": _("Catálogo de aplicativos"),
    "installed": _("Instalados"),
    "updates": _("Atualizações"),
    "copr": _("COPR"),
    "sources": _("Fontes"),
    "settings": _("Configurações"),
    "local": _("RPM local"),
}

CHIP_SOURCES = [
    ("Todos", None),
    ("DNF", "Fedora"),
    ("Terra", "Terra"),
    ("COPR", "COPR"),
    ("Flatpak", "Flatpak"),
]

SOURCES_DROPDOWN = ["Todas", "Fedora", "Terra", "COPR"]

STYLE = b"""
.fs-header-title { font-weight: 700; font-size: 16px; }
.fs-topbar { border-bottom: 1px solid rgba(0, 0, 0, 0.07); }
.fs-sidebar { border-right: 1px solid rgba(0, 0, 0, 0.07); }
.fs-sidebar-btn { min-width: 42px; min-height: 42px; padding: 0; }
.fs-subnav { padding: 8px 24px 8px; border-bottom: 1px solid rgba(0, 0, 0, 0.07); }
.fs-navbtn { font-weight: 600; border-width: 0px; background: none; color: #4A5158; padding: 5px 12px; min-height: 30px; border-radius: 999px; }
.fs-navbtn:hover:not(:checked) { background: rgba(0, 0, 0, 0.06); }
.fs-navbtn:checked { background: #D5E5FA; color: #205A9F; font-weight: 700; }
.fs-heading { font-size: 32px; font-weight: 800; }
.fs-page-title { font-size: 21px; font-weight: 700; }
.fs-name { font-weight: 700; font-size: 17px; }
.fs-search { min-height: 32px; padding: 0 10px; font-size: 15px; }
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
.fs-package-action { min-width: 96px; }
.fs-linkbtn { background: none; border-width: 0px; color: #2769B4; font-weight: 700; min-height: 32px; padding: 0 10px; border-radius: 8px; }
.fs-linkbtn:hover { background: rgba(0, 0, 0, 0.05); }
.fs-kicker { font-size: 12px; font-weight: 700; color: #70777C; }
.fs-origin { font-size: 12px; font-weight: 700; }
.fs-origin-dnf { color: #577087; }
.fs-origin-terra { color: #577087; }
.fs-origin-copr { color: #8A6A3C; }
.fs-origin-flatpak { color: #2F7DB2; }
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
.fs-copr-table { border-radius: 12px; }
.fs-copr-table-header { min-height: 36px; }
.fs-copr-table-header-label { font-size: 12px; font-weight: 700; color: #7D858C; }
.fs-copr-table-row { min-height: 44px; }
.fs-copr-package { font-weight: 700; font-size: 15px; }
.fs-copr-value { font-size: 14px; }
.fs-copr-status { padding: 0; font-size: 12px; font-weight: 700; }
.fs-copr-status-ok { background: none; color: #319268; }
.fs-copr-status-failed { background: none; color: #C9504C; }
.fs-copr-status-running { background: none; color: #B88940; }
.fs-rpm-drop { padding: 28px 20px; }
.fs-rpm-install { min-width: 84px; min-height: 30px; padding: 0 10px; }
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
    def __init__(self, *, background: bool = False) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self._background_start = background
        self._notification_sent = False
        self._indicator = None
        self._background_hold = False
        self.connect("activate", self.on_activate)
        self.page = "explore"
        self.detail_package: Package | None = None
        self._detail_packages: dict[str, Package] = {}
        self.safe = False
        self.busy = False
        self._busy_summary = ""
        self.query = ""
        self.filter_source = "Todos"
        self.view_mode = "grid"
        self.sort_mode = 0
        self.query_installed = ""
        self.installed_source = 0
        self.query_updates = ""
        self.query_sources = ""
        self.copr_query = ""
        self.selected: set[str] = set()
        self.window: Adw.ApplicationWindow | None = None
        self.toast_overlay: Adw.ToastOverlay | None = None
        self.main_box: Gtk.Box | None = None
        self.sidebar_rows: dict[str, Gtk.ToggleButton] = {}
        self.updates_badge: Gtk.Label | None = None
        self._topbar_search: Gtk.SearchEntry | None = None
        self._topnav_subnav: Gtk.Box | None = None
        self._topnav_labels: list[tuple[Gtk.Label, Gtk.Label | None]] = []
        self._topnav: Gtk.Box | None = None
        self._root: Gtk.Box | None = None

        self.packages_installed: dict[str, dict] = {}
        self.packages_upgrades: list[dict] = []
        self.packages_featured: list[dict] = []
        self._featured_view_key: tuple[str, int] | None = None
        self._featured_view_rows: list[dict] = []
        self.featured_visible = 48
        self.featured_loading_more = False
        self._catalog_scroller: Gtk.ScrolledWindow | None = None
        self._catalog_scroll_y = 0.0
        self.flatpak_rows: list[dict] = []
        self.flatpak_installed: dict[str, dict] = {}
        self._flatpak_icon_cache: dict[str, Gdk.Texture] = {}
        self._flatpak_icon_widgets: dict[str, list[Gtk.Image]] = {}
        self._flatpak_icon_pending: set[str] = set()
        self.flatpak_ready = False
        self.flatpak_loading = False
        self.flatpak_search_rows: list[dict] | None = None
        self.flatpak_search_query = ""
        self.flatpak_search_loading = False
        self.flatpak_search_token = 0
        self._source_settings_path = Path(GLib.get_user_config_dir()) / "fedora-store" / "sources.json"
        self.third_party_sources = self._load_source_preferences()
        self.navigation_mode = self.third_party_sources.get("navigation", "topnav")
        self.repos: list[dict] = []
        self.local_rpm: dict[str, str] | None = None
        self.local_rpm_detail = False
        self.local_rpm_loading = False
        self.ready = False
        self._core_loading = False
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
        self.copr_projects_token = 0
        self.copr_projects_pending = False
        self.copr_projects_data: list[dict] | None = None
        self.copr_projects_failed = False
        self.copr_package_project: tuple[str, str, str] | None = None
        self._copr_project_packages: dict[str, list[dict]] = {}
        self._copr_project_packages_loading: set[str] = set()
        self._copr_project_packages_failed: set[str] = set()
        self._copr_expanded: dict[str, dict] = {}
        self._copr_loading: set[str] = set()
        self._copr_rows: dict[str, Adw.ExpanderRow] = {}

    def _load_source_preferences(self) -> dict[str, bool | str]:
        defaults = {
            "flatpak": False,
            "terra": False,
            "copr": False,
            "tray": False,
            "autostart": False,
            "navigation": "topnav",
        }
        try:
            loaded = json.loads(self._source_settings_path.read_text())
        except (OSError, ValueError):
            return defaults
        if not isinstance(loaded, dict):
            return defaults
        preferences = {}
        for key, value in defaults.items():
            if key == "navigation":
                selected = loaded.get(key, value)
                preferences[key] = selected if selected in ("topnav", "sidebar") else value
            else:
                preferences[key] = bool(loaded.get(key, value))
        return preferences

    @property
    def _autostart_path(self) -> Path:
        return Path(GLib.get_user_config_dir()) / "autostart" / "fedora-store.desktop"

    def _set_autostart(self, enabled: bool) -> None:
        path = self._autostart_path
        if not enabled:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                self._toast(_("Não foi possível remover a inicialização automática."))
            return
        command = shlex.join([sys.executable, "-m", "fedora_store", "--background"])
        content = "\n".join((
            "[Desktop Entry]",
            "Type=Application",
            "Name=Aplicativos",
            f"Exec={command}",
            f"Icon={LOGO_PATH}",
            "X-GNOME-Autostart-enabled=true",
            "",
        ))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        except OSError:
            self._toast(_("Não foi possível configurar a inicialização automática."))

    def _set_background_hold(self, enabled: bool) -> None:
        if enabled and not self._background_hold:
            self.hold()
            self._background_hold = True
        elif not enabled and self._background_hold:
            self.release()
            self._background_hold = False

    def _install_tray_icon(self) -> Path:
        icon_path = Path(GLib.get_user_data_dir()) / "icons" / "hicolor" / "64x64" / "apps" / f"{TRAY_ICON_NAME}.png"
        icon_path.parent.mkdir(parents=True, exist_ok=True)
        if not icon_path.exists() or icon_path.stat().st_mtime < LOGO_PATH.stat().st_mtime:
            image = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(LOGO_PATH), 64, 64, True)
            image.savev(str(icon_path), "png", [], [])
        return icon_path

    def _tray_method_call(self, _connection, _sender, _path, _interface, method, _parameters, invocation) -> None:
        if method in ("Activate", "SecondaryActivate") and self.window:
            self.window.present()
        invocation.return_value(GLib.Variant("()", ()))

    def _tray_menu_item(self, item_id: int, label: str | None = None) -> GLib.Variant:
        attributes = {
            "visible": GLib.Variant("b", True),
            "enabled": GLib.Variant("b", True),
        }
        if label is None:
            attributes["type"] = GLib.Variant("s", "separator")
        else:
            attributes["label"] = GLib.Variant("s", label)
        return GLib.Variant("(ia{sv}av)", (item_id, attributes, []))

    def _tray_menu_layout(self) -> GLib.Variant:
        children = [
            GLib.Variant("v", self._tray_menu_item(1, _("Abrir"))),
            GLib.Variant("v", self._tray_menu_item(2, _("Atualizar sistema"))),
            GLib.Variant("v", self._tray_menu_item(3)),
            GLib.Variant("v", self._tray_menu_item(4, _("Fechar aplicativo"))),
        ]
        root = GLib.Variant(
            "(ia{sv}av)",
            (0, {"children-display": GLib.Variant("s", "submenu")}, children),
        )
        return GLib.Variant.new_tuple(GLib.Variant("u", 1), root)

    def _tray_menu_method_call(self, _connection, _sender, _path, _interface, method, parameters, invocation) -> None:
        if method == "GetLayout":
            invocation.return_value(self._tray_menu_layout())
            return
        if method == "AboutToShow":
            invocation.return_value(GLib.Variant("(b)", (False,)))
            return
        if method == "Event":
            item_id, event, _data, _timestamp = parameters.unpack()
            if event == "clicked":
                GLib.idle_add(self._run_tray_action, item_id)
            invocation.return_value(GLib.Variant("()", ()))

    def _run_tray_action(self, item_id: int) -> bool:
        if item_id == 1 and self.window:
            self.window.present()
        elif item_id == 2:
            if self.window:
                self.window.present()
            self._update_all()
        elif item_id == 4:
            self._set_tray(False)
            if self.window:
                self.window.destroy()
            self.quit()
        return False

    def _tray_get_property(self, _connection, _sender, _path, _interface, name: str) -> GLib.Variant | None:
        values = {
            "Category": GLib.Variant("s", "ApplicationStatus"),
            "Id": GLib.Variant("s", APP_ID),
            "Title": GLib.Variant("s", _("Aplicativos")),
            "Status": GLib.Variant("s", "Active"),
            "IconName": GLib.Variant("s", TRAY_ICON_NAME),
            "IconThemePath": GLib.Variant("s", str(Path(GLib.get_user_data_dir()) / "icons")),
            "ItemIsMenu": GLib.Variant("b", False),
            "Menu": GLib.Variant("o", TRAY_MENU_PATH),
        }
        return values.get(name)

    @staticmethod
    def _tray_menu_get_property(_connection, _sender, _path, _interface, name: str) -> GLib.Variant | None:
        values = {
            "Version": GLib.Variant("u", 4),
            "TextDirection": GLib.Variant("s", "ltr"),
            "Status": GLib.Variant("s", "normal"),
            "IconThemePath": GLib.Variant("as", []),
        }
        return values.get(name)

    def _set_tray(self, enabled: bool) -> bool:
        if not enabled:
            if self._indicator is not None:
                connection, registration, menu_registration = self._indicator
                connection.unregister_object(registration)
                connection.unregister_object(menu_registration)
                self._indicator = None
            self._set_background_hold(False)
            return True
        if self._indicator is not None:
            self._set_background_hold(True)
            return True
        try:
            self._install_tray_icon()
            connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            node = Gio.DBusNodeInfo.new_for_xml(
                "<node><interface name='org.kde.StatusNotifierItem'>"
                "<method name='Activate'><arg type='i' direction='in'/><arg type='i' direction='in'/></method>"
                "<method name='SecondaryActivate'><arg type='i' direction='in'/><arg type='i' direction='in'/></method>"
                "<method name='ContextMenu'><arg type='i' direction='in'/><arg type='i' direction='in'/></method>"
                "<property name='Category' type='s' access='read'/><property name='Id' type='s' access='read'/>"
                "<property name='Title' type='s' access='read'/><property name='Status' type='s' access='read'/>"
                "<property name='IconName' type='s' access='read'/><property name='IconThemePath' type='s' access='read'/>"
                "<property name='ItemIsMenu' type='b' access='read'/><property name='Menu' type='o' access='read'/></interface></node>"
            )
            registration = connection.register_object(
                TRAY_OBJECT_PATH, node.interfaces[0], self._tray_method_call, self._tray_get_property, None,
            )
            menu_node = Gio.DBusNodeInfo.new_for_xml(
                "<node><interface name='com.canonical.dbusmenu'>"
                "<method name='GetLayout'><arg type='i' direction='in'/><arg type='i' direction='in'/><arg type='as' direction='in'/><arg type='u' direction='out'/><arg type='(ia{sv}av)' direction='out'/></method>"
                "<method name='Event'><arg type='i' direction='in'/><arg type='s' direction='in'/><arg type='v' direction='in'/><arg type='u' direction='in'/></method>"
                "<method name='AboutToShow'><arg type='i' direction='in'/><arg type='b' direction='out'/></method>"
                "<property name='Version' type='u' access='read'/><property name='TextDirection' type='s' access='read'/>"
                "<property name='Status' type='s' access='read'/><property name='IconThemePath' type='as' access='read'/>"
                "</interface></node>"
            )
            menu_registration = connection.register_object(
                TRAY_MENU_PATH, menu_node.interfaces[0], self._tray_menu_method_call, self._tray_menu_get_property, None,
            )
            connection.call(
                "org.kde.StatusNotifierWatcher", "/StatusNotifierWatcher",
                "org.kde.StatusNotifierWatcher", "RegisterStatusNotifierItem",
                GLib.Variant("(s)", (APP_ID,)), None, Gio.DBusCallFlags.NONE, -1, None, None, None,
            )
            self._indicator = (connection, registration, menu_registration)
            self._set_background_hold(True)
            return True
        except Exception:
            self._toast(_("Não foi possível criar o ícone na bandeja."))
            return False

    def _background_switch_state(self, switch: Gtk.Switch, state: bool, key: str) -> bool:
        if state == self.third_party_sources[key]:
            return True
        if key == "tray":
            if not self._set_tray(state):
                switch.set_active(False)
                return True
            if not state and self.third_party_sources["autostart"]:
                self.third_party_sources["autostart"] = False
                self._set_autostart(False)
        elif state and not self.third_party_sources["tray"]:
            if not self._set_tray(True):
                switch.set_active(False)
                return True
            self.third_party_sources["tray"] = True
        self.third_party_sources[key] = state
        self._save_source_preferences()
        if key == "autostart":
            self._set_autostart(state)
        switch.set_active(state)
        if self.page == "settings":
            self.render_page()
        return True

    def _save_source_preferences(self) -> None:
        try:
            self._source_settings_path.parent.mkdir(parents=True, exist_ok=True)
            self._source_settings_path.write_text(json.dumps(self.third_party_sources))
        except OSError:
            self._toast(_("Não foi possível salvar as preferências de fontes."))

    # ---------- boot ----------

    def on_activate(self, _app: Adw.Application) -> None:
        if self.window:
            self.window.present()
            self._load_initial()
            return
        self.window = Adw.ApplicationWindow(application=self, title=_("Aplicativos"))
        self.window.connect("close-request", self._close_requested)
        self.window.set_default_size(1440, 900)
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)
        self.toast_overlay = Adw.ToastOverlay()
        self.window.set_content(self.toast_overlay)

        provider = Gtk.CssProvider()
        provider.load_from_data(STYLE)
        display = self.window.get_display()
        Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root = root
        self.toast_overlay.set_child(root)
        self._build_shell(root)
        self.window.connect("notify::width", self._update_responsive_topbar)

        self._register_actions()
        self.render_page()
        self._update_responsive_topbar()
        self.window.present()
        if self.third_party_sources["tray"]:
            self._set_tray(True)
        if self._background_start and self.third_party_sources["tray"]:
            self.window.hide()
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
        if self._core_loading:
            return
        self._core_loading = True

        def core_worker():
            refresh_error = ""
            try:
                installed_rows = repo.installed()
                try:
                    upgrade_rows = repo.refresh_upgrades()
                except Exception as error:
                    refresh_error = str(error)
                    upgrade_rows = repo.upgrades()
                repos_rows = repo.repos()
                GLib.idle_add(self._apply_core, installed_rows, upgrade_rows, repos_rows, refresh_error)
            except Exception as error:
                GLib.idle_add(self._core_failed, error)

        def featured_worker():
            try:
                rows = repo.available_all()
            except Exception:
                rows = []
            results = repo.fancy_app_filter(rows, limit=None) if rows else []
            GLib.idle_add(self._apply_featured, results)

        threading.Thread(target=core_worker, daemon=True).start()
        threading.Thread(target=featured_worker, daemon=True).start()

    def _apply_core(self, installed_rows, upgrade_rows, repos_rows, refresh_error: str = "") -> bool:
        self._core_loading = False
        if installed_rows or not self.packages_installed:
            self.packages_installed = {row["name"]: row for row in installed_rows}
        if upgrade_rows or not self.packages_upgrades:
            self.packages_upgrades = list(upgrade_rows)
        if repos_rows or not self.repos:
            self.repos = list(repos_rows)
        self._featured_view_key = None
        self._featured_view_rows = []
        self.ready = True
        self._update_badge()
        self.render_page()
        if self._background_start and self.packages_upgrades and not self._notification_sent:
            count = len(self.packages_upgrades)
            notification = Gio.Notification.new(_("Atualizações disponíveis"))
            notification.set_body(
                _("Há 1 atualização disponível.") if count == 1
                else _("{0} atualizações estão disponíveis.").format(count)
            )
            notification.set_default_action("app.activate")
            self.send_notification("updates-available", notification)
            self._notification_sent = True
        if refresh_error:
            self._toast(_("Não foi possível verificar atualizações novas; exibindo o cache do DNF."))
        return False

    def _core_failed(self, error) -> bool:
        self._core_loading = False
        self.ready = True
        self._update_badge()
        self.render_page()
        self._toast(_("Não foi possível ler o DNF: {0}").format(str(error)[:120]))
        return False

    def _apply_featured(self, results) -> bool:
        self.packages_featured = results
        self._featured_view_key = None
        self._featured_view_rows = []
        self.featured_visible = 48
        self.featured_loading_more = False
        self.featured_ready = True
        if self.page == "explore" and not self.detail_package:
            self.render_page()
        return False

    def _load_flatpak_catalog(self) -> None:
        if self.flatpak_loading or self.flatpak_ready:
            return
        self.flatpak_loading = True

        def worker() -> None:
            try:
                rows = repo.flathub_catalog()
                installed = repo.flatpak_installed()
            except Exception:
                rows, installed = [], {}
            GLib.idle_add(self._finish_flatpak_catalog, rows, installed)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_flatpak_catalog(self, rows: list[dict], installed: dict[str, dict]) -> bool:
        self.flatpak_rows = rows
        self.flatpak_installed = installed
        self.flatpak_loading = False
        self.flatpak_ready = True
        if self.page == "explore" and self.filter_source == "Flatpak":
            self.render_page()
        return False

    def _begin_flatpak_search(self, query: str) -> None:
        """Search the complete Flathub AppStream index off the GTK thread."""
        self.flatpak_search_token += 1
        token = self.flatpak_search_token
        self.flatpak_search_query = query.casefold()
        self.flatpak_search_rows = None
        self.flatpak_search_loading = True
        self.render_page()

        def worker() -> None:
            try:
                rows = repo.flathub_search(query)
            except Exception:
                rows = []
            GLib.idle_add(self._finish_flatpak_search, token, rows)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_flatpak_search(self, token: int, rows: list[dict]) -> bool:
        if token != self.flatpak_search_token:
            return False
        self.flatpak_search_rows = rows
        self.flatpak_search_loading = False
        if self.page == "explore" and self.filter_source == "Flatpak":
            self.render_page()
        return False

    def _update_badge(self) -> None:
        count = self._updates_count()
        if self.updates_badge:
            self.updates_badge.set_text(str(count))
            self.updates_badge.set_visible(count > 0 and not self._topbar_compact)

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

    # ---------- Navigation ----------

    def _build_shell(self, root: Gtk.Box) -> None:
        if self.navigation_mode == "sidebar":
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
            content.set_hexpand(True)
            content.set_vexpand(True)
            root.append(content)
            self._build_sidebar(content)
            host = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            host.set_hexpand(True)
            host.set_vexpand(True)
            header = Gtk.Box()
            header.set_margin_top(8)
            header.set_margin_start(16)
            header.set_margin_end(16)
            spacer = Gtk.Box()
            spacer.set_hexpand(True)
            header.append(spacer)
            header.append(self._close_button())
            host.append(header)
            content.append(host)
        else:
            self._build_topnav(root)
            host = root
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.set_hexpand(True)
        self.main_box.set_vexpand(True)
        host.append(self.main_box)
        self._build_footer(root)

    def _navigation_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        menu.append(_("Navegação superior"), "app.navigation-topnav")
        menu.append(_("Barra lateral"), "app.navigation-sidebar")
        return menu

    def _logo_button(self) -> Gtk.MenuButton:
        logo = Gtk.Image.new_from_file(str(LOGO_PATH))
        logo.set_pixel_size(30)
        button = Gtk.MenuButton(menu_model=self._navigation_menu())
        button.set_child(logo)
        button.add_css_class("flat")
        button.set_tooltip_text(_("Escolher estilo de navegação"))
        return button

    def _close_button(self) -> Gtk.Button:
        close = Gtk.Button(icon_name="window-close-symbolic")
        close.add_css_class("flat")
        close.set_tooltip_text(_("Fechar aplicativo"))
        close.connect("clicked", self._close_window)
        return close

    def _settings_button(self) -> Gtk.Button:
        settings = Gtk.Button(icon_name="emblem-system-symbolic")
        settings.add_css_class("flat")
        settings.set_tooltip_text(_("Configurações"))
        settings.connect("clicked", lambda *_args: self.navigate("settings"))
        return settings

    def _build_footer(self, root: Gtk.Box) -> None:
        footer = Gtk.Box()
        footer.set_margin_start(16)
        footer.set_margin_end(16)
        footer.set_margin_bottom(8)
        footer.append(self._settings_button())
        root.append(footer)

    def _build_sidebar(self, root: Gtk.Box) -> None:
        self._topbar_tools = Gtk.Box(spacing=6)
        rail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        rail.add_css_class("fs-sidebar")
        rail.set_size_request(72, -1)
        rail.set_margin_top(12)
        rail.set_margin_bottom(12)
        rail.set_margin_start(10)
        rail.set_margin_end(10)
        rail.append(self._logo_button())
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        rail.append(separator)
        self._topnav_labels.clear()
        self.sidebar_rows.clear()
        first: Gtk.ToggleButton | None = None
        for key, label, icon_name in SIDEBAR_ITEMS:
            button = Gtk.ToggleButton()
            button.set_name(key)
            button.set_tooltip_text(label)
            button.set_icon_name(icon_name)
            button.add_css_class("fs-navbtn")
            button.add_css_class("fs-sidebar-btn")
            if first:
                button.set_group(first)
            else:
                first = button
            button.connect("clicked", self._nav_clicked, key)
            if key == "copr":
                button.set_visible(bool(self.third_party_sources["copr"]))
            rail.append(button)
            self.sidebar_rows[key] = button
        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        rail.append(spacer)
        root.append(rail)
        self._select_sidebar_row()

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
        brand.set_tooltip_text(_("Aplicativos"))
        brand.append(self._logo_button())
        topbar.set_start_widget(brand)

        nav = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self._topnav = nav
        topbar.set_center_widget(nav)
        self._topnav_labels.clear()
        first: Gtk.ToggleButton | None = None
        for key, label, ic in SIDEBAR_ITEMS:
            btn = Gtk.ToggleButton()
            btn.set_name(key)
            btn.set_tooltip_text(label)
            content = Gtk.Box(spacing=8)
            content.append(Gtk.Image(
                icon_name=ic if self._icon_available(ic) else "application-x-executable-symbolic",
                pixel_size=16))
            label_widget = Gtk.Label(label=label)
            content.append(label_widget)
            badge: Gtk.Label | None = None
            if key == "updates":
                badge = Gtk.Label(label=str(self._updates_count()))
                badge.add_css_class("dim-label")
                badge.set_visible(self._updates_count() > 0)
                content.append(badge)
                self.updates_badge = badge
            self._topnav_labels.append((label_widget, badge))
            btn.set_child(content)
            btn.add_css_class("fs-navbtn")
            if first:
                btn.set_group(first)
            else:
                first = btn
            btn.connect("clicked", self._nav_clicked, key)
            if key == "copr":
                btn.set_visible(self.third_party_sources["copr"])
            nav.append(btn)
            self.sidebar_rows[key] = btn

        self._topbar_tools = Gtk.Box(spacing=6)
        self._topbar_tools.set_halign(Gtk.Align.END)
        topbar.set_end_widget(self._topbar_tools)
        self._refresh_topbar_search()
        self._select_sidebar_row()

    def _update_responsive_topbar(self, *_args: object) -> bool:
        if not self.window:
            return False
        width = self.window.get_width()
        compact = width < 1100
        very_compact = width < 860
        self._topbar_compact = compact
        for label, badge in self._topnav_labels:
            label.set_visible(not compact)
            if badge:
                badge.set_visible(not compact and self._updates_count() > 0)
        if self._topnav:
            self._topnav.set_spacing(3 if compact else 6)
        if self._topbar_tools:
            self._topbar_tools.set_spacing(3 if compact else 6)
        if self._topbar_search:
            self._topbar_search.set_width_chars(16 if very_compact else 22 if compact else 30)
        return False

    def _refresh_topbar_search(self) -> None:
        if self._topbar_search:
            search_parent = self._topbar_search.get_parent()
            if search_parent:
                search_parent.remove(self._topbar_search)
        self._clear(self._topbar_tools)
        self._search_entries.clear()
        self._topbar_search = None
        search_config = {
            "explore": (_("Buscar pacotes nos repositórios"), "query"),
            "installed": (_("Buscar aplicativos instalados"), "query_installed"),
            "updates": (_("Buscar atualizações"), "query_updates"),
            "copr": (_("Buscar projetos COPR na API"), "copr_query"),
            "sources": (_("Buscar fontes de aplicativos"), "query_sources"),
        }.get(self.page)
        if search_config:
            placeholder, attr = search_config
            search = self._search_entry(placeholder, attr)
            search.add_css_class("fs-topbar-search")
            search.set_width_chars(24)
            self._topbar_search = search

        self._topbar_tools.append(self._close_button())
        self._update_responsive_topbar()

    def _close_window(self, *_args: object) -> None:
        if self.window:
            self.window.close()

    def _close_requested(self, _window: Adw.ApplicationWindow) -> bool:
        if not self.third_party_sources["tray"]:
            return False
        self._set_tray(True)
        self.window.hide()
        return True

    def _set_navigation_mode(
        self, _action: Gio.SimpleAction, _parameter: GLib.Variant | None, mode: str
    ) -> None:
        if mode == self.navigation_mode:
            return
        self.navigation_mode = mode
        self.third_party_sources["navigation"] = mode
        self._save_source_preferences()
        if not self.toast_overlay:
            return
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._root = root
        self.toast_overlay.set_child(root)
        self._build_shell(root)
        self._update_responsive_topbar()
        self.render_page()

    def _source_switch_state(self, switch: Gtk.Switch, state: bool, key: str) -> bool:
        if state == self.third_party_sources[key]:
            return True
        if not state or key == "copr":
            self._set_source_preference(key, state)
            switch.set_active(state)
            return True
        switch.set_sensitive(False)
        if key == "flatpak":
            args = [
                "pkexec", "flatpak", "remote-add", "--if-not-exists", "--system",
                "flathub", repo.FLATHUB_REPO_URL,
            ]
        else:
            if repo.terra_configured():
                args = [
                    "pkexec", "dnf", "config-manager", "setopt",
                    "terra.enabled=1", "terra-source.enabled=1",
                ]
            else:
                args = [
                    "pkexec", "dnf", "config-manager", "addrepo",
                    "--from-repofile=https://github.com/terrapkg/subatomic-repos/raw/main/terra.repo",
                ]
        self._toast(_("Aguarde a autorização do sistema para ativar a fonte."))

        def worker() -> None:
            try:
                result = repo.subprocess_(args, timeout=900)
                error = "" if result.returncode == 0 else (result.stderr or result.stdout or "").strip()[-160:]
            except Exception as exception:
                error = str(exception)[:160]
            GLib.idle_add(self._finish_source_enable, key, switch, error)

        threading.Thread(target=worker, daemon=True).start()
        return True

    def _finish_source_enable(self, key: str, switch: Gtk.Switch, error: str) -> bool:
        switch.set_sensitive(True)
        if error:
            self._toast(_("Não foi possível ativar a fonte: {0}").format(error or _("erro desconhecido")))
            return False
        self._set_source_preference(key, True)
        switch.set_active(True)
        return False

    def _set_source_preference(self, key: str, enabled: bool) -> None:
        self.third_party_sources[key] = enabled
        self._save_source_preferences()
        if key == "copr" and (button := self.sidebar_rows.get("copr")):
            button.set_visible(enabled)
            if not enabled and self.page == "copr":
                self.navigate("explore")
                return
        if key == "flatpak" and enabled:
            self._load_flatpak_catalog()
        if key == "terra" and enabled:
            self._reload_data()
            return
        source = {"terra": "Terra", "copr": "COPR", "flatpak": "Flatpak"}[key]
        if not enabled and self.filter_source == source:
            self.filter_source = "Todos"
        self.render_page()

    def _select_sidebar_row(self) -> None:
        btn = self.sidebar_rows.get(self.page)
        if btn:
            if not btn.get_active():
                btn.set_active(True)
            return
        for nav_button in self.sidebar_rows.values():
            if nav_button.get_active():
                nav_button.set_active(False)

    def _nav_clicked(self, btn: Gtk.ToggleButton, key: str) -> None:
        if not btn.get_active():
            return
        if self.page == key and not self.detail_package:
            return
        self.navigate(key)

    def navigate(self, page: str) -> None:
        self.page = page
        self.detail_package = None
        self.copr_package_project = None
        self.local_rpm_detail = False
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
        self._refresh_topbar_search()
        self._clear(self.main_box)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        child_view = self.detail_package is not None or self.copr_package_project is not None or self.local_rpm_detail
        if child_view:
            title = _("Detalhes do aplicativo") if self.detail_package else (
                _("Pacote RPM local") if self.local_rpm_detail else _("Pacotes do projeto COPR")
            )
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
        header.set_show_end_title_buttons(False)
        if child_view:
            view.add_top_bar(header)
        self._topnav_subnav = None
        if not child_view and self._topbar_search:
            subnav = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            subnav.add_css_class("fs-subnav")
            subnav.set_hexpand(True)
            self._topbar_search.set_halign(Gtk.Align.CENTER)
            self._topbar_search.set_width_chars(30)
            subnav.append(self._topbar_search)
            self._topnav_subnav = subnav
            self.main_box.append(subnav)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.set_vexpand(True)
        self._catalog_scroller = scroller
        if self.page == "explore" and not self.detail_package:
            scroller.get_vadjustment().connect("value-changed", self._catalog_scrolled)
        clamp = Adw.Clamp(tightening_threshold=1400, maximum_size=2000)
        scroller.set_child(clamp)
        view.set_content(scroller)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        body.set_margin_top(20)
        body.set_margin_bottom(40)
        body.set_margin_start(24)
        body.set_margin_end(24)
        clamp.set_child(body)
        self.main_box.append(view)
        renderers = {
            "explore": self._explore,
            "installed": self._installed,
            "updates": self._updates,
            "copr": self._copr_page,
            "sources": self._sources,
            "settings": self._settings,
            "local": self._local_rpm_page,
        }
        self.safe = False
        if self.detail_package:
            self._render_detail(body)
        elif self.copr_package_project:
            self._render_copr_project_packages(body)
        elif self.local_rpm_detail:
            self._render_local_rpm_detail(body)
        else:
            renderers.get(self.page, self._explore)(body)

    def _back_to_catalog(self, *_args: object) -> None:
        self.detail_package = None
        self.copr_package_project = None
        self.local_rpm_detail = False
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
            self.render_page()
            return
        if text.casefold() == self._active_search and self.search_results is not None:
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
        key = {"DNF": "dnf", "Terra": "terra", "Flatpak": "flatpak"}.get(origin, "copr")
        label.add_css_class(f"fs-origin-{key}")
        return label

    # ---------- Search ----------

    def _begin_search(self, query: str) -> None:
        if self.page == "explore" and self.filter_source == "Flatpak":
            self._begin_flatpak_search(query)
            return
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


    def _begin_copr_projects(self, query: str) -> None:
        """Search COPR projects through the API (sources page)."""
        self.copr_projects_token += 1
        token = self.copr_projects_token
        self.copr_projects_pending = True
        self.copr_projects_data = None
        self.copr_projects_failed = False
        if self.page == "copr" and not self.detail_package:
            self.render_page()

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
        controls = Gtk.Box(spacing=8)
        controls.set_margin_top(4)
        controls.set_margin_bottom(4)
        controls.set_margin_start(64)
        controls.set_margin_end(24)
        first: Gtk.ToggleButton | None = None
        for source, _key in CHIP_SOURCES:
            if source in ("Terra", "COPR", "Flatpak") and not self.third_party_sources[source.casefold()]:
                continue
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
        (self._topnav_subnav or body).append(controls)

        if self.filter_source == "Flatpak":
            self._explore_flatpak(body)
            return

        if not self.ready:
            body.append(self._state_card(_("Carregando catálogo"), _("Lendo os repositórios do sistema…"), spinner=True))
            return

        if self.query:
            self._explore_search(body)
            return

        if not self.featured_ready:
            body.append(self._state_card(_("Carregando catálogo"), _("Consultando os repositórios do sistema…"), spinner=True))
            return


        if self.selected and self.page == "explore":
            body.append(self._bulk_bar(_("Instalar selecionados")))
        data_rows = self._featured_data_rows()
        if not data_rows:
            message = _("Ainda não há dados dos repositórios; aguarde ou tente novamente.")
            body.append(self._state_card(
                _("Nenhum resultado encontrado"), message,
                icon="system-search-symbolic", action_label=_("Recarregar"),
                callback=self._reload_data))
            return
        rows = self._featured_rows(data_rows[:self.featured_visible])
        body.append(self._package_view(rows))
        if self.featured_loading_more and self.featured_visible < len(data_rows):
            loader = Gtk.Box(spacing=8)
            loader.set_halign(Gtk.Align.CENTER)
            spinner = Gtk.Spinner(spinning=True)
            loader.append(spinner)
            loader.append(Gtk.Label(label=_("Carregando mais aplicativos…")))
            body.append(loader)

    def _explore_flatpak(self, body: Gtk.Box) -> None:
        if not self.flatpak_ready:
            self._load_flatpak_catalog()
            body.append(self._state_card(
                _("Carregando Flatpak"),
                _("Consultando o catálogo público do Flathub…"),
                spinner=True,
            ))
            return
        query = self.query.casefold()
        if query and self.flatpak_search_query == query:
            if self.flatpak_search_loading:
                body.append(self._state_card(
                    _("Buscando no Flathub"),
                    _("Consultando aplicativos para “{0}”…").format(self.query),
                    spinner=True,
                ))
                return
            rows = self.flatpak_search_rows or []
        else:
            rows = [
                row for row in self.flatpak_rows
                if not query or query in f"{row['name']} {row['summary']} {row['flatpak_id']}".casefold()
            ]
        if not rows:
            body.append(self._state_card(
                _("Nenhum aplicativo encontrado"),
                _("O Flathub não retornou aplicativos para esta busca."),
                icon="system-search-symbolic",
            ))
            return
        packages = []
        for row in rows:
            installed = self.flatpak_installed.get(row["flatpak_id"], {})
            package = Package(
                name=row["name"],
                summary=row["summary"],
                description=row["description"],
                icon="application-x-executable-symbolic",
                source="Flatpak",
                repo_id="flathub",
                version=row["version"],
                installed_version=installed.get("version") or None,
                flatpak_id=row["flatpak_id"],
                icon_url=row["icon"],
            )
            packages.append(package)
        body.append(self._package_view(packages))

    def _explore_search(self, body: Gtk.Box) -> None:
        if self.search_pending and self.search_results is None:
            body.append(self._state_card(_("Buscando"), _("Consultando o DNF por “{0}”…").format(self.query), spinner=True))
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
                body.append(self._package_view(cards))
            if total > 80:
                note = Gtk.Label(label=_("Mostrando os {0} primeiros de {1} resultados — refine a busca.").format(len(cards), total), xalign=0, wrap=True)
                note.add_css_class("dim-label")
                body.append(note)

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


    def _copr_project_card(self, project: dict, enabled: set[str]) -> Gtk.Widget:
        owner = str(project.get("ownername") or "")
        project_name = str(project.get("name") or "")
        full_name = str(project.get("full_name") or f"{owner}/{project_name}".strip("/"))
        description = str(project.get("description") or "").strip().replace("\n", " ")
        if len(description) > 180:
            description = description[:177] + "…"
        contact = str(project.get("contact") or owner or "—")

        card = Gtk.Box(spacing=14)
        card.add_css_class("card")
        card.set_size_request(-1, 112)
        card.set_margin_top(2)
        card.set_margin_bottom(2)

        icon = Gtk.Image(icon_name="folder-remote-symbolic", pixel_size=24)
        icon.add_css_class("fs-dim-icon")
        icon.set_margin_start(16)
        icon.set_valign(Gtk.Align.CENTER)
        card.append(icon)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        texts.set_hexpand(True)
        texts.set_valign(Gtk.Align.CENTER)
        name = Gtk.Label(label=full_name, xalign=0)
        name.add_css_class("fs-name")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        texts.append(name)
        if description:
            desc = Gtk.Label(label=description, xalign=0)
            desc.add_css_class("dim-label")
            desc.set_ellipsize(Pango.EllipsizeMode.END)
            texts.append(desc)
        maintainer = Gtk.Label(label=_("Mantenedor: {0}").format(contact), xalign=0)
        maintainer.add_css_class("dim-label")
        maintainer.add_css_class("fs-note")
        texts.append(maintainer)
        card.append(texts)

        view_packages = Gtk.Button(label=_("Ver pacotes"))
        view_packages.add_css_class("fs-pillbtn")
        view_packages.set_valign(Gtk.Align.CENTER)
        view_packages.connect("clicked", self._open_copr_project_packages, owner, project_name, full_name)
        card.append(view_packages)

        if full_name in enabled:
            status = Gtk.Label(label="●  " + _("Habilitado"))
            status.add_css_class("fs-status-ok")
            status.set_margin_end(16)
            status.set_valign(Gtk.Align.CENTER)
            card.append(status)
        else:
            enable = Gtk.Button(label=_("Habilitar"))
            enable.add_css_class("suggested-action")
            enable.add_css_class("fs-pillbtn")
            enable.set_margin_end(16)
            enable.set_valign(Gtk.Align.CENTER)
            enable.connect("clicked", self._enable_copr_project, full_name)
            card.append(enable)
        return card

    def _open_copr_project_packages(
        self, _button: Gtk.Widget, owner: str, project_name: str, full_name: str
    ) -> None:
        if not owner or not project_name:
            self._toast(_("Projeto COPR inválido."))
            return
        project_key = f"{owner}/{project_name}"
        self.copr_package_project = (owner, project_name, full_name)
        if project_key in self._copr_project_packages or project_key in self._copr_project_packages_loading:
            self.render_page()
            return
        self._copr_project_packages_loading.add(project_key)
        self.render_page()

        def worker() -> None:
            try:
                packages = repo.copr_packages(owner, project_name, limit=120, include_builds=True)
            except Exception:
                packages = []
                failed = True
            else:
                failed = False
            GLib.idle_add(self._finish_copr_project_packages, project_key, packages, failed)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_copr_project_packages(self, project_key: str, packages: list[dict], failed: bool) -> bool:
        self._copr_project_packages_loading.discard(project_key)
        if failed:
            self._copr_project_packages_failed.add(project_key)
        else:
            self._copr_project_packages[project_key] = packages
            self._copr_project_packages_failed.discard(project_key)
        if self.copr_package_project and project_key == "/".join(self.copr_package_project[:2]):
            self.render_page()
        return False

    def _render_copr_project_packages(self, body: Gtk.Box) -> None:
        project = self.copr_package_project
        if not project:
            return
        owner, project_name, full_name = project
        project_key = f"{owner}/{project_name}"
        self._page_block(
            body,
            _("Pacotes de {0}").format(full_name),
            _("Pacotes publicados neste projeto COPR. Habilite o projeto somente após revisar a lista."),
        )
        if project_key in self._copr_project_packages_loading:
            body.append(self._state_card(
                _("Carregando pacotes"),
                _("Consultando a API pública do COPR…"),
                spinner=True,
            ))
            return
        if project_key in self._copr_project_packages_failed:
            body.append(self._state_card(
                _("Pacotes indisponíveis"),
                _("Não foi possível consultar os pacotes deste projeto COPR."),
                icon="network-offline-symbolic",
                action_label=_("Tentar novamente"),
                callback=lambda *_: self._retry_copr_project_packages(owner, project_name, full_name),
            ))
            return
        packages = self._copr_project_packages.get(project_key, [])
        if not packages:
            body.append(self._state_card(
                _("Nenhum pacote publicado"),
                _("A API do COPR não retornou pacotes para este projeto."),
                icon="folder-remote-symbolic",
            ))
            return
        def value_cell(text: str, width: int, css_class: str = "") -> Gtk.Label:
            cell = Gtk.Label(label=text, xalign=0)
            cell.add_css_class("fs-copr-value")
            if css_class:
                cell.add_css_class(css_class)
            cell.set_size_request(width, -1)
            cell.set_ellipsize(Pango.EllipsizeMode.END)
            return cell

        columns = (
            (_("Pacote"), 260),
            (_("Última versão"), 170),
            (_("Enviado em"), 170),
            (_("Status"), 140),
            (_("Build automático"), 160),
        )
        table = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        table.add_css_class("card")
        table.add_css_class("fs-copr-table")
        header = Gtk.Box(spacing=24)
        header.add_css_class("fs-copr-table-header")
        header.set_margin_start(10)
        header.set_margin_end(10)
        for label, width in columns:
            header_label = Gtk.Label(label=label, xalign=0)
            header_label.add_css_class("fs-copr-table-header-label")
            header_label.set_size_request(width, -1)
            if label == _("Pacote"):
                header_label.set_hexpand(True)
            header.append(header_label)
        table.append(header)

        package_list = Gtk.ListBox()
        package_list.set_selection_mode(Gtk.SelectionMode.NONE)
        package_list.add_css_class("boxed-list")
        for package in packages:
            build = package.get("latest_build") if isinstance(package.get("latest_build"), dict) else {}
            source = build.get("source_package") if isinstance(build.get("source_package"), dict) else {}
            submitted = build.get("submitted_on")
            try:
                submitted_text = datetime.fromtimestamp(int(submitted)).strftime("%d/%m/%Y %H:%M")
            except (TypeError, ValueError, OSError):
                submitted_text = "—"
            state = str(build.get("state") or "")
            status_text, status_class = {
                "succeeded": (_("Concluído"), "fs-copr-status-ok"),
                "failed": (_("Falhou"), "fs-copr-status-failed"),
                "forked": (_("Em andamento"), "fs-copr-status-running"),
                "pending": (_("Na fila"), "fs-copr-status-running"),
            }.get(state, (state or _("Sem build"), ""))

            row = Gtk.Box(spacing=24)
            row.add_css_class("fs-copr-table-row")
            row.set_margin_top(3)
            row.set_margin_bottom(3)
            row.set_margin_start(10)
            row.set_margin_end(10)
            package_info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            package_info.set_hexpand(True)
            package_info.set_size_request(columns[0][1], -1)
            name = Gtk.Label(label=str(package.get("name") or _("Pacote sem nome")), xalign=0)
            name.add_css_class("fs-copr-package")
            name.set_ellipsize(Pango.EllipsizeMode.END)
            source_type = str(package.get("source_type") or "")
            if source_type:
                name.set_tooltip_text(_("Origem: {0}").format(source_type))
            package_info.append(name)
            row.append(package_info)
            row.append(value_cell(str(source.get("version") or "—"), columns[1][1]))
            row.append(value_cell(submitted_text, columns[2][1]))
            status = value_cell(status_text, columns[3][1], "fs-copr-status")
            if status_class:
                status.add_css_class(status_class)
            row.append(status)
            auto_text = _("Ativado") if package.get("auto_rebuild") else _("Desativado")
            auto = value_cell(auto_text, columns[4][1], "fs-status-ok" if package.get("auto_rebuild") else "fs-status-off")
            row.append(auto)
            package_list.append(row)
        table.append(package_list)
        body.append(table)

    def _retry_copr_project_packages(self, owner: str, project_name: str, full_name: str) -> None:
        self._copr_project_packages_failed.discard(f"{owner}/{project_name}")
        self._open_copr_project_packages(Gtk.Button(), owner, project_name, full_name)

    def _enable_copr_project(self, _button: Gtk.Widget, project: str) -> None:
        if not project or "/" not in project:
            self._toast(_("Projeto COPR inválido."))
            return
        GLib.idle_add(self._run_copr_toggle, project, True)

    def _reload_data(self, *_args: object) -> None:
        self.featured_ready = False
        self.featured_visible = 48
        self.featured_loading_more = False
        self.render_page()
        self._load_initial()

    def _catalog_scrolled(self, adjustment: Gtk.Adjustment) -> None:
        if self.page != "explore" or self.detail_package or self.query or self.featured_loading_more:
            return
        if adjustment.get_value() + adjustment.get_page_size() < adjustment.get_upper() - 32:
            return
        if self.featured_visible >= len(self._featured_data_rows()):
            return
        self.featured_loading_more = True
        self._catalog_scroll_y = adjustment.get_value()
        self.render_page()
        GLib.idle_add(self._restore_catalog_scroll)
        GLib.timeout_add(150, self._finish_featured_load)

    def _finish_featured_load(self) -> bool:
        self.featured_visible += 48
        self.featured_loading_more = False
        self.render_page()
        GLib.idle_add(self._restore_catalog_scroll)
        return False

    def _restore_catalog_scroll(self) -> bool:
        if self._catalog_scroller:
            self._catalog_scroller.get_vadjustment().set_value(self._catalog_scroll_y)
        return False

    def _featured_data_rows(self) -> list[dict]:
        key = (self.filter_source, self.sort_mode)
        if key == self._featured_view_key:
            return self._featured_view_rows

        rows = []
        for row in self.packages_featured:
            name = row["name"]
            if self.filter_source == "Instalados" and name not in self.packages_installed:
                continue
            if self.filter_source not in ("Todos", "Instalados"):
                source = "Fedora" if self.filter_source == "DNF" else self.filter_source
                if repo.repo_label(row.get("repository", "")) != source:
                    continue
            rows.append(row)
        if self.sort_mode == 0:
            rows.sort(key=lambda row: row["name"].casefold())
        else:
            rows.sort(key=lambda row: (repo.repo_label(row.get("repository", "")), row["name"].casefold()))
        self._featured_view_key = key
        self._featured_view_rows = rows
        return rows

    def _featured_rows(self, raw_rows: list[dict]) -> list[Package]:
        rows: list[Package] = []
        for row in raw_rows:
            name = row["name"]
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
        return rows

    def _filter_toggled(self, button: Gtk.ToggleButton, source: str) -> None:
        if self.safe or not button.get_active() or source == self.filter_source:
            return
        self.filter_source = source
        self._featured_view_key = None
        self._featured_view_rows = []
        self.featured_visible = 48
        self.featured_loading_more = False
        self._catalog_scroll_y = 0.0
        self.render_page()

    def _sort_changed(self, dropdown: Gtk.DropDown, _param: object) -> None:
        if self.safe:
            return
        self.sort_mode = dropdown.get_selected()
        self._featured_view_key = None
        self._featured_view_rows = []
        self.render_page()

    def _view_toggled(self, button: Gtk.ToggleButton, mode: str) -> None:
        if self.safe or not button.get_active() or mode == self.view_mode:
            return
        self.view_mode = mode
        self.render_page()

    def _package_image(self, package: Package, pixel_size: int) -> Gtk.Image:
        image = Gtk.Image(icon_name=package.icon, pixel_size=pixel_size)
        if not package.icon_url:
            return image
        texture = self._flatpak_icon_cache.get(package.icon_url)
        if texture:
            image.set_from_paintable(texture)
            image.set_pixel_size(pixel_size)
            return image
        self._flatpak_icon_widgets.setdefault(package.icon_url, []).append(image)
        if package.icon_url not in self._flatpak_icon_pending:
            self._flatpak_icon_pending.add(package.icon_url)

            def worker() -> None:
                try:
                    data = repo.download_icon(package.icon_url)
                except Exception:
                    data = b""
                GLib.idle_add(self._finish_flatpak_icon, package.icon_url, data)

            threading.Thread(target=worker, daemon=True).start()
        return image

    def _finish_flatpak_icon(self, url: str, data: bytes) -> bool:
        self._flatpak_icon_pending.discard(url)
        if not data:
            self._flatpak_icon_widgets.pop(url, None)
            return False
        try:
            texture = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))
        except Exception:
            self._flatpak_icon_widgets.pop(url, None)
            return False
        self._flatpak_icon_cache[url] = texture
        for image in self._flatpak_icon_widgets.pop(url, []):
            image.set_from_paintable(texture)
            image.set_pixel_size(32)
        return False

    def _detail_id(self, package: Package) -> str:
        identity = package.flatpak_id or package.repo_id or package.name
        target = f"{package.source}:{identity}:{package.name}"
        self._detail_packages[target] = package
        return target

    def _package_grid(self, packages: list[Package]) -> Gtk.FlowBox:
        grid = Gtk.FlowBox()
        grid.set_selection_mode(Gtk.SelectionMode.NONE)
        grid.set_homogeneous(True)
        grid.set_hexpand(True)
        grid.set_halign(Gtk.Align.FILL)
        grid.set_min_children_per_line(1)
        grid.set_max_children_per_line(4)
        grid.set_column_spacing(16)
        grid.set_row_spacing(16)
        grid.set_valign(Gtk.Align.START)
        for package in packages:
            grid.append(self._package_card(package))
        return grid

    def _package_view(self, packages: list[Package]) -> Gtk.Widget:
        return self._package_list(packages) if self.view_mode == "list" else self._package_grid(packages)

    def _package_card(self, package: Package) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class("card")
        card.set_size_request(220, 124)
        card.set_vexpand(False)
        card.set_valign(Gtk.Align.START)
        card.set_margin_top(2)
        card.set_margin_bottom(2)
        card.set_margin_start(2)
        card.set_margin_end(2)

        intro = Gtk.Box(spacing=10)
        intro.set_hexpand(True)
        intro.set_margin_top(12)
        intro.set_margin_start(12)
        intro.set_margin_end(12)
        if not package.installed and not package.updatable and package.source != "Flatpak":
            select = Gtk.CheckButton()
            select.set_active(package.name in self.selected)
            select.set_tooltip_text(_("Selecionar para instalar"))
            select.set_valign(Gtk.Align.CENTER)
            select.connect("toggled", self._selection_changed, package.name)
            intro.append(select)
        intro.append(self._package_image(package, 32))
        name = Gtk.Label(label=package.name, xalign=0)
        name.add_css_class("fs-name")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_tooltip_text(package.name)
        name.set_hexpand(True)
        intro.append(name)
        detail = Gtk.GestureClick()
        detail.connect("released", self._open_detail, package)
        name.add_controller(detail)
        card.append(intro)

        spacer = Gtk.Box()
        spacer.set_vexpand(True)
        card.append(spacer)

        actions = Gtk.Box(spacing=6)
        actions.set_margin_bottom(12)
        actions.set_margin_start(12)
        actions.set_margin_end(12)
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
        action.add_css_class("fs-package-action")
        action.set_valign(Gtk.Align.CENTER)
        action.connect("clicked", self._package_action, package)
        actions.append(action)
        menu = Gio.Menu()
        menu.append(_("Abrir detalhes"), detail_target(self._detail_id(package)))
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
            action.add_css_class("fs-package-action")
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
        if package.source == "Flatpak":
            self._apply_flatpak(package)
        else:
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
        clear = Gtk.Button(label=_("Limpar"))
        clear.add_css_class("flat")
        clear.connect("clicked", self._clear_selection)
        bar.append(clear)
        button = Gtk.Button(label=_(action_label))
        button.add_css_class("suggested-action")
        button.add_css_class("fs-bold")
        button.add_css_class("fs-pillbtn")
        button.connect("clicked", self._bulk_apply)
        bar.append(button)
        return bar

    def _clear_selection(self, *_args: object) -> None:
        self.selected.clear()
        self.render_page()

    def _bulk_apply(self, *_args: object) -> None:
        packages = [self._pkg(name) for name in self.selected]
        packages = [p for p in packages if p is not None]
        self._apply(packages)

    # ---------- Instalados ----------

    def _installed(self, body: Gtk.Box) -> None:
        self._page_block(body, _("Aplicativos instalados"), _("Gerencie os pacotes presentes neste computador."))

        controls = Gtk.Box(spacing=10)
        controls.set_margin_top(4)
        controls.set_margin_bottom(4)
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
        listbox.add_css_class("card")
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
        all_packages = self._update_packages()
        packages = [
            package for package in all_packages
            if not self.query_updates or self.query_updates in package.name.casefold()
        ]
        block = Gtk.Box(spacing=16)
        block.set_hexpand(True)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        heading = Gtk.Label(label=_("Atualizações disponíveis"), xalign=0)
        heading.add_css_class("fs-heading")
        texts.append(heading)
        count = len(all_packages)
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

    # ---------- RPM local ----------

    def _local_rpm_page(self, body: Gtk.Box) -> None:
        self._page_block(body, _("Instalar RPM local"), _("Arraste um arquivo .rpm ou escolha-o no computador."))
        drop = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        drop.add_css_class("card")
        drop.add_css_class("fs-rpm-drop")
        drop.set_halign(Gtk.Align.FILL)
        drop.append(Gtk.Image(icon_name="package-x-generic-symbolic", pixel_size=40))
        title = Gtk.Label(label=_("Solte um arquivo RPM aqui"), xalign=0)
        title.add_css_class("fs-name")
        title.set_halign(Gtk.Align.CENTER)
        drop.append(title)
        choose = Gtk.Button(label=_("Escolher arquivo"))
        choose.add_css_class("fs-pillbtn")
        choose.set_halign(Gtk.Align.CENTER)
        choose.connect("clicked", self._choose_local_rpm)
        drop.append(choose)
        target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        target.connect("drop", self._drop_local_rpm)
        drop.add_controller(target)
        body.append(drop)
        if self.local_rpm_loading:
            body.append(self._state_card(_("Lendo pacote"), _("Verificando os metadados do RPM…"), spinner=True))
        elif self.local_rpm:
            data = self.local_rpm
            row = Adw.ActionRow(title=data["name"], subtitle=data["summary"] or _("Sem descrição"))
            row.add_prefix(Gtk.Image(icon_name="package-x-generic-symbolic"))
            row.add_suffix(Gtk.Label(label=f'{data["version"]} · {data["arch"]} · {int(data["size"] or 0) / 1_048_576:.1f} MB'))
            install = Gtk.Button(label=_("Instalar"))
            install.add_css_class("suggested-action")
            install.add_css_class("fs-rpm-install")
            install.set_valign(Gtk.Align.CENTER)
            install.set_vexpand(False)
            install.set_size_request(-1, 30)
            install.connect("clicked", self._install_local_rpm)
            row.add_suffix(install)
            card = Gtk.ListBox()
            card.add_css_class("card")
            card.append(row)
            body.append(card)

    def _choose_local_rpm(self, _button: Gtk.Button) -> None:
        dialog = Gtk.FileDialog(title=_("Escolher pacote RPM"))
        dialog.open(self.window, None, self._finish_choose_local_rpm)

    def _finish_choose_local_rpm(self, dialog: Gtk.FileDialog, result) -> None:
        try:
            file = dialog.open_finish(result)
        except GLib.Error:
            return
        self._load_local_rpm(file.get_path() or "")

    def _drop_local_rpm(self, _target: Gtk.DropTarget, files: Gdk.FileList, _x: float, _y: float) -> bool:
        items = files.get_files()
        if not items:
            return False
        first = items[0] if isinstance(items, list) else items.get_item(0)
        self._load_local_rpm(first.get_path() or "")
        return True

    def _load_local_rpm(self, path: str) -> None:
        self.local_rpm, self.local_rpm_loading = None, True
        self.render_page()
        def worker() -> None:
            try:
                data, error = repo.local_rpm_metadata(path), ""
            except Exception as exception:
                data, error = None, str(exception)
            GLib.idle_add(self._finish_local_rpm, data, error)
        threading.Thread(target=worker, daemon=True).start()

    def _finish_local_rpm(self, data: dict[str, str] | None, error: str) -> bool:
        self.local_rpm_loading, self.local_rpm = False, data
        self.local_rpm_detail = data is not None
        self.render_page()
        if error:
            self._toast(_("Não foi possível ler o RPM: {0}").format(error[:130]))
        return False

    def _render_local_rpm_detail(self, body: Gtk.Box) -> None:
        if not self.local_rpm:
            return
        data = self.local_rpm
        hero = Gtk.Box(spacing=18)
        icon_path = data.get("icon", "")
        icon = Gtk.Image.new_from_file(icon_path) if icon_path else Gtk.Image(icon_name="package-x-generic-symbolic")
        icon.set_pixel_size(72)
        hero.append(icon)
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        texts.set_hexpand(True)
        name = Gtk.Label(label=data["name"], xalign=0)
        name.add_css_class("fs-detail-title")
        texts.append(name)
        summary = Gtk.Label(label=data["summary"] or _("Pacote RPM local"), xalign=0, wrap=True)
        summary.add_css_class("dim-label")
        texts.append(summary)
        texts.append(Gtk.Label(label=_("Pacote local · RPM"), xalign=0))
        hero.append(texts)
        install = Gtk.Button(label=_("Instalar"))
        install.add_css_class("suggested-action")
        install.add_css_class("fs-rpm-install")
        install.set_valign(Gtk.Align.CENTER)
        install.set_vexpand(False)
        install.set_size_request(-1, 30)
        install.connect("clicked", self._install_local_rpm)
        hero.append(install)
        body.append(hero)
        rows = Gtk.ListBox()
        rows.add_css_class("card")
        rows.add_css_class("boxed-list")
        for title, value in ((_("Versão"), data["version"]), (_("Arquitetura"), data["arch"]),
                             (_("Tamanho"), f'{int(data["size"] or 0) / 1_048_576:.1f} MB'),
                             (_("Arquivo"), data["path"])):
            rows.append(Adw.ActionRow(title=title, subtitle=value))
        body.append(rows)

    def _install_local_rpm(self, _button: Gtk.Button) -> None:
        if self.local_rpm and not self.busy:
            self._run_root(["pkexec", "dnf", "install", "-y", self.local_rpm["path"]], _("Pacote local instalado"), "data")

    def _update_all(self, *_args: object) -> None:
        self._apply(self._update_packages())

    # ---------- Fontes ----------

    def _settings(self, body: Gtk.Box) -> None:
        self._page_block(
            body,
            _("Configurações"),
            _("Controle quais fontes de terceiros aparecem no catálogo."),
        )
        heading = Gtk.Label(label=_("Fontes de terceiros"), xalign=0)
        heading.add_css_class("fs-page-title")
        body.append(heading)
        note = Gtk.Label(
            label=_("Ativar uma fonte do sistema solicita autorização pelo Polkit."),
            xalign=0,
            wrap=True,
        )
        note.add_css_class("dim-label")
        note.add_css_class("fs-note")
        body.append(note)
        rows = Gtk.ListBox()
        rows.set_selection_mode(Gtk.SelectionMode.NONE)
        rows.add_css_class("card")
        rows.add_css_class("boxed-list")
        for key, title, subtitle in (
            ("flatpak", _("Flatpak / Flathub"), _("Aplicativos em sandbox do Flathub.")),
            ("terra", _("Terra"), _("Repositório comunitário para Fedora.")),
            ("copr", _("COPR"), _("Escolha projetos comunitários individualmente.")),
        ):
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            switch = Gtk.Switch(active=self.third_party_sources[key])
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("state-set", self._source_switch_state, key)
            row.add_suffix(switch)
            rows.append(row)
        body.append(rows)

        behavior_heading = Gtk.Label(label=_("Execução em segundo plano"), xalign=0)
        behavior_heading.add_css_class("fs-page-title")
        behavior_heading.set_margin_top(18)
        body.append(behavior_heading)
        behavior = Gtk.ListBox()
        behavior.set_selection_mode(Gtk.SelectionMode.NONE)
        behavior.add_css_class("card")
        behavior.add_css_class("boxed-list")
        for key, title, subtitle in (
            ("tray", _("Manter na bandeja"), _("Ao fechar a janela, mantenha o Aplicativos ativo na bandeja.")),
            ("autostart", _("Iniciar ao entrar na sessão"), _("Inicia em segundo plano e avisa quando houver atualizações.")),
        ):
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            switch = Gtk.Switch(active=self.third_party_sources[key])
            switch.set_valign(Gtk.Align.CENTER)
            switch.connect("state-set", self._background_switch_state, key)
            row.add_suffix(switch)
            behavior.append(row)
        body.append(behavior)

    def _sources(self, body: Gtk.Box) -> None:
        self._page_block(body, _("Fontes de aplicativos"), _("Repositórios configurados no DNF neste computador."))
        if not self.ready:
            body.append(self._state_card(_("Carregando fontes"), _("Lendo a lista de repositórios…"), spinner=True))
            return

        heading = Gtk.Label(label=_("Repositórios do sistema"), xalign=0)
        heading.add_css_class("fs-page-title")
        body.append(heading)
        system_repos = [
            repo_row for repo_row in self.repos
            if not str(repo_row["id"]).startswith(("copr:", "coprdep:"))
            and (
                not self.query_sources
                or self.query_sources in f"{repo_row['id']} {repo_row['name']}".casefold()
            )
        ]
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
        all_copr = [r for r in self.repos if str(r["id"]).startswith("copr:")]
        copr_repos = [r for r in all_copr if not self.copr_query or self.copr_query in f"{r['id']} {r['name']}".casefold()]
        enabled = self._enabled_copr_projects()
        self._copr_rows = {}

        if self.copr_query:
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

    def _detail_key(self, package: Package) -> str:
        return f"{package.source}:{package.flatpak_id or package.repo_id}:{package.name}"

    def _kick_detail_info(self, package: Package) -> None:
        key = self._detail_key(package)
        self._detail_pending.add(key)
        name = package.name

        def worker() -> None:
            rows: list[tuple[str, str, str]] = []
            try:
                rows = repo.info_rows(name)
            except Exception:
                rows = []
            GLib.idle_add(self._detail_loaded, key, rows)

        threading.Thread(target=worker, daemon=True).start()

    def _detail_loaded(self, key: str, rows: list) -> bool:
        self._detail_pending.discard(key)
        if rows:
            self._detail_info[key] = rows
            self._detail_failed.discard(key)
        else:
            self._detail_failed.add(key)
        if self.detail_package is not None and self._detail_key(self.detail_package) == key:
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
        dnf_backed = package.source != "Flatpak"
        if dnf_backed and not package.installed_version:
            row = self.packages_installed.get(package.name)
            if row:
                package.installed_version = row.get("evr")
        if dnf_backed and not package.update_version:
            upgrade_row = next((u for u in self.packages_upgrades if u["name"] == package.name), None)
            if upgrade_row:
                package.update_version = upgrade_row.get("evr")
        detail_key = self._detail_key(package)
        cached = self._detail_info.get(detail_key)
        if cached and not package.version:
            self._hydrate_from_info(package, cached)
        if dnf_backed and not package.version and detail_key not in self._detail_pending and detail_key not in self._detail_failed:
            self._kick_detail_info(package)
        has_data = bool(package.version or package.installed_version or package.repo_id)
        hero = Gtk.Box(spacing=22)
        hero.set_hexpand(True)
        hero.append(self._package_image(package, 72))
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
            provider = "DNF" if dnf_backed else "Flathub"
            if detail_key in self._detail_failed:
                body.append(self._state_card(
                    _("Informações indisponíveis"),
                    _("O {0} não retornou dados para {1}. Tente novamente mais tarde.").format(provider, package.name),
                    icon="dialog-information-symbolic",
                ))
            else:
                body.append(self._state_card(
                    _("Consultando {0}").format(provider),
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
        about = Gtk.Label(label=package.description or package.summary or _("Sem descrição disponível."), xalign=0, wrap=True)
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
        if package.flatpak_id:
            rows.append((_("ID do aplicativo"), package.flatpak_id))
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
    def _apply_flatpak(self, package: Package) -> None:
        if self.busy or not package.flatpak_id:
            return
        self.busy = True
        operation = self._operation(package)
        self._busy_summary = operation
        if package.installed:
            command = ["pkexec", "flatpak", "uninstall", "--system", "-y", package.flatpak_id]
        else:
            command = ["pkexec", "flatpak", "install", "--system", "-y", "flathub", package.flatpak_id]
        self._show_progress([package])

        def worker() -> None:
            try:
                result = repo.subprocess_(command, timeout=1800)
                if result.returncode == 126:
                    error = "__auth_cancelled__"
                elif result.returncode == 127:
                    error = "__auth_failed__"
                elif result.returncode:
                    error = (result.stderr or result.stdout or "").strip()[-160:]
                else:
                    error = ""
            except Exception as exception:
                error = str(exception)[:160]
            GLib.idle_add(self._finish_flatpak_action, error)

        threading.Thread(target=worker, daemon=True).start()

    def _finish_flatpak_action(self, error: str) -> bool:
        self.busy = False
        summary = self._busy_summary
        self._busy_summary = ""
        self.flatpak_ready = False
        self.detail_package = None
        self._load_flatpak_catalog()
        self.render_page()
        if error == "__auth_cancelled__":
            self._toast(_("Autenticação cancelada — nada foi alterado"))
        elif error == "__auth_failed__":
            self._toast(_("Falha de autenticação — nada foi alterado"))
        elif error:
            self._toast(_("A operação falhou: {0}").format(error))
        else:
            self._toast(_("{0} concluída com sucesso").format(summary))
        return False


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
            commands.append(["pkexec", "dnf", "upgrade", "--refresh", "-y", *upgrades])
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
                try:
                    upgrade_rows = repo.refresh_upgrades()
                except Exception:
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
        operations = {self._operation(package) for package in packages}
        if operations == {_("Instalar")}:
            heading_text = _("Instalando aplicativo…") if len(packages) == 1 else _("Instalando aplicativos…")
        elif operations == {_("Atualizar")}:
            heading_text = _("Atualizando aplicativo…") if len(packages) == 1 else _("Atualizando aplicativos…")
        elif operations == {_("Remover")}:
            heading_text = _("Removendo aplicativo…") if len(packages) == 1 else _("Removendo aplicativos…")
        else:
            heading_text = _("Aplicando alterações…")
        subject = packages[0].name if len(packages) == 1 else _(
            "{0} pacotes selecionados"
        ).format(len(packages))

        panel = Gtk.Box(spacing=14)
        panel.set_halign(Gtk.Align.CENTER)
        panel.set_size_request(640, -1)
        panel.set_margin_top(12)
        panel.set_margin_bottom(16)
        panel.set_margin_start(16)
        panel.set_margin_end(16)
        panel.append(Gtk.Spinner(spinning=True))
        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        texts.set_hexpand(True)
        heading = Gtk.Label(label=heading_text, xalign=0)
        heading.add_css_class("fs-name")
        texts.append(heading)
        sub = Gtk.Label(
            label=_("{0}. Isso pode levar alguns instantes.").format(subject),
            xalign=0,
        )
        sub.set_ellipsize(Pango.EllipsizeMode.END)
        sub.add_css_class("dim-label")
        texts.append(sub)
        panel.append(texts)
        progress = Gtk.ProgressBar()
        progress.set_size_request(180, -1)
        progress.add_css_class("fs-progress")
        progress.set_pulse_step(0.12)
        progress.set_valign(Gtk.Align.CENTER)
        panel.append(progress)
        self.main_box.append(panel)

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
        if reload_fn in ("repos", "data"):
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
        for name, mode in (("navigation-topnav", "topnav"), ("navigation-sidebar", "sidebar")):
            navigation = Gio.SimpleAction.new(name, None)
            navigation.connect("activate", self._set_navigation_mode, mode)
            self.add_action(navigation)

    def _act_open_detail(self, _action: Gio.SimpleAction, variant: GLib.Variant) -> None:
        target = variant.unpack()
        package = self._detail_packages.get(target)
        if package is None and target.startswith("'") and target.endswith("'"):
            target = target[1:-1].replace("''", "'")
            package = self._detail_packages.get(target)
        package = package or self._pkg(target)
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
    background = "--background" in sys.argv
    args = [arg for arg in sys.argv if arg != "--background"]
    app = FedoraStore(background=background)
    raise SystemExit(app.run(args))
