"""Unit tests for network.services — pure-Python logic, no DB required."""
from django.test import SimpleTestCase

from network.services import (
    get_shortest_path,
    bfs_distance,
    nodes_within_distance,
    is_within_proximity,
    calculate_fare,
)


# ---------------------------------------------------------------------------
# Shared fixture: a simple directed graph
#
#   1 -> 2 -> 3 -> 4
#        |
#        v
#        5 -> 6
# ---------------------------------------------------------------------------
GRAPH = {
    1: [2],
    2: [3, 5],
    3: [4],
    4: [],
    5: [6],
    6: [],
}


class TestGetShortestPath(SimpleTestCase):
    def test_direct_connection(self):
        self.assertEqual(get_shortest_path(1, 2, GRAPH), [1, 2])

    def test_multi_hop(self):
        self.assertEqual(get_shortest_path(1, 4, GRAPH), [1, 2, 3, 4])

    def test_branch_path(self):
        self.assertEqual(get_shortest_path(2, 6, GRAPH), [2, 5, 6])

    def test_same_node(self):
        self.assertEqual(get_shortest_path(3, 3, GRAPH), [3])

    def test_unreachable(self):
        # 4 has no outgoing edges
        self.assertIsNone(get_shortest_path(4, 1, GRAPH))

    def test_unknown_node(self):
        self.assertIsNone(get_shortest_path(99, 1, GRAPH))


class TestBfsDistance(SimpleTestCase):
    def test_adjacent(self):
        self.assertEqual(bfs_distance(1, 2, GRAPH), 1)

    def test_three_hops(self):
        self.assertEqual(bfs_distance(1, 4, GRAPH), 3)

    def test_unreachable(self):
        self.assertIsNone(bfs_distance(4, 1, GRAPH))


class TestNodesWithinDistance(SimpleTestCase):
    def test_radius_1_from_2(self):
        # From node 2 within 1 hop (undirected): 1, 3, 5 are all adjacent
        result = nodes_within_distance(2, 1, GRAPH)
        self.assertIn(1, result)
        self.assertIn(3, result)
        self.assertIn(5, result)

    def test_radius_0(self):
        result = nodes_within_distance(3, 0, GRAPH)
        self.assertEqual(result, {3})


class TestIsWithinProximity(SimpleTestCase):
    def test_node_on_route(self):
        self.assertTrue(is_within_proximity(3, [1, 2, 3, 4], max_dist=0, graph=GRAPH))

    def test_node_adjacent_to_route(self):
        self.assertTrue(is_within_proximity(5, [1, 2, 3], max_dist=1, graph=GRAPH))

    def test_node_too_far(self):
        self.assertFalse(is_within_proximity(6, [1], max_dist=0, graph=GRAPH))


class TestCalculateFare(SimpleTestCase):
    """
    Fare formula: fare = UNIT_PRICE * Σ(1/n_i) + BASE_FEE
    Defaults: UNIT_PRICE=2.0, BASE_FEE=3.0
    """

    def test_single_passenger_one_hop(self):
        # 1 hop, 1 passenger: 2.0 * (1/1) + 3.0 = 5.0
        fare = calculate_fare([1, 2], pickup_index=0, dropoff_index=1)
        self.assertAlmostEqual(fare, 5.0)

    def test_single_passenger_two_hops(self):
        # 2 hops, 1 passenger: 2.0 * (1+1) + 3.0 = 7.0
        fare = calculate_fare([1, 2, 3], pickup_index=0, dropoff_index=2)
        self.assertAlmostEqual(fare, 7.0)

    def test_shared_ride_fare_reduced(self):
        # 1 hop, 2 passengers sharing all hops → 2.0*(1/2) + 3.0 = 4.0
        confirmed = [{'pickup_index': 0, 'dropoff_index': 1}]
        fare = calculate_fare([1, 2], pickup_index=0, dropoff_index=1, confirmed_passengers=confirmed)
        self.assertAlmostEqual(fare, 4.0)

    def test_pickup_dropoff_same_index_zero_fare(self):
        # zero hops — only base fee
        fare = calculate_fare([1, 2, 3], pickup_index=1, dropoff_index=1)
        self.assertAlmostEqual(fare, 3.0)

    def test_confirmed_passengers_outside_window_no_effect(self):
        # Confirmed passenger boards after new passenger alights — shouldn't affect fare
        confirmed = [{'pickup_index': 2, 'dropoff_index': 3}]
        solo_fare = calculate_fare([1, 2, 3, 4], pickup_index=0, dropoff_index=2)
        shared_fare = calculate_fare([1, 2, 3, 4], pickup_index=0, dropoff_index=2,
                                     confirmed_passengers=confirmed)
        self.assertAlmostEqual(solo_fare, shared_fare)
