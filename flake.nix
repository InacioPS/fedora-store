{
  description = "Loja de aplicativos Fedora com GTK4 e libadwaita";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = function: nixpkgs.lib.genAttrs systems (system:
        function (import nixpkgs { inherit system; }));
    in {
      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = with pkgs; [
            (python3.withPackages (pythonPackages: [ pythonPackages.pygobject3 ]))
            gobject-introspection
            gtk4
            libadwaita
            pkg-config
            desktop-file-utils
            appstream
            adwaita-icon-theme
            meson
            ninja
          ];
          nativeBuildInputs = with pkgs; [ wrapGAppsHook4 ];
          buildInputs = with pkgs; [ gtk4 libadwaita gobject-introspection ];
          shellHook = ''
            export GI_TYPELIB_PATH="${pkgs.gtk4}/lib/girepository-1.0:${pkgs.libadwaita}/lib/girepository-1.0''${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}"
            export XDG_DATA_DIRS="${pkgs.gtk4}/share:${pkgs.libadwaita}/share''${XDG_DATA_DIRS:+:$XDG_DATA_DIRS}"
            echo "Ambiente Fedora Store pronto (GTK4 + libadwaita)."
          '';
        };
      });
    };
}
