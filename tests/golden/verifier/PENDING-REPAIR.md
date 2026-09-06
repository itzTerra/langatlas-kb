# 2B golden-set rework — remaining manual-review items

Auto-repaired: 93 of 219 verifier items (82 clean single-match + 11 overlap-boundary
resolved), propagating to 30 of 40 stale retrieval golden entries. This file lists
everything still needing human judgment.

Total remaining: 126 verifier items, 10 retrieval entries.

## Retrieval golden set — still stale (10 entries)

These map to the hardest verifier items below (same underlying evidence chunk).
Fixing the verifier item first, then re-deriving/repairing these, closes both at once.

- `queries-concepts.yaml` `paraphrase-001`: `['vanroy-haridi-2003#c00071']`
- `queries-concepts.yaml` `paraphrase-003`: `['sebesta-copl#c00837']`
- `queries-concepts.yaml` `paraphrase-006`: `['sebesta-copl#c00887']`
- `queries-concepts.yaml` `paraphrase-008`: `['sebesta-copl#c00772']`
- `queries-concepts.yaml` `paraphrase-011`: `['rust-fls#c01034']`
- `queries-concepts.yaml` `paraphrase-014`: `['sebesta-copl#c00895']`
- `queries-derived.yaml` `retrieval-derived-011`: `['sebesta-copl#c00772']`
- `queries-derived.yaml` `retrieval-derived-013`: `['sebesta-copl#c00837']`
- `queries-derived.yaml` `retrieval-derived-017`: `['sebesta-copl#c00887']`
- `queries-derived.yaml` `retrieval-derived-020`: `['rust-fls#c01034']`

## Verifier items by failure reason

### OCR-noise items (8) — deliberately garbled quotes, need semantic re-identification, not exact-match

These items exist specifically to test OCR-noise tolerance; their `citation.quote` is an
intentional corruption (e.g. rn→m, ii→ii/ci confusion) and will never substring-match the
real corpus text. Repair by reading the claim and finding the real passage by hand.

- `items-ocr-and-diversity.yaml` `v-ocr-0001`: current `['vanroy-haridi-2003#c00255']`
- `items-ocr-and-diversity.yaml` `v-ocr-0002`: current `['vanroy-haridi-2003#c00349']`
- `items-ocr-and-diversity.yaml` `v-ocr-0003`: current `['vanroy-haridi-2003#c00110']`
- `items-ocr-and-diversity.yaml` `v-ocr-0004`: current `['haskell-2010-report#c00080']`
- `items-ocr-and-diversity.yaml` `v-ocr-0005`: current `['c23-n3220#c00277']`
- `items-ocr-and-diversity.yaml` `v-ocr-0006`: current `['rust-fls#c01034']`
- `items-ocr-and-diversity.yaml` `v-ocr-0007`: current `['jls-se25#c00262']`
- `items-ocr-and-diversity.yaml` `v-ocr-0008`: current `['ghc-users-guide#c00443']`

### No quote to match against (79)

Items with no `citation.quote` field — often siblings of a quote-bearing item pointing at
the same old chunk (a shared passage supporting several claims). Check whether the sibling
with a quote was resolved above; if so the same new id likely applies here too, pending
human confirmation the claim is still actually supported by that passage's new boundaries.

