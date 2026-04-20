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
            nodejs_20

            python310
            uv

            stdenv.cc 

            zlib
            glib
            libglvnd
          ];

          shellHook = ''
            cd backend

            export UV_PROJECT_ENVIRONMENT=.venv

            if [ ! -d .venv ]; then
              uv venv .venv --python ${pkgs.python310}/bin/python3.10
            fi

            source .venv/bin/activate

            export LD_LIBRARY_PATH="${
              pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc   # cũng sửa luôn ở đây
                pkgs.zlib
                pkgs.glib
                pkgs.libglvnd
              ]
            }:$LD_LIBRARY_PATH"
          '';
        };
      });
}