"""D52's `gaps`: corroborating instances per `<dimension, value>`, where a value is a member
feature (D67). Report-only — crossing `--min-instances` triggers nothing — and one threshold
for every dimension, deliberately (D52: no per-dimension override)."""
from langatlas_coverage.metrics import Store, dimension_members, instance_counts

DEFAULT_MIN_INSTANCES = 2
CAVEAT = ("Advisory only (D52). This metric is near-meaningless before D28 phase 1 completes:"
          " instances arrive with Stage 5's sweeps, and R5 reality checks mint none (D68).")


def gaps(store: Store, *, min_instances: int = DEFAULT_MIN_INSTANCES) -> list[dict]:
    counts = instance_counts(store)
    rows = []
    for dimension, members in sorted(dimension_members(store).items()):
        for feature in members:
            count = counts.get(feature, {})
            corroborating = count.get("present", 0) + count.get("partial", 0)
            rows.append({"dimension": dimension, "value": feature,
                         "present": count.get("present", 0),
                         "partial": count.get("partial", 0),
                         "corroborating": corroborating,
                         "thin": corroborating < min_instances})
    return rows


def render_gaps(rows: list[dict], *, min_instances: int, instances_total: int) -> str:
    lines = [f"# Coverage gaps (--min-instances {min_instances})", "", CAVEAT, ""]
    if not instances_total:
        lines += ["No FeatureInstance records yet — every value below is thin by construction.",
                  ""]
    lines += ["| dimension | value | present | partial | corroborating | |",
              "|---|---|---:|---:|---:|---|"]
    for row in rows:
        lines.append(f"| {row['dimension']} | {row['value']} | {row['present']} |"
                     f" {row['partial']} | {row['corroborating']} |"
                     f" {'thin' if row['thin'] else ''} |")
    thin = sum(1 for row in rows if row["thin"])
    lines += ["", f"{thin} of {len(rows)} dimension value(s) below {min_instances}."]
    return "\n".join(lines) + "\n"
