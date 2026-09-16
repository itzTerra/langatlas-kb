R4 debate records (`<debate-id>.yaml`): proposer, two challengers, moderator
resolution, typed challenges. Written by the debate machinery (Stage 3C); read by
the controversy assessor (Stage 3D) and the D30 instrumentation scripts.
`draft debate` writes a record but does not commit it: the records are landed by
`draft finalize`, together with the carve plan whose conclusions they are.
