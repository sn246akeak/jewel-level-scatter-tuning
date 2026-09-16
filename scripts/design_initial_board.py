#!/usr/bin/env python3
"""Create a legal clustered candidate from source state plus declarative design constraints."""

from __future__ import annotations

import argparse
import heapq
import itertools
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from board_common import (
    DIR4,
    are_near_families,
    board_sha256,
    color_counts,
    color_family,
    component_cells,
    luminance,
    palette_map,
    read_json,
    source_payload,
    write_json,
)


class MinCostFlow:
    def __init__(self, size: int):
        self.graph: list[list[list[int]]] = [[] for _ in range(size)]

    def add(self, source: int, target: int, capacity: int, cost: int) -> int:
        forward = [target, capacity, cost, len(self.graph[target])]
        reverse = [source, 0, -cost, len(self.graph[source])]
        self.graph[source].append(forward)
        self.graph[target].append(reverse)
        return len(self.graph[source]) - 1

    def solve(self, source: int, sink: int, required: int) -> int:
        node_count = len(self.graph)
        potential = [0] * node_count
        flow = 0
        while flow < required:
            distance = [10**18] * node_count
            previous: list[tuple[int, int] | None] = [None] * node_count
            distance[source] = 0
            queue = [(0, source)]
            while queue:
                current, node = heapq.heappop(queue)
                if current != distance[node]:
                    continue
                for edge_index, edge in enumerate(self.graph[node]):
                    target, capacity, cost, _ = edge
                    if capacity <= 0:
                        continue
                    candidate = current + cost + potential[node] - potential[target]
                    if candidate < distance[target]:
                        distance[target] = candidate
                        previous[target] = (node, edge_index)
                        heapq.heappush(queue, (candidate, target))
            if previous[sink] is None:
                raise ValueError("no legal inventory allocation exists after applying design constraints")
            for node in range(node_count):
                if distance[node] < 10**18:
                    potential[node] += distance[node]
            amount = required - flow
            node = sink
            while node != source:
                parent, edge_index = previous[node]  # type: ignore[misc]
                amount = min(amount, self.graph[parent][edge_index][1])
                node = parent
            node = sink
            while node != source:
                parent, edge_index = previous[node]  # type: ignore[misc]
                edge = self.graph[parent][edge_index]
                edge[1] -= amount
                self.graph[node][edge[3]][1] += amount
                node = parent
            flow += amount
        return flow


def allocation_cost(source_id: int, target_id: int, palette: dict[int, str]) -> int:
    source_family = color_family(palette[source_id])
    target_family = color_family(palette[target_id])
    contrast = abs(luminance(palette[source_id]) - luminance(palette[target_id]))
    cost = round((1 - min(contrast * 2, 1)) * 30)
    if are_near_families(source_family, target_family):
        cost += 45
    if source_family == "pale" and target_family in {"pale", "yellow", "pink"}:
        cost += 35
    return cost * 100 + target_id


def transport(
    source_counts: Counter[int], target_counts: Counter[int], palette: dict[int, str]
) -> dict[int, Counter[int]]:
    source_ids = sorted(source_counts)
    target_ids = sorted(target_counts)
    graph = MinCostFlow(2 + len(source_ids) + len(target_ids))
    start = 0
    source_offset = 1
    target_offset = 1 + len(source_ids)
    sink = target_offset + len(target_ids)
    for index, color_id in enumerate(source_ids):
        graph.add(start, source_offset + index, source_counts[color_id], 0)
    edge_refs: dict[tuple[int, int], tuple[int, int, int]] = {}
    for source_index, source_id in enumerate(source_ids):
        node = source_offset + source_index
        for target_index, target_id in enumerate(target_ids):
            if source_id == target_id:
                continue
            capacity = min(source_counts[source_id], target_counts[target_id])
            edge_index = graph.add(
                node, target_offset + target_index, capacity, allocation_cost(source_id, target_id, palette)
            )
            edge_refs[(source_id, target_id)] = (node, edge_index, capacity)
    for index, color_id in enumerate(target_ids):
        graph.add(target_offset + index, sink, target_counts[color_id], 0)
    required = sum(source_counts.values())
    graph.solve(start, sink, required)
    result: dict[int, Counter[int]] = defaultdict(Counter)
    for pair, (node, edge_index, capacity) in edge_refs.items():
        used = capacity - graph.graph[node][edge_index][1]
        if used:
            result[pair[0]][pair[1]] = used
    return result


