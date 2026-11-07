Name:           fedora-store
Version:        0.1.1
Release:        1%{?dist}
Summary:        Loja de aplicativos para Fedora

License:        GPL-3.0-or-later
URL:            https://github.com/fedorastore/fedora-store
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk4
Requires:       libadwaita
Requires:       dnf5
Requires:       flatpak
Requires:       polkit
Requires:       rpm
Requires:       cpio

%description
Aplicação GTK4/libadwaita para explorar pacotes Fedora, Flatpak,
atualizações, repositórios e projetos COPR.

%prep
%autosetup

%build
# Aplicação Python sem etapa de compilação.

%install
install -d %{buildroot}%{_datadir}/fedora-store
cp -a fedora_store %{buildroot}%{_datadir}/fedora-store/
find %{buildroot}%{_datadir}/fedora-store -type d -name __pycache__ -prune -exec rm -rf {} +

install -Dpm0755 packaging/fedora-store %{buildroot}%{_bindir}/fedora-store
install -Dpm0644 packaging/io.github.fedorastore.FedoraStore.desktop \
  %{buildroot}%{_datadir}/applications/io.github.fedorastore.FedoraStore.desktop
install -Dpm0644 fedora_store/assets/fedora-store-logo.png \
  %{buildroot}%{_datadir}/icons/hicolor/128x128/apps/io.github.fedorastore.FedoraStore.png

%check
desktop-file-validate packaging/io.github.fedorastore.FedoraStore.desktop

%files
%license LICENSE.md
%doc README.md
%{_bindir}/fedora-store
%{_datadir}/fedora-store/fedora_store/
%{_datadir}/applications/io.github.fedorastore.FedoraStore.desktop
%{_datadir}/icons/hicolor/128x128/apps/io.github.fedorastore.FedoraStore.png

%changelog
* Sat Nov 07 2026 Fedora Store contributors <maintainers@fedorastore.invalid> - 0.1.1-1
- Atualizacao pela release do GitHub com botao na notificacao
* Thu Nov 05 2026 Fedora Store contributors <maintainers@fedorastore.invalid> - 0.1.0-1
- First RPM package
