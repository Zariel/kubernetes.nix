# kubernetes.nix

`kubernetes.nix` is an append-only catalogue of versioned Kubernetes packages for Nix and NixOS. Each attribute stays on one Kubernetes minor and follows only that minor's newest stable patch:

```nix
pkgs.kubernetes_1_33
pkgs.kubernetes_1_34
pkgs.kubernetes_1_35
pkgs.kubernetes_1_36
```

The operating model is intentionally simple:

> The catalogue updates automatically. Hosts upgrade deliberately.

This is aimed at kubeadm-managed nodes, where changing Kubernetes minors must be coordinated with version-skew rules, etcd snapshots, CNI and storage compatibility, control-plane upgrades, and kubelet restarts. Following nixpkgs's moving default can change a host package before that lifecycle work is planned; selecting `pkgs.kubernetes_1_36` cannot move the host to 1.37.

## Use as a flake input

The following consumer `flake.nix` makes this repository follow the host's nixpkgs input and applies its overlay to a NixOS system:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    kubernetes-nix = {
      url = "github:Zariel/kubernetes.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    { nixpkgs, kubernetes-nix, ... }:
    {
      nixosConfigurations.kubernetes-node = nixpkgs.lib.nixosSystem {
        modules = [
          {
            nixpkgs.hostPlatform = "x86_64-linux";
            nixpkgs.overlays = [ kubernetes-nix.overlays.default ];
          }
          ./configuration.nix
        ];
      };
    };
}
```

Then select one minor in `configuration.nix`:

```nix
{ pkgs, ... }:

let
  k8s = pkgs.kubernetes_1_36;
in
{
  environment.systemPackages = [
    k8s.kubeadm
    k8s.kubectl
    pkgs.cri-tools
  ];

  services.kubernetes.kubelet = {
    enable = true;
    package = k8s.kubelet;
  };
}
```

If a system constructs and passes its own `pkgs` instance to `nixosSystem`, add the overlay to that nixpkgs import instead. Alternatively, use the flake packages directly through `inputs.kubernetes-nix.packages.${pkgs.system}`.

Every version set contains four derivations:

```nix
pkgs.kubernetes_1_36.kubeadm
pkgs.kubernetes_1_36.kubelet
pkgs.kubernetes_1_36.kubectl
pkgs.kubernetes_1_36.kubernetes # bundle containing all three binaries
```

The same attributes are available from the flake:

```bash
nix build .#kubernetes_1_36.kubeadm
nix build .#kubernetes_1_36.kubelet
nix build .#kubernetes_1_36.kubectl
```

The supported evaluation platforms are `x86_64-linux` and `aarch64-linux`. CI builds the changed minors on `x86_64-linux`; the weekly full run rebuilds every catalogue entry.

## Upgrade policy

Patch releases are proposed by Renovate. The custom manager is limited to patch updates, refreshes the Nix source hash in the same commit, and CI rejects any version that does not match its filename and `minor` field. Once CI validates and builds all three binaries, the automation PR is squash-merged.

New stable minors are found daily from the upstream Kubernetes GitHub releases API. Discovery adds a new `versions/1.X.json`, calculates its real source hash, and opens an automerge PR. Existing files are never renamed or deleted, and CI compares PRs with their base revision to enforce that append-only rule.

Changing host minors remains an explicit configuration edit:

```diff
-  k8s = pkgs.kubernetes_1_35;
+  k8s = pkgs.kubernetes_1_36;
```

Before applying that change, follow the Kubernetes kubeadm upgrade documentation and version-skew policy. At minimum, take and verify an etcd snapshot, check CNI/CSI and add-on compatibility, run `kubeadm upgrade plan`, upgrade the control plane, update/restart kubelet, and validate workloads. This repository packages binaries; it does not run kubeadm, manage `/etc/kubernetes`, install a CNI, snapshot etcd, or manage cluster objects.

## Automation setup

The workflows authenticate as a dedicated GitHub App, following the same short-lived installation-token pattern used by `Zariel/home-ops`. Add these repository secrets:

- `BOT_APP_ID`: the GitHub App ID.
- `BOT_APP_PRIVATE_KEY`: a private key for the installed app.

Grant the app read/write access to repository contents, pull requests, issues, commit statuses, workflows, and Actions. Each workflow mints a token scoped to this repository; the action revokes it at job completion. App-authored PR and push events trigger CI normally, unlike changes made with the repository's built-in `GITHUB_TOKEN`.

The workflows create their required labels idempotently. The `main` branch requires a pull request and the stable `CI passed` gate; direct pushes are rejected. The merge workflow only accepts a passing `CI` run for the exact head commit, the `automerge` label, and a `renovate/` or `automation/` source branch. If an automation PR falls behind `main`, the workflow updates its branch and waits for CI to pass again before merging. GitHub deletes merged head branches automatically.

Automation is split into four workflows:

- `Renovate` runs daily. It updates patches, refreshes hashes, maintains `flake.lock` daily against `nixpkgs-unstable`, and updates Actions.
- `Discover new Kubernetes minors` runs daily and adds only minors newer than the current highest catalogue entry.
- `CI` validates JSON and append-only history, checks the flake, builds changed minors, and verifies the reported kubeadm, kubelet, and kubectl versions. Pushes, schedules, and manual runs build the full matrix.
- `Merge passing automation PRs` merges only labelled automation branches after CI succeeds.

Renovate runs from the repository's locked nixpkgs input, so its executable is reproducible and normally substituted from `cache.nixos.org`. Running it directly on the Actions host keeps Nix available to the post-upgrade hash task. The command allowlist permits only `python3 scripts/update-hashes.py --changed`.

## Binary cache

Prebuilt packages are published to the public `zariel` Cachix cache. NixOS consumers can enable it declaratively:

```nix
{
  nix.settings = {
    extra-substituters = [ "https://zariel.cachix.org" ];
    extra-trusted-public-keys = [
      "zariel.cachix.org-1:dh6rKTuFoqFU6PW4VWKtaTPXMXzOLUeThjOKi3Yps48="
    ];
  };
}
```

On other Nix systems with Cachix installed, run `cachix use zariel`. The cache is optional; Nix builds locally when a substitute is unavailable. Cache hits require the package derivation inputs to match, so consumers that make this flake follow a different nixpkgs revision may still need to build locally.

## Local development

```bash
python3 scripts/validate-versions.py
python3 -m unittest discover -s tests -v
nix flake check
nix build .#kubernetes_1_36.kubeadm
python3 scripts/list-upstream-releases.py
python3 scripts/add-new-minor.py
python3 scripts/update-hashes.py --changed
```

`update-hashes.py` uses `nix store prefetch-file --unpack`, so it writes the exact recursive hash expected by `fetchFromGitHub`. Kubernetes releases vendor their Go dependencies; `vendorHash` is therefore deliberately `null`, matching the nixpkgs packaging approach.

## Catalogue support

The catalogue is append-only, not a promise that upstream supports old minors forever. Kubernetes end-of-life entries remain addressable and are still exercised by the scheduled build. If an old release becomes incompatible with a future nixpkgs toolchain, it will be marked broken through an explicit policy change rather than silently deleted or repointed.
