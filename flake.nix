{
  description = "Nix packaging and local dev tooling for compotes + its REST extras";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
    # compotes' own `main` is a pristine mirror of nim65s/main (the events
    # feature is proposed upstream from the events-upstream branch instead,
    # carrying no REST/Nix additions of its own). `extras-base` is the
    # branch that actually has compotes-rest-api wired in (INSTALLED_APPS,
    # urls.py, pyproject.toml) - fetch that explicitly, not the default
    # branch, or a future `nix flake update` would silently point this at
    # the clean, REST-less main and break the build.
    compotes-src = {
      url = "github:MaximilienNaveau/compotes/extras-base";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      poetry2nix,
      flake-utils,
      compotes-src,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python3;

        # This poetry2nix snapshot's vendored manylinux tag table
        # (vendor/pyproject.nix/lib/pep599.nix) is missing a `riscv64` entry,
        # and pep600.nix indexes it unsafely (`.${tagArch}` instead of
        # `.${tagArch} or null`), so it hard-crashes as soon as any package's
        # lockfile metadata lists a riscv64-tagged wheel (e.g. ruff). Patch
        # the vendored copy rather than waiting on an upstream fix.
        # Separately: removeGitDependenciesHook (hooks/default.nix) strips
        # git/branch/rev/tag from a git-sourced [tool.poetry.dependencies]
        # entry before poetry-core builds a wheel, but not `subdirectory` -
        # compotes' own compotes-rest-api dependency uses subdirectory (it
        # lives in a sub-path of this repo), so the leftover
        # {subdirectory = ..., version = "*"} fails poetry-core's dependency
        # schema validation ("must be valid exactly by one definition").
        poetry2nixPatchedSrc = pkgs.runCommand "poetry2nix-patched-src" { } ''
          cp -r ${poetry2nix} $out
          chmod -R u+w $out
          substituteInPlace $out/vendor/pyproject.nix/lib/pep600.nix \
            --replace-fail \
              'pep599.manyLinuxTargetMachines.''${tagArch} != platform.parsed.cpu.name' \
              '(pep599.manyLinuxTargetMachines.''${tagArch} or null) != platform.parsed.cpu.name'
          substituteInPlace $out/hooks/default.nix \
            --replace-fail \
              '[ "git" "branch" "rev" "tag" ]' \
              '[ "git" "branch" "rev" "tag" "subdirectory" ]'
        '';
        p2n = import (poetry2nixPatchedSrc + "/default.nix") { inherit pkgs; };
        inherit (p2n) mkPoetryApplication mkPoetryEnv overrides;

        poetryOverrides = overrides.withDefaults (
          final: prev: {
            # compotes-rest-api is a git dependency (not in poetry2nix's
            # curated build-systems.json), so its own build backend
            # (poetry-core, per its pyproject.toml) isn't auto-detected.
            compotes-rest-api = prev.compotes-rest-api.overridePythonAttrs (old: {
              nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.poetry-core ];
            });
          }
        );

        commonArgs = {
          projectDir = compotes-src;
          inherit python;
          overrides = poetryOverrides;
          # poetry2nix defaults to sdist over wheels; several deps' sdists
          # (e.g. gunicorn's pyproject.toml license = "MIT" string) fail
          # newer setuptools' stricter PEP 639 validation. Wheels also
          # avoid needing native build inputs for C-extension packages.
          preferWheels = true;
        };
      in
      {
        packages.default = mkPoetryApplication (
          commonArgs
          // {
            # main (always-on deps) + prod (gunicorn, psycopg2) - what's
            # actually needed to run compotes, as opposed to lint/test tools.
            groups = [
              "main"
              "prod"
            ];
            # Skip poetry2nix's check phase: it pulls in dev-group tools
            # (e.g. ruff) to run project tests as part of the Nix build, but
            # compotes' tests already run via its own CI/manage.py test, not
            # via Nix, and nixpkgs doesn't have a pinned build hash for our
            # exact ruff version (a Rust tool, built from source otherwise).
            checkGroups = [ ];
            doCheck = false;
          }
        );

        devShells.default = pkgs.mkShell {
          packages = [
            (mkPoetryEnv (
              commonArgs
              // {
                # Matches compotes CI's `poetry install --with dev` (main +
                # dev, no prod-only gunicorn/psycopg2 - local dev uses
                # sqlite; see process-compose.yaml).
                groups = [
                  "main"
                  "dev"
                ];
              }
            ))
            pkgs.poetry
            pkgs.process-compose
          ];
          # compotes-src is a read-only /nix/store path (fetched, not a live
          # checkout - by design, compotes carries no Nix files of its own).
          # process-compose.yaml's commands cd there and redirect the sqlite
          # DB to a writable /tmp path.
          shellHook = ''
            export COMPOTES_SRC=${compotes-src}
          '';
        };
      }
    );
}
