{ lib, versionsDir }:

let
  entries = builtins.readDir versionsDir;
  versionFiles = lib.filterAttrs (
    name: type: type == "regular" && builtins.match "[0-9]+\\.[0-9]+\\.json" name != null
  ) entries;

  readVersion =
    filename:
    let
      data = builtins.fromJSON (builtins.readFile (versionsDir + "/${filename}"));
      filenameMinor = lib.removeSuffix ".json" filename;
      expectedPrefix = "${data.minor}.";
    in
    assert lib.assertMsg (
      data.minor == filenameMinor
    ) "${filename}: minor must be ${filenameMinor}, got ${data.minor}";
    assert lib.assertMsg (lib.hasPrefix expectedPrefix data.version)
      "${filename}: version ${data.version} is outside minor ${data.minor}";
    data
    // {
      attribute = "kubernetes_${lib.replaceStrings [ "." ] [ "_" ] data.minor}";
    };
in
lib.listToAttrs (
  map (filename: {
    name = (readVersion filename).attribute;
    value = readVersion filename;
  }) (lib.sort builtins.lessThan (builtins.attrNames versionFiles))
)
