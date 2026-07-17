{
  description = "Nix packaging and local dev tooling for compotes + its REST extras";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    poetry2nix = {
      url = "github:nix-community/poetry2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      poetry2nix,
      flake-utils,
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
        # not needed by our own git dependency below (compotes has no
        # subdirectory), but harmless to keep patched in case a future
        # dependency needs it.
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
            # compotes is a git dependency (not in poetry2nix's curated
            # build-systems.json), so its own build backend (poetry-core,
            # per its pyproject.toml) isn't auto-detected.
            compotes = prev.compotes.overridePythonAttrs (old: {
              nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [ final.poetry-core ];
            });
          }
        );

        # packages/rest_api is the one place the full stack (compotes +
        # compotes_rest_api + compotes_extras_site) is actually assembled -
        # everything starts from here, not from a fetched compotes source
        # tree. compotes has no Nix files and no knowledge of any of this.
        commonArgs = {
          projectDir = ./packages/rest_api;
          inherit python;
          overrides = poetryOverrides;
          # poetry2nix defaults to sdist over wheels; several deps' sdists
          # (e.g. gunicorn's pyproject.toml license = "MIT" string) fail
          # newer setuptools' stricter PEP 639 validation. Wheels also
          # avoid needing native build inputs for C-extension packages.
          preferWheels = true;
        };

        # Matches this package's own CI (`poetry install --with dev`): main
        # + dev, no prod-only gunicorn/psycopg2 - the dev instance runs
        # `runserver` against sqlite, not gunicorn.
        #
        # mkPoetryApplication, not mkPoetryEnv: mkPoetryEnv only installs
        # *dependencies*, not this project's own packages
        # (compotes_rest_api/compotes_extras_site) - caught by actually
        # running `nix run .#dev`, which failed with `ModuleNotFoundError:
        # No module named 'compotes_extras_site'` under mkPoetryEnv.
        devPythonEnv =
          (mkPoetryApplication (
            commonArgs
            // {
              groups = [
                "main"
                "dev"
              ];
              checkGroups = [ ];
              doCheck = false;
            }
          )).dependencyEnv;

        # main + prod (gunicorn, psycopg2) - what's actually needed to run
        # the full stack for real, as opposed to lint/test tools.
        prodApp = mkPoetryApplication (
          commonArgs
          // {
            groups = [
              "main"
              "prod"
            ];
            # Skip poetry2nix's check phase: it pulls in dev-group tools
            # (e.g. ruff) to run this package's tests as part of the Nix
            # build, but those already run via CI/manage.py test, not via
            # Nix, and nixpkgs doesn't have a pinned build hash for our
            # exact ruff version (a Rust tool, built from source otherwise).
            checkGroups = [ ];
            doCheck = false;
          }
        );

        # A process-compose wrapper factory: bakes in a given python env +
        # extra tools and a given process-compose.yaml, so `nix run
        # .#<name>` alone starts the instance. -f/--config is only a valid
        # flag for `up` (or no subcommand, which defaults to it) -
        # client-only subcommands like `down`/`attach` just talk to the
        # already-running server via its port and reject -f outright
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
        # migrate + runserver, sqlite.
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
        };

        # gunicorn/psycopg2, no dev tools - for interactive poking (e.g.
        # `python -m django shell`) in a prod-like env. `nix run .#prod`
        # above is the actual entrypoint for running the instance itself.
        devShells.prod = pkgs.mkShell {
          packages = [
            prodApp.dependencyEnv
            pkgs.process-compose
            pkgs.traefik
          ];
        };
      }
    );
}