def transport_pairs(
    pair_counts: Counter[tuple[int, int]], target_counts: Counter[int], palette: dict[int, str]
) -> dict[tuple[int, int], Counter[int]]:
    pair_ids = sorted(pair_counts)
    target_ids = sorted(target_counts)
    graph = MinCostFlow(2 + len(pair_ids) + len(target_ids))
    start, pair_offset, target_offset = 0, 1, 1 + len(pair_ids)
    sink = target_offset + len(target_ids)
    for index, pair in enumerate(pair_ids):
        graph.add(start, pair_offset + index, pair_counts[pair], 0)
    refs: dict[tuple[tuple[int, int], int], tuple[int, int, int]] = {}
    for pair_index, pair in enumerate(pair_ids):
        node = pair_offset + pair_index
        for target_index, target_id in enumerate(target_ids):
            if target_id in pair:
                continue
            capacity = min(pair_counts[pair], target_counts[target_id])
            cost = max(allocation_cost(source_id, target_id, palette) for source_id in set(pair))
            edge_index = graph.add(node, target_offset + target_index, capacity, cost)
            refs[(pair, target_id)] = (node, edge_index, capacity)
    for index, target_id in enumerate(target_ids):
        graph.add(target_offset + index, sink, target_counts[target_id], 0)
    graph.solve(start, sink, sum(pair_counts.values()))
    result: dict[tuple[int, int], Counter[int]] = defaultdict(Counter)
    for (pair, target_id), (node, edge_index, capacity) in refs.items():
        used = capacity - graph.graph[node][edge_index][1]
        if used:
            result[pair][target_id] = used
    return result


def component_count(cells: set[tuple[int, int]]) -> int:
    seen: set[tuple[int, int]] = set()
    count = 0
    for cell in cells:
        if cell in seen:
            continue
        count += 1
        queue = [cell]
        seen.add(cell)
        for x, y in queue:
            for dx, dy in DIR4:
                neighbor = (x + dx, y + dy)
                if neighbor in cells and neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    return count


def partition_region(cells: list[tuple[int, int]], allocations: Counter[int]) -> dict[tuple[int, int], int]:
    items = [(color_id, count) for color_id, count in allocations.items() if count]
    if sum(count for _, count in items) != len(cells):
        raise ValueError("region allocation does not match region size")
    if len(items) == 1:
        return {cell: items[0][0] for cell in cells}
    projections = (
        lambda p: (p[0], p[1]),
        lambda p: (-p[0], p[1]),
        lambda p: (p[1], p[0]),
        lambda p: (-p[1], p[0]),
        lambda p: (p[0] + p[1], p[1], p[0]),
        lambda p: (p[0] - p[1], p[1], p[0]),
    )
    orders = list(itertools.permutations(items)) if len(items) <= 6 else [tuple(sorted(items))]
    best: tuple[tuple[int, int, tuple], dict[tuple[int, int], int]] | None = None
    for projection_index, projection in enumerate(projections):
        ordered_cells = sorted(cells, key=projection)
        for order in orders:
            assigned: dict[tuple[int, int], int] = {}
            position = 0
            for color_id, count in order:
                for cell in ordered_cells[position : position + count]:
                    assigned[cell] = color_id
                position += count
            groups = {
                color_id: {cell for cell, assigned_id in assigned.items() if assigned_id == color_id}
                for color_id, _ in items
            }
            fragments = sum(component_count(group) for group in groups.values())
            transition_edges = sum(
                1
                for (x, y), color_id in assigned.items()
                for dx, dy in ((1, 0), (0, 1))
                if (x + dx, y + dy) in assigned and assigned[(x + dx, y + dy)] != color_id
            )
            score = (fragments, transition_edges, tuple(color for color, _ in order), projection_index)
            if best is None or score < best[0]:
                best = (score, assigned)
    assert best is not None
    return best[1]


