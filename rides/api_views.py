"""
DRF API views for driver-facing endpoints.
"""
from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from network.models import Node
from network.services import (
    build_graph, calculate_detour, calculate_fare,
    is_within_proximity,
)
from .models import Trip, TripSequence, CarpoolRequest, CarpoolOffer
from .serializers import (
    CarpoolRequestSerializer, UpdateNodeSerializer, MakeOfferSerializer,
)


def _get_driver_trip(request, trip_id):
    try:
        return Trip.objects.get(pk=trip_id, driver=request.user)
    except Trip.DoesNotExist:
        return None


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_current_node(request, trip_id):
    """POST /api/rides/<trip_id>/update-node/ — mark driver's current position."""
    trip = _get_driver_trip(request, trip_id)
    if trip is None:
        return Response({'error': 'Trip not found.'}, status=404)
    if trip.status != 'active':
        return Response({'error': 'Trip is not active.'}, status=400)

    ser = UpdateNodeSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=400)

    node_id = ser.validated_data['node_id']
    try:
        seq = trip.route_sequence.get(node_id=node_id)
    except TripSequence.DoesNotExist:
        return Response({'error': 'Node is not on this trip\'s route.'}, status=400)

    trip.route_sequence.filter(order__lte=seq.order).update(passed=True)
    trip.current_node_id = node_id
    trip.save(update_fields=['current_node_id'])

    return Response({'message': f'Current node updated to {seq.node.name}.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def trip_carpool_requests(request, trip_id):
    """GET /api/rides/<trip_id>/requests/ — eligible carpool requests for a trip."""
    trip = _get_driver_trip(request, trip_id)
    if trip is None:
        return Response({'error': 'Trip not found.'}, status=404)
    if trip.status != 'active':
        return Response({'error': 'Trip is not active.'}, status=400)

    remaining_ids = list(
        trip.route_sequence.filter(passed=False)
        .order_by('order')
        .values_list('node_id', flat=True)
    )
    if not remaining_ids:
        return Response([])

    proximity = getattr(settings, 'CARPOOL_PROXIMITY_NODES', 2)
    graph = build_graph()
    offered_ids = set(
        CarpoolOffer.objects.filter(trip=trip).values_list('request_id', flat=True)
    )

    eligible = []
    for req in CarpoolRequest.objects.filter(
        status='pending'
    ).exclude(id__in=offered_ids).select_related('passenger', 'pickup_node', 'destination_node'):
        if (is_within_proximity(req.pickup_node_id, remaining_ids, proximity, graph)
                and is_within_proximity(req.destination_node_id, remaining_ids, proximity, graph)):
            eligible.append(req)

    return Response(CarpoolRequestSerializer(eligible, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def make_offer(request, trip_id):
    """POST /api/rides/<trip_id>/make-offer/ — offer to serve a carpool request."""
    trip = _get_driver_trip(request, trip_id)
    if trip is None:
        return Response({'error': 'Trip not found.'}, status=404)
    if trip.status != 'active':
        return Response({'error': 'Trip is not active.'}, status=400)

    confirmed_count = trip.accepted_passengers.filter(status='confirmed').count()
    if confirmed_count >= trip.max_passengers:
        return Response({'error': 'Trip is at maximum passenger capacity.'}, status=400)

    ser = MakeOfferSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=400)

    carpool_req = CarpoolRequest.objects.select_related(
        'pickup_node', 'destination_node'
    ).get(pk=ser.validated_data['request_id'])

    if CarpoolOffer.objects.filter(trip=trip, request=carpool_req).exists():
        return Response({'error': 'Offer already made for this request.'}, status=400)

    remaining_ids = list(
        trip.route_sequence.filter(passed=False)
        .order_by('order')
        .values_list('node_id', flat=True)
    )
    if not remaining_ids:
        return Response({'error': 'No remaining route.'}, status=400)

    detour_result = calculate_detour(
        remaining_ids,
        carpool_req.pickup_node_id,
        carpool_req.destination_node_id,
    )
    if detour_result is None:
        return Response({'error': 'Cannot serve this passenger — no viable route.'}, status=400)

    confirmed_passengers = []
    new_route = detour_result['new_route']
    for confirmed_req in trip.accepted_passengers.filter(status='confirmed').select_related(
        'pickup_node', 'destination_node'
    ):
        try:
            p_idx = new_route.index(confirmed_req.pickup_node_id)
            d_idx = new_route.index(confirmed_req.destination_node_id, p_idx)
            confirmed_passengers.append({'pickup_index': p_idx, 'dropoff_index': d_idx})
        except ValueError:
            pass

    fare = calculate_fare(
        new_route,
        detour_result['pickup_index'],
        detour_result['dropoff_index'],
        confirmed_passengers,
    )

    offer = CarpoolOffer.objects.create(
        request=carpool_req,
        trip=trip,
        detour_nodes=detour_result['detour_nodes'],
        fare=fare,
    )

    return Response({
        'offer_id': offer.id,
        'detour_nodes': offer.detour_nodes,
        'fare': str(offer.fare),
        'message': 'Offer sent to passenger.',
    }, status=201)


@api_view(['GET'])
def trip_status(request, trip_id):
    """GET /api/trip/<id>/status/ — live trip status for polling (no auth required)."""
    try:
        trip = Trip.objects.select_related(
            'driver', 'current_node', 'start_node', 'end_node'
        ).get(pk=trip_id)
    except Trip.DoesNotExist:
        return Response({'error': 'Trip not found.'}, status=404)

    route = list(trip.route_sequence.select_related('node').order_by('order'))
    total = len(route)
    passed_count = sum(1 for s in route if s.passed)
    progress_pct = int(passed_count / total * 100) if total else 0

    passengers = []
    for req in trip.accepted_passengers.filter(
        status='confirmed'
    ).select_related('passenger', 'pickup_node', 'destination_node'):
        offer = req.offers.filter(trip=trip).first()
        passengers.append({
            'username': req.passenger.username,
            'pickup': req.pickup_node.name,
            'destination': req.destination_node.name,
            'fare': str(offer.fare) if offer else None,
        })

    next_node = None
    for s in route:
        if not s.passed:
            next_node = {'id': s.node_id, 'name': s.node.name}
            break

    return Response({
        'trip_id': trip.id,
        'status': trip.status,
        'driver': trip.driver.username,
        'current_node': (
            {'id': trip.current_node_id, 'name': trip.current_node.name}
            if trip.current_node else None
        ),
        'next_node': next_node,
        'route': [
            {'id': s.node_id, 'name': s.node.name, 'passed': s.passed, 'order': s.order}
            for s in route
        ],
        'progress_pct': progress_pct,
        'passed_count': passed_count,
        'total_nodes': total,
        'passengers': passengers,
    })


@api_view(['GET'])
def active_trips_map(request):
    """GET /api/trips/active/ — all active trips for map overlay (no auth required)."""
    trips = Trip.objects.filter(status='active').select_related(
        'driver', 'current_node', 'start_node', 'end_node'
    )
    result = []
    for trip in trips:
        route = list(trip.route_sequence.select_related('node').order_by('order'))
        result.append({
            'trip_id': trip.id,
            'driver': trip.driver.username,
            'current_node_id': trip.current_node_id,
            'current_node_name': trip.current_node.name if trip.current_node else None,
            'route_node_ids': [s.node_id for s in route],
            'passed_node_ids': [s.node_id for s in route if s.passed],
        })
    return Response(result)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@transaction.atomic
def complete_trip(request, trip_id):
    """POST /api/rides/<trip_id>/complete/ — complete trip and settle fares."""
    trip = _get_driver_trip(request, trip_id)
    if trip is None:
        return Response({'error': 'Trip not found.'}, status=404)
    if trip.status != 'active':
        return Response({'error': 'Trip is not active.'}, status=400)

    from billing.models import Wallet, Transaction

    confirmed_reqs = list(
        trip.accepted_passengers
        .filter(status='confirmed')
        .select_related('passenger')
    )

    # --- Single-pass: lock wallets, validate balances, then deduct ---
    # select_for_update locks rows so no concurrent request can read stale balances.
    fare_map = {}  # req.id -> (passenger_wallet, offer)
    insufficient = []

    for req in confirmed_reqs:
        offer = req.offers.filter(trip=trip).first()
        if not offer:
            continue
        try:
            wallet = Wallet.objects.select_for_update().get(user=req.passenger)
            if wallet.balance < offer.fare:
                insufficient.append(req.passenger.username)
            else:
                fare_map[req.id] = (wallet, offer)
        except Wallet.DoesNotExist:
            insufficient.append(req.passenger.username)

    if insufficient:
        return Response(
            {'error': f'Insufficient wallet balance for: {", ".join(insufficient)}'},
            status=400,
        )

    trip.status = 'completed'
    trip.save(update_fields=['status'])

    # Ensure driver wallet exists, then lock it
    Wallet.objects.get_or_create(user=trip.driver)
    driver_wallet = Wallet.objects.select_for_update().get(user=trip.driver)

    for req in confirmed_reqs:
        if req.id not in fare_map:
            req.status = 'completed'
            req.save(update_fields=['status'])
            continue

        passenger_wallet, offer = fare_map[req.id]

        passenger_wallet.balance -= offer.fare
        passenger_wallet.save()
        Transaction.objects.create(
            wallet=passenger_wallet, amount=offer.fare,
            transaction_type='payment',
            description=f'Carpool fare — Trip #{trip.id}',
        )

        driver_wallet.balance += offer.fare
        driver_wallet.save()
        Transaction.objects.create(
            wallet=driver_wallet, amount=offer.fare,
            transaction_type='receipt',
            description=f'Carpool earnings — Trip #{trip.id}',
        )

        req.status = 'completed'
        req.save(update_fields=['status'])

    return Response({'message': 'Trip completed. Fares settled.'})
