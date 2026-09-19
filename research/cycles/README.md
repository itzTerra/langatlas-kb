One file per theme cycle (`<NN>-<theme>.yaml`): the developer's sign-off, the
cycle's rotating R5 language sample, its status, and the node ids it minted.
Written by `langatlas-research cycle`; read by every R3-R6 runner and by
`coverage report.py dossier`.
A cycle becomes `settled` only through `langatlas-research consolidate settle` (the developer's
act, recorded as `settled: {by, date}`); from then on CI refuses an unmanifested restructure of
any record the cycle minted.