def parse_region_constraints(spec: dict[str, Any], regions: list[dict[str, Any]]) -> dict[int, Counter[int]]:
    raw = spec.get("design", {}).get("region_targets", {})
    known = {region["id"] for region in regions}
    output: dict[int, Counter[int]] = {}
    for region_key, targets in raw.items():
        region_id = int(region_key)
        if region_id not in known:
            raise ValueError(f"unknown region id in design spec: {region_id}")
        if not isinstance(targets, dict) or any(type(value) is not int or value < 0 for value in targets.values()):
            raise ValueError(f"region {region_id} target counts must be nonnegative integers")
        output[region_id] = Counter({int(key): value for key, value in targets.items() if value})
    return output


def allocate_to_regions(
    regions: list[dict[str, Any]], matrix: dict[int, Counter[int]],
    fixed: dict[int, Counter[int]] | None = None,
) -> dict[int, Counter[int]]:
    fixed = fixed or {}
    by_source: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for region in regions:
        by_source[region["color"]].append(region)
    result = {region["id"]: Counter(fixed.get(region["id"], {})) for region in regions}
    for source_id, source_regions in by_source.items():
        quotas = Counter(matrix.get(source_id, {}))
        for region in sorted(source_regions, key=lambda item: (-item["size"], item["id"])):
            allocation = result[region["id"]]
            capacity = region["size"] - sum(allocation.values())
            while capacity:
                exact = [target_id for target_id, count in quotas.items() if count == capacity]
                target_id = min(exact) if exact else max(quotas, key=lambda key: (quotas[key], -key))
                amount = min(capacity, quotas[target_id])
                if amount <= 0:
                    raise ValueError(f"unable to fill region {region['id']}")
                allocation[target_id] += amount
                quotas[target_id] -= amount
                if quotas[target_id] == 0:
                    del quotas[target_id]
                capacity -= amount
        if quotas:
            raise ValueError(f"unplaced target quotas for source color {source_id}: {dict(quotas)}")
    return result


