# Classification Profiles F1-F10

Module A selects one primary profile and zero or more secondary profiles. Profile IDs, names, risk tags, and priority orders are fixed. The primary profile supplies the entire Module B order. Secondary profiles record additional risks and do not modify or merge that order.

If several profiles fit, select the one supported by the strongest measured or visual evidence. Use F1 only when no specialized profile dominates. Copy the chosen order verbatim; AI must not rename or reorder rules.

## Required analysis artifact

Write `source_analysis.json` with this shape:

```json
{
  "level_id": "<level or pre-level id>",
  "source_revision": "<stable source identifier>",
  "dimensions": {"width": 0, "height": 0, "art_cells": 0},
  "objective_metrics": {
    "bright_color_ratio": 0.0,
    "high_saturation_ratio": 0.0,
    "small_component_ratio": 0.0,
    "rare_color_count": 0,
    "boundary_color_count": 0,
    "dominant_color_ratio": 0.0,
    "near_hue_groups": []
  },
  "ai_semantics": {
    "visual_pairing": false,
    "exact_pixel_symmetry": false,
    "contains_face_or_expression": false,
    "containment_structure": false,
    "outline_or_linework_dominant": false,
    "notes": []
  },
  "matched_classes": ["F1"]
}
```

Metrics must come from source data where measurable. `ai_semantics` records visual interpretation of subject, silhouette, containment, symmetry, face, expression, and hierarchy. Do not invent numeric precision from visual inspection alone.

## Required profile artifact

Write `priority_profile.json` with this shape:

```json
{
  "level_id": "<same id as source_analysis>",
  "source_revision": "<same revision as source_analysis>",
  "primary_class": "F4",
  "secondary_classes": ["F3", "F7"],
  "risk_tags": ["high_brightness", "near_hue", "rare_color_tail"],
  "priority_order": ["R1", "R2", "R7", "R5", "R6", "R3", "R9", "R4", "R8", "R10", "R11"],
  "evidence": {
    "bright_color_ratio": 0.58,
    "near_hue_groups": ["yellow-orange", "pink-purple"],
    "visual_pairing": true,
    "exact_pixel_symmetry": false
  }
}
```

`primary_class` and `secondary_classes` must appear in `source_analysis.json.matched_classes`. `priority_order` must exactly match the primary profile below.

## F1 Balanced structural

- Match: no specialized risk clearly dominates.
- Risk tags: `balanced_structure`.
- Order: `R1 > R2 > R3 > R4 > R5 > R6 > R7 > R8 > R9 > R10 > R11`.

## F2 Fragment and detail heavy

- Match: many 1-3 cell source components, decorative chips, or disconnected local details.
- Risk tags: `fragment_heavy`, `small_components`.
- Order: `R1 > R2 > R3 > R10 > R9 > R4 > R8 > R5 > R6 > R7 > R11`.

## F3 Near-hue palette

- Match: several source colors fall into adjacent hue families or same-hue value variants.
- Risk tags: `near_hue`, `low_color_separation`.
- Order: `R1 > R2 > R6 > R5 > R3 > R9 > R7 > R4 > R8 > R10 > R11`.

## F4 High brightness and saturation

- Match: bright or saturated colors occupy a large share of art cells, or multiple bright families touch across long edges.
- Risk tags: `high_brightness`, `high_saturation`.
- Order: `R1 > R2 > R7 > R5 > R6 > R3 > R9 > R4 > R8 > R10 > R11`.

## F5 Symmetric structure

- Match: the silhouette or major internal regions have clear left-right, top-bottom, rotational, or paired symmetry.
- Risk tags: `symmetry`, `paired_regions`.
- Order: `R1 > R2 > R9 > R3 > R4 > R8 > R5 > R6 > R7 > R10 > R11`.

## F6 Complex boundary

- Match: the source contour contains many color changes, disconnected arcs, holes, or narrow protrusions.
- Risk tags: `complex_boundary`, `contour_fragments`.
- Order: `R1 > R2 > R8 > R3 > R9 > R4 > R5 > R6 > R7 > R10 > R11`.

## F7 Rare colors and count tails

- Match: one or more colors have very small totals or totals that are difficult to place without 1-3 cell remainders.
- Risk tags: `rare_color_tail`, `small_inventory`.
- Order: `R1 > R2 > R3 > R4 > R10 > R9 > R8 > R5 > R6 > R7 > R11`.

## F8 Dominant large regions

- Match: one source color exceeds 50% of art cells or a few large regions dominate a low-color image.
- Risk tags: `dominant_region`, `low_color_count`.
- Order: `R1 > R2 > R3 > R9 > R5 > R4 > R8 > R6 > R7 > R10 > R11`.

## F9 Face or expression sensitive

- Match: the image contains a readable face, eyes, mouth, skin area, or expression whose treatment affects appeal.
- Risk tags: `face_expression`, `feature_hierarchy`.
- Order: `R1 > R2 > R9 > R5 > R7 > R6 > R3 > R4 > R8 > R10 > R11`.

## F10 Containment or linework dominant

- Match: nested regions, outlines, frames, enclosed details, or thin structural lines carry the identity of the image.
- Risk tags: `containment`, `outline_linework`.
- Order: `R1 > R2 > R9 > R4 > R3 > R8 > R5 > R6 > R7 > R10 > R11`.

## Selection checks

Before accepting Module A, confirm:

- Exactly one primary profile is set.
- Every matched non-primary profile appears in `secondary_classes`.
- Risk tags belong to matched profiles.
- Evidence values come from `source_analysis.json`.
- The priority order contains each of R1-R11 exactly once and matches the primary profile character for character.
