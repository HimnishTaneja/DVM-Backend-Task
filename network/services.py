"""
Graph services: BFS path finding, detour calculation, and fare computation.

Fare formula (spec-compliant):
    fare = p * Σ(1/n_i) + base_fee
    where:
        p        = unit price per hop  (CARPOOL_UNIT_PRICE in settings)
        n_i      = total passengers in the car at hop i
        base_fee = flat boarding fee   (CARPOOL_BASE_FEE in settings)
"""
from collections import deque
from django.conf import settings
from django.core.cache import cache
from network.models import Node, Edge

_GRAPH_CACHE_KEY = 'carpool_graph'
_GRAPH_CACHE_TTL = 60  # seconds


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph(use_cache=True):
    """Return adjacency list {node_id: [neighbour_id, ...]}.

    Results are cached for 60 s to avoid repeated DB hits on every dashboard
    load. Pass use_cache=False when nodes/edges have just been mutated.
    """
    if use_cache:
        cached = cache.get(_GRAPH_CACHE_KEY)
        if cached is not None:
            return cached

    graph = {n.id: [] for n in Node.objects.all()}
    for edge in Edge.objects.select_related('from_node', 'to_node'):
        graph.setdefault(edge.from_node.id, []).append(edge.to_node.id)

    if use_cache:
        cache.set(_GRAPH_CACHE_KEY, graph, _GRAPH_CACHE_TTL)
    return graph


def get_shortest_path(start_id, end_id, graph=None):
    """
    BFS shortest path from start_id to end_id.
    Returns list of node IDs (inclusive) or None if unreachable.
    Accepts an optional pre-built graph to avoid repeated DB calls.
    """
    if graph is None:
        graph = build_graph()

    if start_id not in graph or end_id not in graph:
        return None
    if start_id == end_id:
        return [start_id]

    queue = deque([(start_id, [start_id])])
    visited = {start_id}

    while queue:
        current, path = queue.popleft()
        for neighbour in graph.get(current, []):
            if neighbour == end_id:
                return path + [neighbour]
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append((neighbour, path + [neighbour]))
    return None


def bfs_distance(start_id, end_id, graph=None):
    """Shortest path length (hops), or None if unreachable."""
    path = get_shortest_path(start_id, end_id, graph)
    return (len(path) - 1) if path else None


# ---------------------------------------------------------------------------
# Proximity check
# ---------------------------------------------------------------------------

def nodes_within_distance(center_id, max_dist, graph=None):
    """
    Return set of node IDs reachable from center_id within max_dist hops
    via BFS on an undirected view of the graph.
    """
    if graph is None:
        graph = build_graph()

    undirected = {}
    for node_id, neighbours in graph.items():
        undirected.setdefault(node_id, set()).update(neighbours)
        for nb in neighbours:
            undirected.setdefault(nb, set()).add(node_id)

    visited = {center_id: 0}
    queue = deque([center_id])
    while queue:
        node = queue.popleft()
        d = visited[node]
        if d >= max_dist:
            continue
        for nb in undirected.get(node, []):
            if nb not in visited:
                visited[nb] = d + 1
                queue.append(nb)
    return set(visited.keys())


def is_within_proximity(node_id, route_node_ids, max_dist=None, graph=None):
    """True if node_id is within max_dist hops of ANY node in route_node_ids."""
    if max_dist is None:
        max_dist = getattr(settings, 'CARPOOL_PROXIMITY_NODES', 2)
    if graph is None:
        graph = build_graph()
    close_nodes = nodes_within_distance(node_id, max_dist, graph)
    return bool(close_nodes.intersection(set(route_node_ids)))


# ---------------------------------------------------------------------------
# Detour calculation
# ---------------------------------------------------------------------------

def calculate_detour(remaining_route, pickup_id, dropoff_id, graph=None):
    """
    Find optimal insertion of (pickup, dropoff) into the driver's remaining
    route (list of node IDs, last element = driver's destination).

    Accepts an optional pre-built graph to avoid repeated DB calls.

    Returns dict or None:
        {
            'detour_nodes': int,
            'new_route': [node_id, ...],
            'pickup_index': int,
            'dropoff_index': int,
        }
    """
    if not remaining_route:
        return None

    if graph is None:
        graph = build_graph()
    base_hops = len(remaining_route) - 1
    end_id = remaining_route[-1]

    best = None

    for i in range(len(remaining_route)):
        branch_start = remaining_route[i]

        path_to_pickup = get_shortest_path(branch_start, pickup_id, graph)
        if not path_to_pickup:
            continue

        path_pickup_to_dropoff = get_shortest_path(pickup_id, dropoff_id, graph)
        if not path_pickup_to_dropoff:
            continue

        path_dropoff_to_end = get_shortest_path(dropoff_id, end_id, graph)
        if not path_dropoff_to_end:
            continue

        new_hops = (
            i
            + (len(path_to_pickup) - 1)
            + (len(path_pickup_to_dropoff) - 1)
            + (len(path_dropoff_to_end) - 1)
        )
        detour = new_hops - base_hops

        if best is None or detour < best['detour_nodes']:
            prefix = remaining_route[:i]
            merged = (
                prefix
                + path_to_pickup
                + path_pickup_to_dropoff[1:]
                + path_dropoff_to_end[1:]
            )
            pickup_idx = merged.index(pickup_id)
            dropoff_idx = merged.index(dropoff_id, pickup_idx)

            best = {
                'detour_nodes': detour,
                'new_route': merged,
                'pickup_index': pickup_idx,
                'dropoff_index': dropoff_idx,
            }

    return best


# ---------------------------------------------------------------------------
# Fare calculation  (spec: fare = p * Σ(1/n_i) + base_fee)
# ---------------------------------------------------------------------------

def calculate_fare(new_route, pickup_index, dropoff_index, confirmed_passengers=None):
    """
    Calculate passenger fare.

    Args:
        new_route          – full driver route after passenger insertion
        pickup_index       – index in new_route where passenger boards
        dropoff_index      – index in new_route where passenger alights
        confirmed_passengers – list of {'pickup_index': int, 'dropoff_index': int}
                               for already-confirmed passengers

    Returns fare as float.
    """
    p = getattr(settings, 'CARPOOL_UNIT_PRICE', 2.0)
    base_fee = getattr(settings, 'CARPOOL_BASE_FEE', 3.0)

    if confirmed_passengers is None:
        confirmed_passengers = []

    total = 0.0
    for hop in range(pickup_index, dropoff_index):
        n_i = 1  # this new passenger
        for cp in confirmed_passengers:
            if cp.get('pickup_index', 0) <= hop < cp.get('dropoff_index', 0):
                n_i += 1
        total += 1.0 / n_i

    return round(p * total + base_fee, 2)


def calculate_fare_simple(passenger_hops, n_passengers=1):
    """
    Simplified fare when exact route indices aren't available.
    Assumes constant n_passengers over all hops.
    """
    p = getattr(settings, 'CARPOOL_UNIT_PRICE', 2.0)
    base_fee = getattr(settings, 'CARPOOL_BASE_FEE', 3.0)
    if passenger_hops <= 0:
        return round(base_fee, 2)
    return round(p * passenger_hops * (1.0 / max(n_passengers, 1)) + base_fee, 2)