def center_target_candidates(totals: Counter[int], center_count: int):
    ids = sorted(totals)
    base = {color_id: totals[color_id] % 2 for color_id in ids}
    remaining_units = (center_count - sum(base.values())) // 2
    if remaining_units < 0 or (center_count - sum(base.values())) % 2:
        return
    capacities = {color_id: (totals[color_id] - base[color_id]) // 2 for color_id in ids}

    def visit(index: int, remaining: int, current: dict[int, int]):
        if index == len(ids):
            if remaining == 0:
                yield Counter({color_id: base[color_id] + 2 * current.get(color_id, 0) for color_id in ids})
            return
        color_id = ids[index]
        for amount in range(min(capacities[color_id], remaining) + 1):
            current[color_id] = amount
            yield from visit(index + 1, remaining - amount, current)
        current.pop(color_id, None)

    yield from visit(0, remaining_units, {})


def asymmetric_pair_candidates(
    base: list[list[int]], odd_targets: list[int]
):
    width = len(base[0])
    height = len(base)
    cells = sorted(
        [(x, y) for y, row in enumerate(base) for x in range(width // 2) if row[x] > 0],
        key=lambda p: (abs(p[0] - (width - 1) / 2) + abs(p[1] - (height - 1) / 2), p[1], p[0]),
    )

    def pairings(values: tuple[int, ...]):
        if not values:
            yield []
            return
        first = values[0]
        for index in range(1, len(values)):
            second = values[index]
            rest = values[1:index] + values[index + 1 :]
            for tail in pairings(rest):
                yield [(first, second), *tail]

    def place(color_pairs, index, used, current):
        if index == len(color_pairs):
            yield dict(current)
            return
        left_target, right_target = color_pairs[index]
        for x, y in cells:
            if (x, y) in used:
                continue
            mirror = width - 1 - x
            left_base, right_base = base[y][x], base[y][mirror]
            for a, b in ((left_target, right_target), (right_target, left_target)):
                if a != left_base and b != right_base:
                    used.add((x, y))
                    current[(x, y)] = (a, b)
                    yield from place(color_pairs, index + 1, used, current)
                    current.pop((x, y))
                    used.remove((x, y))

    for color_pairs in pairings(tuple(odd_targets)):
        yield from place(color_pairs, 0, set(), {})


def symmetric_board(base: list[list[int]], totals: Counter[int], palette: dict[int, str]) -> list[list[int]]:
    width = len(base[0])
    if any((row[x] > 0) != (row[width - 1 - x] > 0) for row in base for x in range(width // 2)):
        raise ValueError("symmetric design requested but the source silhouette is not left-right symmetric")
    middle = width // 2
    center_cells = [(middle, y) for y, row in enumerate(base) if width % 2 and row[middle] > 0]
    center_source = Counter(base[y][x] for x, y in center_cells)
    asymmetric: dict[tuple[int, int], tuple[int, int]] = {}
    center_matrix = pair_matrix = None
    pair_board = None
    if width % 2:
        center_options = ((candidate, {}) for candidate in center_target_candidates(totals, len(center_cells)))
    else:
        odd_targets = [color_id for color_id, count in totals.items() if count % 2]
        center_options = (
            (Counter({color_id: 1 for color_id in odd_targets}), assignment)
            for assignment in asymmetric_pair_candidates(base, odd_targets)
        )
    for center_targets, candidate_asymmetric in center_options:
        excluded = set(candidate_asymmetric)
        remaining_pairs = [
            (x, y, (row[x], row[width - 1 - x]))
            for y, row in enumerate(base)
            for x in range(width // 2)
            if row[x] > 0 and (x, y) not in excluded
        ]
        pair_counts = Counter(pair for _, _, pair in remaining_pairs)
        try:
            candidate_center = transport(center_source, center_targets, palette) if center_cells else {}
            pair_targets = Counter({color_id: (totals[color_id] - center_targets[color_id]) // 2 for color_id in totals})
            candidate_pairs = transport_pairs(pair_counts, pair_targets, palette) if sum(pair_counts.values()) else {}
        except ValueError:
            continue
        pair_types = sorted(pair_counts)
        pair_to_fake = {pair: index + 1 for index, pair in enumerate(pair_types)}
        pair_board = [[-1 for _ in row] for row in base]
        for x, y, pair in remaining_pairs:
            pair_board[y][x] = pair_to_fake[pair]
        fake_to_pair = {value: key for key, value in pair_to_fake.items()}
        center_matrix, pair_matrix, asymmetric = candidate_center, candidate_pairs, candidate_asymmetric
        break
    if center_matrix is None or pair_matrix is None or pair_board is None:
        raise ValueError("no legal minimum-difference left-right allocation exists")

    initial = [[-1 for _ in row] for row in base]
    center_by_source: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for cell in center_cells:
        center_by_source[base[cell[1]][cell[0]]].append(cell)
    for source_id, cells in center_by_source.items():
        quotas = Counter(center_matrix[source_id])
        position = 0
        for target_id, count in sorted(quotas.items(), key=lambda item: (-item[1], item[0])):
            for x, y in sorted(cells, key=lambda p: p[1])[position : position + count]:
                initial[y][x] = target_id
            position += count

    for (x, y), (left_target, right_target) in asymmetric.items():
        initial[y][x] = left_target
        initial[y][width - 1 - x] = right_target

    pair_regions = component_cells(pair_board)
    fake_matrix = {fake_id: pair_matrix[pair] for fake_id, pair in fake_to_pair.items()}
    left_allocations = allocate_to_regions(pair_regions, fake_matrix)
    for region in pair_regions:
        assignment = partition_region(region["cells"], left_allocations[region["id"]])
        for (x, y), target_id in assignment.items():
            initial[y][x] = target_id
            initial[y][width - 1 - x] = target_id
    return initial


def design(source_path: Path, profile_path: Path, spec: dict[str, Any] | None = None, candidate_revision: int = 1) -> dict[str, Any]:
    source_data = read_json(source_path)
    profile = read_json(profile_path)
    level_id, source_revision, base, colors = source_payload(source_data)
    if profile.get("level_id") != level_id or profile.get("source_revision") != source_revision:
        raise ValueError("priority profile does not identify the same source board")
    palette = palette_map(colors)
    totals = color_counts(base)
    regions = component_cells(base)
    fixed = parse_region_constraints(spec or {}, regions)
    require_symmetry = bool((spec or {}).get("ai_semantics", {}).get("exact_pixel_symmetry"))
    if require_symmetry and not fixed:
        initial = symmetric_board(base, totals, palette)
        region_allocations = {
            region["id"]: Counter(initial[y][x] for x, y in region["cells"])
            for region in regions
        }
    else:
        remaining_source = Counter(totals)
        remaining_target = Counter(totals)
        for region in regions:
            allocation = fixed.get(region["id"], Counter())
            if sum(allocation.values()) > region["size"]:
                raise ValueError(f"region {region['id']} constraints exceed its size")
            for target_id, count in allocation.items():
                if target_id not in totals:
                    raise ValueError(f"region {region['id']} uses unknown target color {target_id}")
                if target_id == region["color"]:
                    raise ValueError(f"region {region['id']} violates same-base gate")
                remaining_source[region["color"]] -= count
                remaining_target[target_id] -= count
                if remaining_target[target_id] < 0:
                    raise ValueError(f"fixed region constraints overuse target color {target_id}")
        remaining_source += Counter()
        remaining_target += Counter()
        matrix = transport(remaining_source, remaining_target, palette) if sum(remaining_source.values()) else {}
        region_allocations = allocate_to_regions(regions, matrix, fixed)
        initial = [[-1 for _ in row] for row in base]
        for region in regions:
            assignment = partition_region(region["cells"], region_allocations[region["id"]])
            for (x, y), target_id in assignment.items():
                initial[y][x] = target_id
    if color_counts(initial) != totals:
        raise ValueError("generated board does not preserve inventory")
    conflicts = [(x, y) for y, row in enumerate(initial) for x, target in enumerate(row) if target > 0 and target == base[y][x]]
    if conflicts:
        raise ValueError(f"generated board has {len(conflicts)} same-base conflicts")
    decisions = {rule_id: {"status": "pending_validation", "notes": []} for rule_id in profile["priority_order"]}
    return {
        "level_id": level_id,
        "source_revision": source_revision,
        "candidate_revision": candidate_revision,
        "candidate_sha256": board_sha256(initial),
        "profile_path": profile_path.name,
        "width": len(base[0]),
        "height": len(base),
        "colors": colors,
        "completeBoard": base,
        "initialBoard": initial,
        "base": base,
        "initial": initial,
        "region_allocations": {
            str(region_id): {str(color_id): count for color_id, count in sorted(allocation.items())}
            for region_id, allocation in sorted(region_allocations.items())
        },
        "rule_decisions": decisions,
        "exceptions": list((spec or {}).get("design", {}).get("exceptions", [])),
    }


def render_svg(artifact: dict[str, Any], path: Path, scale: int = 16) -> None:
    board = artifact["initialBoard"]
    palette = palette_map(artifact["colors"])
    width, height = artifact["width"], artifact["height"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width*scale}" height="{height*scale}" viewBox="0 0 {width} {height}">']
    parts.append('<rect width="100%" height="100%" fill="#f2f2f2"/>')
    for y, row in enumerate(board):
        for x, color_id in enumerate(row):
            if color_id > 0:
                parts.append(f'<rect x="{x}" y="{y}" width="1" height="1" fill="{palette[color_id]}"/>')
    parts.append("</svg>")
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_state", type=Path)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--spec", type=Path)
    parser.add_argument("--candidate-revision", type=int, default=1)
    parser.add_argument("--output", type=Path, default=Path("initial_board.json"))
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    spec = read_json(args.spec) if args.spec else None
    artifact = design(args.source_state, args.profile, spec, args.candidate_revision)
    write_json(args.output, artifact)
    render_svg(artifact, args.preview or args.output.with_suffix(".svg"))
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
