# langatlas-research

Stage 3's research spine: theme cycles, the developer sign-off gate, and the node-minting path.

## What this package is for

Every Stage 3 agent role — surveyor (3B), ontologist and edge drafter (3C), reality checker
(3E) — ends by handing a **draft** to this package. Drafts are dumb data; this package turns
one into a validated, normalized record at its `context/spec.md` §3.3 path and lands it through
the D36 commit protocol, one commit per record.

No model is called anywhere in this package. That is deliberate: the minting rules are the part
of Stage 3 that must be deterministic and testable without a provider.

## The gate

`require_sign_off(cycle)` is D27's hard checkpoint — the developer signs off a cycle's theme
before anything runs. The sign-off is bound to a digest of the theme text, so editing the theme
afterwards re-opens the gate rather than silently inheriting it. Nothing technically prevents an
agent from writing a sign-off block; the gate is a checkpoint artifact the developer reads in a
diff, not an ACL.

## Commands

```
langatlas-research init                       # create research/
langatlas-research themes list
langatlas-research cycle new 1 typing         # draft cycle 1, plan its R5 language sample
langatlas-research cycle sign-off 1           # the developer checkpoint
langatlas-research cycle status
langatlas-research cycle advance 1 --to r3-done
langatlas-research validate                   # every research artifact against its schema
```

## Tests

```
uv --directory tools/research sync --extra dev
uv --directory tools/research run pytest -m ''   # `git`-marked tests build throwaway repos
```
