# Standalone deployment example

No local `flake.nix` needed here — `nix run` can reference a flake straight
from GitHub, so an empty directory with just a `.env` file is enough:

```sh
mkdir my-compotes && cd my-compotes
cp path/to/.env.example .env   # or copy the one from this folder
$EDITOR .env                    # at minimum, set SECRET_KEY if DEBUG=False

nix run github:MaximilienNaveau/compotes-extras -- up -D
```

`process-compose` loads `.env` from the current directory automatically —
nothing else needs to know it exists. This is the same recipe as the [`dev/`
folder](../dev), just pointed at the published repo (`github:...`) instead
of a local checkout (`..`), for running this on a machine that doesn't have
the source cloned. See the root [`.env.example`](../.env.example) for every
supported variable, and the [README](../README.md#nix-packaging--local-dev-instance)
for start/stop/update commands — they're identical either way, only the
flake reference differs (`..` vs `github:MaximilienNaveau/compotes-extras`).

The `.env.example` in this folder is the same file, geared towards an
actual deployment rather than local dev — `DEBUG=False` needs a real
`SECRET_KEY`, and you'll likely want `DB=postgres` pointed at a real
database rather than the sqlite default.
