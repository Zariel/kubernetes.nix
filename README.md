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

## Use the overlay

Add the flake and make it follow the host's nixpkgs input:

```nix
{
  inputs.kubernetes-nix.url = "github:Zariel/kubernetes.nix";
  inputs.kubernetes-nix.inputs.nixpkgs.follows = "nixpkgs";
}
```

Then install its overlay and select one minor:

```nix
{ inputs, pkgs, ... }:

let
  k8s = pkgs.kubernetes_1_36;
in
{
  nixpkgs.overlays = [
    inputs.kubernetes-nix.overlays.default
  ];

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

Because NixOS module arguments are evaluated before option definitions, ensure the overlay is applied in the system's nixpkgs construction (or through a module imported before `pkgs` is created). If that is awkward, use the flake packages directly through `inputs.kubernetes-nix.packages.${pkgs.system}`.

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

The workflows create their required labels idempotently. The `main` branch requires a pull request and the stable `CI passed` gate; direct pushes are rejected. The merge workflow only accepts a passing `CI` run for the exact head commit, the `automerge` label, and a `renovate/` or `automation/` source branch.

Automation is split into four workflows:

- `Renovate` runs daily. It updates patches, refreshes hashes, maintains `flake.lock` daily against `nixpkgs-unstable`, and updates Actions.
- `Discover new Kubernetes minors` runs daily and adds only minors newer than the current highest catalogue entry.
- `CI` validates JSON and append-only history, checks the flake, and builds changed minors. Pushes, schedules, and manual runs build the full matrix.
- `Merge passing automation PRs` merges only labelled automation branches after CI succeeds.

Renovate is self-hosted in Actions because its post-upgrade task needs Nix to calculate source hashes. The command allowlist permits only `python3 scripts/update-hashes.py --changed`.

## Binary cache

The normal Nix cache remains enabled. To use Cachix for these relatively expensive builds, set the repository variable `CACHIX_CACHE_NAME`. CI and fork pull requests can then read from a public cache without a secret. Add the `CACHIX_AUTH_TOKEN` repository secret to publish successful builds from trusted branches and same-repository automation PRs. Consumers can configure the cache documented by that Cachix instance as an extra substituter and trusted public key. A binary cache is recommended but not required; GitHub's generic dependency cache is deliberately not used for `/nix/store`.

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
