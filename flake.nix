{
  description = "Lean dev shell: Expo + Python (FastAPI + ML)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
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
            # Expo
            nodejs

            # Python
            python312
            uv

            # đủ để opencv / onnxruntime không chết
            stdenv.cc.cc
            zlib
            glib
            libglvnd
          ];

          shellHook = ''
            export UV_PROJECT_ENVIRONMENT=.venv

            if [ ! -d .venv ]; then
              uv venv .venv --python ${pkgs.python312}/bin/python3.12
            fi

            source .venv/bin/activate

            export LD_LIBRARY_PATH="${
              pkgs.lib.makeLibraryPath [
                pkgs.stdenv.cc.cc
                pkgs.zlib
                pkgs.glib
                pkgs.libglvnd
              ]
            }:$LD_LIBRARY_PATH"

            echo "ready"
          '';
        };
      });
}