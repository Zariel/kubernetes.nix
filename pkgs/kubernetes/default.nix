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
    env.WHAT = "cmd/kubeadm cmd/kubelet cmd/kubectl";

    buildPhase = ''
      runHook preBuild
      patchShebangs ./hack
      make "SHELL=${runtimeShell}" "WHAT=$WHAT"
      runHook postBuild
    '';

    installPhase = ''
      runHook preInstall
      for component in kubeadm kubelet kubectl; do
        install -D "_output/local/go/bin/$component" "$out/bin/$component"
      done
      runHook postInstall
    '';

    meta = {
      description = "Version-pinned Kubernetes command-line tools";
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
in
lib.extendDerivation true {
  recurseForDerivations = true;
  inherit kubernetes;
  kubeadm = mkComponent "kubeadm" "Tool for bootstrapping Kubernetes clusters";
  kubelet = mkComponent "kubelet" "Kubernetes node agent";
  kubectl = mkComponent "kubectl" "Kubernetes command-line client";
} kubernetes