- `items-absence-3.yaml` `v-py-core-0001`: current `['scott-plp#c00417']`
- `items-absence-3.yaml` `v-py-core-0002`: current `['scott-plp#c00417']`
- `items-absence-3.yaml` `v-c-core-0006`: current `['scott-plp#c00304']`
- `items-absence-4.yaml` `v-java-core-0011`: current `['scott-plp#c00282']`
- `items-absence-4.yaml` `v-ruby-core-0001`: current `['scott-plp#c00642']`
- `items-absence-4.yaml` `v-ml-core-0002`: current `['scott-plp#c00434']`
- `items-ada-overview.yaml` `v-ada-core-0009`: current `['sebesta-copl#c00156']`
- `items-ada-overview.yaml` `v-ada-core-0010`: current `['sebesta-copl#c00156']`
- `items-ada-overview.yaml` `v-ada-core-0011`: current `[]`
- `items-ada-overview.yaml` `v-ada-core-0012`: current `['sebesta-copl#c00156']`
- `items-ada-overview.yaml` `v-ada-core-0015`: current `['sebesta-copl#c00156']`
- `items-concurrency.yaml` `v-java-core-0014`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-java-core-0015`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-java-core-0016`: current `[]`
- `items-concurrency.yaml` `v-java-core-0017`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-ada-core-0003`: current `['sebesta-copl#c00772']`
- `items-exceptions-2.yaml` `v-java-core-0028`: current `['sebesta-copl#c00833']`
- `items-exceptions-2.yaml` `v-java-core-0029`: current `['sebesta-copl#c00833']`
- `items-exceptions-2.yaml` `v-java-core-0030`: current `[]`
- `items-exceptions-2.yaml` `v-java-core-0031`: current `['sebesta-copl#c00833']`
- `items-exceptions-2.yaml` `v-java-core-0034`: current `['sebesta-copl#c00833']`
- `items-exceptions.yaml` `v-py-core-0025`: current `['sebesta-copl#c00837']`
- `items-exceptions.yaml` `v-java-core-0022`: current `['sebesta-copl#c00835']`
- `items-exceptions.yaml` `v-java-core-0023`: current `[]`
- `items-exceptions.yaml` `v-py-core-0026`: current `['sebesta-copl#c00837']`
- `items-exceptions.yaml` `v-cpp-core-0004`: current `['sebesta-copl#c00835']`
- `items-haskell-core.yaml` `v-haskell-core-0005`: current `[]`
- `items-haskell-core.yaml` `v-haskell-core-0007`: current `['haskell-2010-report#c00080']`
- `items-haskell-core.yaml` `v-haskell-core-0008`: current `['haskell-2010-report#c00080']`
- `items-haskell-core.yaml` `v-haskell-core-0009`: current `['haskell-2010-report#c00080']`
- `items-haskell-core.yaml` `v-haskell-core-0013`: current `['vanroy-haridi-2003#c00071']`
- `items-java-core.yaml` `v-java-core-0005`: current `[]`
- `items-java-core.yaml` `v-java-core-0006`: current `['jls-se25#c00487']`
- `items-java-core.yaml` `v-java-core-0007`: current `['jls-se25#c00262']`
- `items-java-core.yaml` `v-java-core-0008`: current `['jls-se25#c00487']`
- `items-ml-scheme-haskell.yaml` `v-ml-core-0007`: current `['sebesta-copl#c00893']`
- `items-ml-scheme-haskell.yaml` `v-scheme-core-0002`: current `['sebesta-copl#c00887']`
- `items-ml-scheme-haskell.yaml` `v-scheme-core-0003`: current `[]`
- `items-ml-scheme-haskell.yaml` `v-ml-core-0008`: current `['sebesta-copl#c00893']`
- `items-ml-scheme-haskell.yaml` `v-ml-core-0009`: current `['sebesta-copl#c00895']`
- `items-ocr-and-diversity.yaml` `v-diversity-0001`: current `['c23-n3220#c00567']`
- `items-ocr-and-diversity.yaml` `v-diversity-0002`: current `['rust-fls#c00751']`
- `items-ocr-and-diversity.yaml` `v-diversity-0003`: current `['scott-plp#c00417']`
- `items-ocr-and-diversity.yaml` `v-diversity-0004`: current `['ghc-users-guide#c00161']`
- `items-ocr-and-diversity.yaml` `v-diversity-0005`: current `['haskell-2010-report#c00023']`
- `items-perl.yaml` `v-perl-core-0007`: current `['sebesta-copl#c00178']`
- `items-perl.yaml` `v-perl-core-0008`: current `['sebesta-copl#c00178']`
- `items-perl.yaml` `v-perl-core-0009`: current `[]`
- `items-perl.yaml` `v-perl-core-0010`: current `['sebesta-copl#c00177']`
- `items-perl.yaml` `v-perl-core-0013`: current `['sebesta-copl#c00178']`
- `items-python-core-2.yaml` `v-py-core-0016`: current `[]`
- `items-python-core-2.yaml` `v-py-core-0017`: current `['python-langref-3#c00206']`
- `items-python-core-2.yaml` `v-py-core-0018`: current `['python-langref-3#c00175']`
- `items-python-core-2.yaml` `v-py-core-0019`: current `['python-langref-3#c00175']`
- `items-python-core-2.yaml` `v-py-core-0022`: current `['python-langref-3#c00206']`
- `items-rust-core.yaml` `v-rust-core-0005`: current `[]`
- `items-rust-core.yaml` `v-rust-core-0006`: current `['rust-reference#c00456']`
- `items-rust-core.yaml` `v-rust-core-0008`: current `['rust-reference#c00456']`
- `items-rust-core.yaml` `v-rust-core-0009`: current `['rust-reference#c00456']`
- `items-rust-core.yaml` `v-rust-core-0010`: current `['rust-reference#c00456']`
- `items-rust-fls.yaml` `v-rustfls-0005`: current `[]`
- `items-rust-fls.yaml` `v-rustfls-0006`: current `['rust-fls#c01034']`
- `items-rust-fls.yaml` `v-rustfls-0007`: current `['rust-fls#c01034']`
- `items-rust-fls.yaml` `v-rustfls-0008`: current `['rust-fls#c01034']`
- `items-rust-fls.yaml` `v-rustfls-0011`: current `['rust-fls#c00751']`
- `items-scripting-langs.yaml` `v-js-core-0004`: current `['sebesta-copl#c00309']`
- `items-scripting-langs.yaml` `v-js-core-0005`: current `['sebesta-copl#c00309']`
- `items-scripting-langs.yaml` `v-js-core-0006`: current `[]`
- `items-scripting-langs.yaml` `v-js-core-0007`: current `['sebesta-copl#c00309']`
- `items-scripting-langs.yaml` `v-ruby-core-0004`: current `['sebesta-copl#c00309']`
- `items-since-and-absence-2.yaml` `v-since-0005`: current `['haskell-2010-report#c00080']`
- `items-since-and-absence-2.yaml` `v-since-0006`: current `['jls-se25#c00487']`
- `items-since-and-absence-2.yaml` `v-c-core-0003`: current `['sebesta-copl#c00051']`
- `items-since-and-absence-2.yaml` `v-c-core-0004`: current `['sebesta-copl#c00702']`
- `items-since-and-absence.yaml` `v-since-0001`: current `['python-langref-3#c00250']`
- `items-since-and-absence.yaml` `v-absent-0001`: current `['c23-n3220#c00277']`
- `items-since-and-absence.yaml` `v-absent-0002`: current `['c23-n3220#c00567']`
- `items-since-and-absence.yaml` `v-c-core-0002`: current `['c23-n3220#c00277']`
- `items-since-and-absence.yaml` `v-ghc-core-0003`: current `[]`

### Quote not found in re-chunked corpus (34)

The quote is real (not OCR-noise) but no chunk in the re-chunked corpus contains it verbatim — likely because the quote was itself a paraphrase in the original 2B curation (pre-existing data-quality gap, not caused by re-chunking) or spans a chunk boundary differently now.

- `items-absence-3.yaml` `v-c-core-0005`: current `['sebesta-copl#c00046']`
- `items-absence-4.yaml` `v-cpp-core-0001`: current `['scott-plp#c00232']`
- `items-ada-overview.yaml` `v-ada-core-0013`: current `['sebesta-copl#c00156']`
- `items-concurrency.yaml` `v-java-core-0012`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-ada-core-0001`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-java-core-0013`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-ada-core-0002`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-java-core-0018`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-java-core-0019`: current `['sebesta-copl#c00772']`
- `items-concurrency.yaml` `v-since-0014`: current `['ghc-users-guide#c00468']`
- `items-exceptions-2.yaml` `v-java-core-0027`: current `['sebesta-copl#c00828']`
- `items-exceptions-2.yaml` `v-java-core-0032`: current `['sebesta-copl#c00833']`
- `items-exceptions-2.yaml` `v-since-0016`: current `['ghc-users-guide#c00469']`
- `items-exceptions.yaml` `v-py-core-0024`: current `['sebesta-copl#c00837']`
- `items-exceptions.yaml` `v-java-core-0024`: current `['sebesta-copl#c00835']`
- `items-exceptions.yaml` `v-py-core-0027`: current `['sebesta-copl#c00837']`
- `items-haskell-core.yaml` `v-haskell-core-0010`: current `['haskell-2010-report#c00080']`
- `items-haskell-core.yaml` `v-haskell-core-0012`: current `['vanroy-haridi-2003#c00071']`
- `items-java-core.yaml` `v-java-core-0009`: current `['jls-se25#c00487']`
- `items-ml-scheme-haskell.yaml` `v-scheme-core-0001`: current `['sebesta-copl#c00887']`
- `items-ml-scheme-haskell.yaml` `v-ml-core-0006`: current `['sebesta-copl#c00898']`
- `items-ml-scheme-haskell.yaml` `v-haskell-core-0016`: current `['sebesta-copl#c00898']`
- `items-ml-scheme-haskell.yaml` `v-scheme-core-0004`: current `['sebesta-copl#c00887']`
- `items-perl.yaml` `v-perl-core-0001`: current `['sebesta-copl#c00178']`
- `items-perl.yaml` `v-perl-core-0011`: current `['sebesta-copl#c00178']`
- `items-perl.yaml` `v-perl-core-0012`: current `['sebesta-copl#c00178']`
- `items-python-core-2.yaml` `v-py-core-0014`: current `['python-langref-3#c00206']`
- `items-python-core-2.yaml` `v-py-core-0020`: current `['python-langref-3#c00206']`
- `items-rust-core.yaml` `v-rust-core-0007`: current `['rust-reference#c00456']`
- `items-rust-fls.yaml` `v-rustfls-0009`: current `['rust-fls#c01034']`
- `items-rust-fls.yaml` `v-since-0010`: current `['ghc-users-guide#c00468']`
- `items-rust-fls.yaml` `v-rustfls-0013`: current `['ghc-users-guide#c00468']`
- `items-scripting-langs.yaml` `v-js-core-0008`: current `['sebesta-copl#c00309']`
- `items-since-and-absence.yaml` `v-python-core-0002`: current `['python-langref-3#c00250']`

### Ambiguous match (5) — quote appears verbatim in 2+ non-adjacent chunks, needs human pick

- `items-exceptions.yaml` `v-since-0015`: ambiguous match across ['python-langref-3#c00045', 'python-langref-3#c00046'], current `['python-langref-3#c00041']`
- `items-rust-fls.yaml` `v-rustfls-0001`: ambiguous match across ['rust-fls#c00093', 'rust-fls#c01117'], current `['rust-fls#c01034']`
- `items-rust-fls.yaml` `v-rustfls-0003`: ambiguous match across ['rust-fls#c00377', 'rust-fls#c00558'], current `['rust-fls#c00314']`
- `items-rust-fls.yaml` `v-rustfls-0004`: ambiguous match across ['rust-fls#c00377', 'rust-fls#c00773'], current `['rust-fls#c00314']`
- `items-rust-fls.yaml` `v-rustfls-0010`: ambiguous match across ['rust-fls#c00093', 'rust-fls#c01117'], current `['rust-fls#c01034']`
