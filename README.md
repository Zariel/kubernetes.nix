# kubernetes.nix

Versioned Kubernetes packages for Nix and NixOS:

```nix
pkgs.kubernetes_1_35
pkgs.kubernetes_1_36
```

Each attribute stays on one Kubernetes minor and tracks only its newest stable
patch release. There is no moving `pkgs.kubernetes` alias.

> The catalogue updates automatically. Hosts upgrade deliberately.

This is intended for kubeadm-managed nodes, where minor upgrades must be
coordinated with Kubernetes version-skew rules, etcd snapshots, CNI/CSI
compatibility, control-plane upgrades, and kubelet restarts.

## Use with NixOS

Add the flake, make it follow the host's nixpkgs input, and apply its overlay:

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

Select a Kubernetes minor in `configuration.nix` and use the matching tools
together:

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

If your system passes its own `pkgs` instance to `nixosSystem`, add
`kubernetes-nix.overlays.default` to that nixpkgs import instead.

## Package sets

Every minor exposes:

```nix
pkgs.kubernetes_1_36.kubeadm
pkgs.kubernetes_1_36.kubelet
pkgs.kubernetes_1_36.kubectl
pkgs.kubernetes_1_36.kubernetes # bundle containing all three binaries
```

The same attributes can be built directly from the flake:

```bash
nix build github:Zariel/kubernetes.nix#kubernetes_1_36.kubeadm
nix build github:Zariel/kubernetes.nix#kubernetes_1_36.kubelet
nix build github:Zariel/kubernetes.nix#kubernetes_1_36.kubectl
```

## Binary cache

Prebuilt packages are published to the public `zariel` Cachix cache. Enable it
declaratively on NixOS:

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

On other Nix systems with Cachix installed, run `cachix use zariel`. The cache
is optional; Nix builds locally when no matching substitute exists. Consumers
following a different nixpkgs revision may produce different derivations and
miss the cache.

## Upgrades

Patch updates remain within the selected minor. New stable minors appear as new
attributes without changing existing consumers.

A minor upgrade is an explicit configuration change:

```diff
-  k8s = pkgs.kubernetes_1_35;
+  k8s = pkgs.kubernetes_1_36;
```

Before rebuilding the host, follow the upstream
[kubeadm upgrade guide](https://kubernetes.io/docs/tasks/administer-cluster/kubeadm/kubeadm-upgrade/)
and [version-skew policy](https://kubernetes.io/releases/version-skew-policy/).
Take and verify an etcd snapshot, check CNI/CSI and add-on compatibility,
upgrade the control plane, update or restart kubelet, and validate workloads.

## Scope and support

This repository packages Kubernetes binaries. It does not run kubeadm, manage
`/etc/kubernetes`, install a CNI, manage cluster objects, or take etcd
snapshots.

`x86_64-linux` packages are built and executed in CI. `aarch64-linux` is
exposed and evaluated but is not currently built in CI.

The catalogue is append-only, but not a promise of indefinite upstream support.
Historical attributes are not silently deleted or moved to another minor; an
incompatible old release may instead be marked broken through an explicit
policy change.
