_final: prev:

let
  catalogue = import ../nix/lib.nix {
    inherit (prev) lib;
    versionsDir = ../versions;
  };
in
builtins.mapAttrs (
  _name: versionData:
  prev.callPackage ../pkgs/kubernetes/default.nix {
    inherit versionData;
  }
) catalogue
