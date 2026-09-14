# Priority Rules R1-R11

This file is the only definition source for the rule set. Rule IDs and names are stable. Profiles may only change the order of R3-R11; R1 and R2 always remain first.

## R1: Exact inventory and canonical color identity

Every non-transparent source cell must contain exactly one initial jewel. Every target color total must exactly equal its completed/source total. Generated or exported JSON must use the canonical project ID for every palette hex in the palette, completed board, and initial board. KStage must show every inventory row as fully used with zero remaining.

R1 has no visual or count-balancing exception. Repair any dimension mismatch, missing cell, transparent-cell overflow, count mismatch, unknown palette color, or noncanonical ID before continuing.

## R2: No same-base conflict

An initial jewel must never equal the completed/base color beneath it. The allowed conflict count is zero. R2 has no exception.

## R3: Same-color clustering and source-structure fidelity

Gather each target color into as few meaningful pickup groups as practical while preserving the source image's region grammar. Treat connected source regions and visible art regions as structural units. A large source region should normally contain one target color or a clean two-color split, and a target group should normally stay within one source color plus one neighboring source color.

Source boundaries are soft only when a local crossing connects a group, follows a contour, or preserves a readable shape. Fragment-heavy art must keep its local source grammar before broader cluster optimization. Avoid extra pickup operations caused by preventable splits.

## R4: Structural color continuity

Keep white/off-white, black/dark, outlines, rims, shadows, and other strong structural colors continuous whenever legal. Prefer one readable block, line, rim, skeleton, or outline over separate islands. Low-count light colors require especially strict grouping.

## R5: Light-dark coverage contrast

Prefer placements with a clear value difference between target jewel and base region. Test dark-on-light and light-on-dark options before accepting broad pale-on-pale or similarly valued coverage. A small grouped repair may use weaker contrast only when earlier rules leave no cleaner legal placement.

## R6: Avoid near-hue region exchange

Do not use visually adjacent color families as a main coverage direction when a clearer legal cross-hue option exists. Risk pairs include yellow/orange, orange/red, blue/cyan, blue/purple, purple/pink, green/lime, same-hue light/dark pairs, and pale warm combinations such as white/cream/yellow/pink/tan.

Near-hue use is acceptable only as a minor, grouped, structurally justified count repair after better legal alternatives have been exhausted. Reciprocal area matching never overrides R6.

## R7: Avoid saturation and brightness conflict

Do not create large adjacent groups or long contact edges between high-saturation jewel colors when a calmer legal placement exists. Evaluate jewel-to-jewel adjacency as well as jewel-to-base coverage. Treat white and cream as high-brightness colors that can create glare beside large bright saturated blocks.

Use a legal dark, gray, wine, tan, cream, or lower-saturation structure as a buffer when possible. Otherwise shorten the contact into compact accents or source-shaped details.

## R8: Boundary quality

Use one or two target colors on the outer boundary by default. A third is acceptable only as a clear continuous arc or region. Preserve readable contour segments when full unification would damage earlier rules. Reject checkerboard edges, confetti, isolated boundary dots, background-merging colors, and count leftovers placed on the contour without structural purpose.

## R9: Readable art structure

Preserve the source silhouette, major regions, containment, symmetry, feature hierarchy, and recognizable details. Cross-region placement must follow local shape rather than invent an unrelated path. For obvious symmetry, use the same recolor grammar on counterpart regions and place unavoidable imbalance on the centerline, boundary, or paired details.

Faces and expressions must retain readable features and avoid combinations that visibly distort or harshen them. This part requires AI visual judgment.

## R10: Fragment and flying-point control

Avoid isolated dots, unrelated 1-3 cell pieces, and tiny count leftovers. A small component is acceptable only when it is a deliberate source detail, a contour-following connection, a symmetric accent, or an unavoidable count repair attached as closely as possible to its group. A component isolated in both four-direction and eight-direction analysis is a true flying point.

## R11: Overall play and visual comfort

The accepted board must have an obvious first cleanup target, readable dominant groups, a coherent route from messy to ordered, and a pleasant final initial-state composition. Challenge the first legal result and revise it when a better legal arrangement improves play or visual comfort without breaking an earlier rule.

R11 includes the AI-only judgment of overall balance, containment, facial appeal, and whether the board is tiring or confusing to decode. Script output cannot pass R11 by itself.
