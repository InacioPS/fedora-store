# Repository Guidelines

## Project Overview

Fedora Store is a Python GTK4/libadwaita desktop application for browsing Fedora packages, installed software, updates, configured repositories, and public COPR projects. Package origin must remain explicit (`Fedora`/`DNF`, `Terra`, or `COPR`).

## Architecture & Data Flow

`python -m fedora_store` reaches `fedora_store.app.main()`, which owns the GTK application and page state.

- `fedora_store/app.py` renders navigation and the five page renderers (`_explore`, `_installed`, `_updates`, `_copr_page`, `_sources`), adapts data into UI models, and owns async operation state.
- Startup launches daemon threads for DNF reads; workers marshal UI changes back through `GLib.idle_add`. Preserve that boundary: GTK widgets are updated only on the GTK main thread.
- `fedora_store/repo.py` is the external-data boundary. DNF reads use `dnf -C`; COPR discovery calls its public APIv3; privileged changes run through `pkexec` from `app.py`.
- `fedora_store/catalog.py` defines the UI-facing `Package` dataclass and derived `installed`, `updatable`, and `origin` properties.

Keep UI changes in `app.py`, source/query shaping in `repo.py`, and presentation-model fields in `catalog.py`. Do not hide COPR as an official Fedora source. Do not move privileged work into the UI thread or substitute `sudo` for Polkit.

## Key Directories

- `fedora_store/` — application package.
- `fedora_store/app.py` — GTK UI, in-memory state, navigation, background loading, package/repository actions.
- `fedora_store/repo.py` — DNF and COPR integration plus package/icon helpers.
- `fedora_store/catalog.py` — package presentation model.

## Development Commands

```sh
# First use; loads the Nix flake through .envrc
direnv allow

# Alternative development shell
nix develop

# Run the desktop application
python -m fedora_store
```

No build, test, or lint command is documented. Ruff configuration exists, but Ruff is not supplied by `flake.nix`; do not assume `ruff` is available without checking the active environment.

## Code Conventions & Common Patterns

- Python 3.11+; Ruff is configured for `py311` and 100-character lines in `pyproject.toml`.
- Use `snake_case` for functions/state and `PascalCase` for classes. UI strings are wrapped with `_()` for gettext.
- UI state is held directly on `FedoraStore` (for example `page`, `query`, `packages_installed`, `busy`). Rendering is declarative-by-rebuild: `render_page()` clears and rebuilds the active page while preserving focused search state.
- Search state is page-specific. Keep top-bar search attributes aligned with their renderer (for example `query`, `query_installed`, `query_updates`, `copr_query`, `query_sources`).
- Long-running DNF, HTTP, and privileged actions run in daemon threads and return via `GLib.idle_add`; surface errors through the existing state-card/toast paths.
- Preserve source labels, package versions, and operation consequences in user-visible flows. Operations must not silently discard DNF failures or conflicts.
- Reuse embedded `STYLE` classes and libadwaita components instead of introducing a parallel styling system.

## Important Files

- `fedora_store/__main__.py` — module entry point.
- `fedora_store/app.py` — primary application module; includes GTK CSS and `main()`.
- `fedora_store/repo.py` — DNF/COPR integration; `subprocess_()` is the common command wrapper.
- `fedora_store/catalog.py` — `Package` model.
- `flake.nix` / `.envrc` — Nix and direnv development environment.
- `pyproject.toml` — Python version and Ruff settings.
- `requeriments.md` — Portuguese product constraints and intended architecture; use it for UX/security context. The filename is intentionally misspelled.
- `README.md` — setup and launch instructions; update it when changing privileged behavior.

## Runtime/Tooling Preferences

Use the Nix flake environment, not a pip-managed replacement. It supplies Python with PyGObject, GTK4, libadwaita, GObject introspection, theme icons, AppStream tools, Meson, Ninja, and Flatpak; it also sets `GI_TYPELIB_PATH` and `XDG_DATA_DIRS`.

Runtime data access expects Fedora, `dnf`, and Flatpak for Flathub support. DNF reads are cache-only (`dnf -C`); Flathub catalog metadata is fetched from its public API. Package/repository mutations require Polkit via `pkexec`.

## Testing & QA

There is no committed test suite, test runner, coverage configuration, formatter configuration, type-checker configuration, or CI workflow.

For changes, smoke-test the changed UI path in a GTK-capable session. For non-UI logic, exercise the relevant `repo.py` function with controlled inputs or a temporary script; `repo.subprocess_()` is the existing patch seam. Add durable tests only when a test harness and an externally observable behavior can be defined; avoid tests that merely assert wiring or implementation details.
