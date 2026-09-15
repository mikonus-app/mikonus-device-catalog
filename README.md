# Mikonus Device Capability Catalog

This repository contains the public Mikonus Device Capability Catalog.

- `stable.json` contains curated, confirmed rules for normal use.
- `beta.json` contains new mappings awaiting confirmation for testers and early access. It may change more frequently.

All published catalogs must use Schema 2. Schema 1 is obsolete and must never be
used as a rollback target.

## Channels and versions

Stable contains reviewed rules for normal use. Beta contains new mappings awaiting
confirmation and may change more frequently. The files have independent,
non-empty `catalogVersion` values. Use a unique, monotonically advancing value for
every channel change, for example `stable-schema2-bootstrap-1` and
`beta-schema2-bootstrap-1`.

## Validation and review

Every pull request must pass the validator and its tests. CI always checks both
catalogs, even when only one changed. Review must confirm that rules match the
Schema-2 app contract and contain no personal data, credentials, tokens, local
URLs, or user identifiers.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/validate_catalog.py stable.json beta.json
```

## Promotion and rollback

Promote Beta to Stable through a reviewed pull request: copy only confirmed rules
into `stable.json` and assign Stable a new unique `catalogVersion`. Beta and Stable
versions must remain distinct.

To roll back, restore a previously reviewed **Schema-2** catalog as a new commit
and assign a new `catalogVersion`, so clients recognize the change. Never roll
back either channel to Schema 1.

The catalog contains technical mapping rules only. It must not contain personal data, tokens, local URLs, or user IDs.

Custom and manufacturer-specific behavior belongs in this catalog. Official provider-standard semantics belong in the Mikonus baseline.
