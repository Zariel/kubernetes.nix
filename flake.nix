{
  description = "Append-only, versioned Kubernetes packages for Nix";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";

  outputs =
    { self, nixpkgs }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      overlays.default = import ./overlays/default.nix;

      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ self.overlays.default ];
          };
          catalogue = import ./nix/lib.nix {
            inherit (pkgs) lib;
            versionsDir = ./versions;
          };
        in
        builtins.mapAttrs (name: _versionData: pkgs.${name}) catalogue
      );

      checks = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          version-catalogue =
            pkgs.runCommand "validate-kubernetes-version-catalogue" { nativeBuildInputs = [ pkgs.python3 ]; }
              ''
                python3 ${./scripts/validate-versions.py} ${./versions}
                touch "$out"
              '';
        }
      );

      formatter = forAllSystems (system: nixpkgs.legacyPackages.${system}.nixfmt);
    };
}
