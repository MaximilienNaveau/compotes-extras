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

        # Matches compotes CI's `poetry install --with dev` (main + dev, no
        # prod-only gunicorn/psycopg2 - the dev instance uses sqlite by
        # default; see process-compose.yaml/.env.example for postgres).
        devPythonEnv = mkPoetryEnv (
          commonArgs
          // {
            groups = [
              "main"
              "dev"
            ];
          }
        );

        # main (always-on deps) + prod (gunicorn, psycopg2) - what compotes
        # actually needs to run, as opposed to lint/test tools. This is the
        # prod-appropriate build: apps.prod/devShells.prod run it via
        # gunicorn, not manage.py runserver (which the dev loop uses).
        prodApp = mkPoetryApplication (
          commonArgs
          // {
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

        # A process-compose wrapper factory: bakes in $COMPOTES_SRC, a
        # given python env + extra tools, and a given process-compose.yaml,
        # so `nix run .#<name>` alone starts the instance. -f/--config is
        # only a valid flag for `up` (or no subcommand, which defaults to
        # it) - client-only subcommands like `down`/`attach` just talk to
        # the already-running server via its port and reject -f outright
        # ("unknown shorthand flag"), hence the case split.
        mkServer =
          {
            name,
            pythonEnv,
            extraPackages ? [ ],
            configFile,
          }:
          pkgs.writeShellApplication {
            inherit name;
            runtimeInputs = [
              pythonEnv
              pkgs.process-compose
            ] ++ extraPackages;
            text = ''
              export COMPOTES_SRC=${compotes-src}
              # process-compose.prod.yaml's traefik process cd's here before
              # running traefik, so traefik.yml's relative `filename:
              # ./dynamic.yml` resolves regardless of the caller's own CWD
              # (dev/, prod/, or the repo root - all valid places to run
              # `nix run` from).
              export FLAKE_SRC=${./.}
              case "''${1:-}" in
                up|"")
                  exec process-compose -f ${configFile} "$@"
                  ;;
                *)
                  exec process-compose "$@"
                  ;;
              esac
            '';
          };

        # dev/ has a ready-made .env; nix run .#dev (or -- up -D / -- down):
        # migrate + manage.py runserver, sqlite.
        devServer = mkServer {
          name = "compotes-dev-server";
          pythonEnv = devPythonEnv;
          configFile = ./process-compose.yaml;
        };

        # prod/ has a ready-made .env; nix run .#prod (or -- up -D / -- down):
        # migrate + gunicorn + (a local testing-only) traefik - see
        # process-compose.prod.yaml and prod/README.md.
        prodServer = mkServer {
          name = "compotes-prod-server";
          pythonEnv = prodApp.dependencyEnv;
          extraPackages = [ pkgs.traefik ];
          configFile = ./process-compose.prod.yaml;
        };

        devApp = {
          type = "app";
          program = "${devServer}/bin/compotes-dev-server";
        };
        prodRunApp = {
          type = "app";
          program = "${prodServer}/bin/compotes-prod-server";
        };
      in
      {
        packages.default = prodApp;

        apps.default = devApp;
        apps.dev = devApp;
        apps.prod = prodRunApp;

        devShells.default = pkgs.mkShell {
          packages = [
            devPythonEnv
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

        # gunicorn/psycopg2, no dev tools - for interactive poking (e.g.
        # `manage.py shell`) in a prod-like env. `nix run .#prod` above is
        # the actual entrypoint for running the instance itself.
        devShells.prod = pkgs.mkShell {
          packages = [
            prodApp.dependencyEnv
            pkgs.process-compose
            pkgs.traefik
          ];
          shellHook = ''
            export COMPOTES_SRC=${compotes-src}
          '';
        };
      }
    );
}
