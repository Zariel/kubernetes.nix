{
  lib,
  buildGoModule,
  fetchFromGitHub,
  runtimeShell,
  which,
  rsync,
  runCommand,
  versionData,
}:

let
  inherit (versionData) version srcHash;

  componentDescriptions = {
    cloud-controller-manager = "Kubernetes cloud controller manager";
    kube-apiserver = "Kubernetes API server";
    kube-controller-manager = "Kubernetes controller manager";
    kube-proxy = "Kubernetes network proxy";
    kube-scheduler = "Kubernetes scheduler";
    kubeadm = "Tool for bootstrapping Kubernetes clusters";
    kubectl = "Kubernetes command-line client";
    kubelet = "Kubernetes node agent";
  };

  componentNames = builtins.attrNames componentDescriptions;

  kubernetes = buildGoModule {
    pname = "kubernetes";
    inherit version;

    src = fetchFromGitHub {
      owner = "kubernetes";
      repo = "kubernetes";
      tag = "v${version}";
      hash = srcHash;
    };

    # Kubernetes releases include a complete vendor tree. This deliberately
    # follows nixpkgs's Kubernetes package rather than re-vendoring modules.
    vendorHash = versionData.vendorHash;

    doCheck = false;
    nativeBuildInputs = [
      which
      rsync
    ];
    env.WHAT = lib.concatMapStringsSep " " (component: "cmd/${component}") componentNames;

    buildPhase = ''
      runHook preBuild
      patchShebangs ./hack
      make "SHELL=${runtimeShell}" "WHAT=$WHAT"
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      for component in ${lib.escapeShellArgs componentNames}; do
        install -D "_output/local/go/bin/$component" "$out/bin/$component"
      done
      runHook postInstall
    '';

    meta = {
      description = "Version-pinned Kubernetes component binaries";
      homepage = "https://kubernetes.io";
      license = lib.licenses.asl20;
      platforms = lib.platforms.linux;
    };
  };

  mkComponent =
    component: description:
    runCommand "${component}-${version}"
      {
        inherit version;
        meta = kubernetes.meta // {
          inherit description;
          mainProgram = component;
        };
      }
      ''
        mkdir -p "$out/bin"
        ln -s "${kubernetes}/bin/${component}" "$out/bin/${component}"
      '';

  componentPackages = lib.mapAttrs mkComponent componentDescriptions;
in
lib.extendDerivation true (
  {
    recurseForDerivations = true;
    inherit kubernetes;
  }
  // componentPackages
) kubernetes
