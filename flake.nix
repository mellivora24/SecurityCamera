{
  description = "Lean dev shell: Expo + Python (FastAPI + ML)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          packages = with pkgs; [
            # Node
            nodejs_20

            # Python
            python310
            uv

            stdenv.cc
            stdenv.cc.cc.lib

            # ML native deps
            zlib
            glib
            libglvnd

            pkg-config
            gnumake
          ];

          shellHook = ''
            # vào backend nếu tồn tại
            cd backend 2>/dev/null || true

            export UV_PROJECT_ENVIRONMENT=.venv

            if [ ! -d .venv ]; then
              uv venv .venv --python ${pkgs.python310}/bin/python3.10
            fi

            source .venv/bin/activate

            export NIX_LD=${pkgs.stdenv.cc.libc}/lib/ld-linux-x86-64.so.2

            export NIX_LD_LIBRARY_PATH="${
              pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc.lib
                pkgs.zlib
                pkgs.glib
                pkgs.libglvnd
              ]
            }"

            # fallback (một số tool vẫn cần)
            export LD_LIBRARY_PATH="$NIX_LD_LIBRARY_PATH:$LD_LIBRARY_PATH"
          '';
        };
      });
}