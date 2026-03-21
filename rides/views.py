from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from network.models import Node
from network.services import get_shortest_path, build_graph, is_within_proximity, calculate_detour, calculate_fare
from users.models import CustomUser
from .models import Trip, TripSequence, CarpoolRequest, CarpoolOffer


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _driver_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.role != CustomUser.IS_DRIVER:
            messages.error(request, 'Driver access required.')
            return redirect('users:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


def _passenger_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.role != CustomUser.IS_PASSENGER:
            messages.error(request, 'Passenger access required.')
            return redirect('users:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


# ---------------------------------------------------------------------------
# Shared matching helper (used by driver_dashboard and driver_requests)
# ---------------------------------------------------------------------------

def _find_matching_requests(trip, graph, proximity):
    """
    Return a list of dicts describing pending CarpoolRequests that can be
    served by *trip*, together with their pre-calculated detour and fare.

    Reuses the caller's pre-built graph to avoid repeated DB hits.
    """
    remaining_ids = list(
        trip.route_sequence.filter(passed=False)
        .order_by('order')
        .values_list('node_id', flat=True)
    )
    if not remaining_ids:
        return []

    offered_ids = set(
        CarpoolOffer.objects.filter(trip=trip).values_list('request_id', flat=True)
    )

    results = []
    pending_reqs = (
        CarpoolRequest.objects
        .filter(status='pending')
        .exclude(id__in=offered_ids)
        .select_related('passenger', 'pickup_node', 'destination_node')
    )

    for req in pending_reqs:
        if not (
            is_within_proximity(req.pickup_node_id, remaining_ids, proximity, graph)
            and is_within_proximity(req.destination_node_id, remaining_ids, proximity, graph)
        ):
            continue

        det = calculate_detour(remaining_ids, req.pickup_node_id, req.destination_node_id, graph)
        if not det:
            continue

        confirmed_pax = []
        for cr in trip.accepted_passengers.filter(status='confirmed'):
            try:
                p_idx = det['new_route'].index(cr.pickup_node_id)
                d_idx = det['new_route'].index(cr.destination_node_id, p_idx)
                confirmed_pax.append({'pickup_index': p_idx, 'dropoff_index': d_idx})
            except ValueError:
                pass

        fare = calculate_fare(det['new_route'], det['pickup_index'], det['dropoff_index'], confirmed_pax)
        results.append({
            'request':      req,
            'trip':         trip,
            'fare':         fare,
            'detour_nodes': det['detour_nodes'],
            'seats_left':   trip.max_passengers - trip.accepted_passengers.filter(status='confirmed').count(),
        })

    return results


# ---------------------------------------------------------------------------
# Driver views
# ---------------------------------------------------------------------------

@_driver_required
def driver_dashboard(request):
    active_trips = list(Trip.objects.filter(driver=request.user, status='active').order_by('-created_at'))
    past_trips = Trip.objects.filter(
        driver=request.user, status__in=['completed', 'cancelled']
    ).order_by('-created_at')[:10]

    try:
        wallet = request.user.wallet
    except Exception:
        wallet = None

    # Build graph once; reuse across all trip matching calls
    graph     = build_graph()
    proximity = getattr(settings, 'CARPOOL_PROXIMITY_NODES', 2)
    incoming  = []
    seen_req_ids = set()

    for trip in active_trips:
        seats_left = trip.max_passengers - trip.accepted_passengers.filter(status='confirmed').count()
        if seats_left <= 0:
            continue
        for match in _find_matching_requests(trip, graph, proximity):
            if match['request'].id not in seen_req_ids:
                incoming.append(match)
                seen_req_ids.add(match['request'].id)

    return render(request, 'rides/driver_dashboard.html', {
        'active_trips': active_trips,
        'past_trips':   past_trips,
        'wallet':       wallet,
        'incoming':     incoming,
    })


@_driver_required
def publish_trip(request):
    nodes = Node.objects.all().order_by('name')
    if request.method == 'POST':
        start_id = request.POST.get('start_node')
        end_id = request.POST.get('end_node')
        max_passengers = int(request.POST.get('max_passengers', 3))

        if not start_id or not end_id:
            messages.error(request, 'Please select start and end nodes.')
            return render(request, 'rides/publish_trip.html', {'nodes': nodes})

        if start_id == end_id:
            messages.error(request, 'Start and end nodes must be different.')
            return render(request, 'rides/publish_trip.html', {'nodes': nodes})

        try:
            start_id = int(start_id)
            end_id = int(end_id)
            max_passengers = max(1, min(int(request.POST.get('max_passengers', 3)), 8))
        except (ValueError, TypeError):
            messages.error(request, 'Invalid node or passenger count.')
            return render(request, 'rides/publish_trip.html', {'nodes': nodes})

        path = get_shortest_path(start_id, end_id)
        if not path:
            messages.error(request, 'No route exists between the selected nodes.')
            return render(request, 'rides/publish_trip.html', {'nodes': nodes})

        with transaction.atomic():
            trip = Trip.objects.create(
                driver=request.user,
                start_node_id=start_id,
                end_node_id=end_id,
                current_node_id=start_id,
                max_passengers=max_passengers,
                status='active',
            )
            for order, node_id in enumerate(path):
                TripSequence.objects.create(trip=trip, node_id=node_id, order=order)

        messages.success(request, f'Trip published! Route has {len(path)} nodes.')
        return redirect('rides:trip_detail', trip_id=trip.id)

    return render(request, 'rides/publish_trip.html', {'nodes': nodes})


@_driver_required
def trip_detail(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, driver=request.user)
    route = trip.route_sequence.select_related('node').order_by('order')
    confirmed_requests = trip.accepted_passengers.filter(
        status='confirmed'
    ).select_related('passenger', 'pickup_node', 'destination_node')
    offers_made = CarpoolOffer.objects.filter(
        trip=trip
    ).select_related('request__passenger', 'request__pickup_node', 'request__destination_node')

    return render(request, 'rides/trip_detail.html', {
        'trip': trip,
        'route': route,
        'confirmed_requests': confirmed_requests,
        'offers_made': offers_made,
    })


@_driver_required
@require_POST
def cancel_trip(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, driver=request.user)
    if trip.status != 'active':
        messages.error(request, 'Only active trips can be cancelled.')
    else:
        trip.status = 'cancelled'
        trip.save(update_fields=['status'])
        # Cancel all pending requests tied to this trip via offers
        for offer in trip.offers_made.all():
            if offer.request.status == 'confirmed' and offer.request.confirmed_trip == trip:
                offer.request.status = 'pending'
                offer.request.confirmed_trip = None
                offer.request.save(update_fields=['status', 'confirmed_trip'])
        messages.success(request, 'Trip cancelled.')
    return redirect('rides:driver_dashboard')


@_driver_required
def driver_requests(request, trip_id):
    """SSR page showing all incoming carpool requests for a trip."""
    trip = get_object_or_404(Trip, pk=trip_id, driver=request.user)

    graph     = build_graph()
    proximity = getattr(settings, 'CARPOOL_PROXIMITY_NODES', 2)
    eligible  = _find_matching_requests(trip, graph, proximity)

    existing_offers = CarpoolOffer.objects.filter(
        trip=trip
    ).select_related('request__passenger', 'request__pickup_node', 'request__destination_node')

    return render(request, 'rides/driver_requests.html', {
        'trip': trip,
        'eligible_requests': eligible,
        'existing_offers': existing_offers,
    })


@_driver_required
@require_POST
@transaction.atomic
def make_offer_view(request, trip_id):
    """HTML form submit version of make_offer API."""
    trip = get_object_or_404(Trip, pk=trip_id, driver=request.user)
    request_id = request.POST.get('request_id')
    carpool_req = get_object_or_404(CarpoolRequest, pk=request_id, status='pending')

    if CarpoolOffer.objects.filter(trip=trip, request=carpool_req).exists():
        messages.warning(request, 'You already made an offer for this request.')
        return redirect('rides:driver_requests', trip_id=trip_id)

    remaining_ids = list(
        trip.route_sequence.filter(passed=False)
        .order_by('order')
        .values_list('node_id', flat=True)
    )
    det = calculate_detour(remaining_ids, carpool_req.pickup_node_id, carpool_req.destination_node_id)
    if not det:
        messages.error(request, 'Cannot serve this passenger — no viable route.')
        return redirect('rides:driver_requests', trip_id=trip_id)

    confirmed_passengers = []
    for cr in trip.accepted_passengers.filter(status='confirmed'):
        try:
            p_idx = det['new_route'].index(cr.pickup_node_id)
            d_idx = det['new_route'].index(cr.destination_node_id, p_idx)
            confirmed_passengers.append({'pickup_index': p_idx, 'dropoff_index': d_idx})
        except ValueError:
            pass

    fare = calculate_fare(
        det['new_route'],
        det['pickup_index'],
        det['dropoff_index'],
        confirmed_passengers,
    )

    CarpoolOffer.objects.create(
        request=carpool_req, trip=trip,
        detour_nodes=det['detour_nodes'], fare=fare,
    )
    messages.success(request, f'Offer sent! Detour: {det["detour_nodes"]} hops | Fare: ${fare}')
    return redirect('rides:driver_requests', trip_id=trip_id)


@_driver_required
@require_POST
@transaction.atomic
def accept_request(request, trip_id, request_id):
    """
    Uber-style one-tap accept: driver picks passenger → instantly confirmed.
    Creates the CarpoolOffer and flips the CarpoolRequest to 'confirmed' in one shot.
    """
    trip = get_object_or_404(Trip, pk=trip_id, driver=request.user, status='active')
    # Lock the row so two concurrent accepts for the same request can't both succeed
    carpool_req = get_object_or_404(
        CarpoolRequest.objects.select_for_update(), pk=request_id, status='pending'
    )

    if CarpoolOffer.objects.filter(trip=trip, request=carpool_req).exists():
        messages.warning(request, 'You already accepted this ride.')
        return redirect('rides:driver_dashboard')

    # Seats check
    seats_taken = trip.accepted_passengers.filter(status='confirmed').count()
    if seats_taken >= trip.max_passengers:
        messages.error(request, 'Your trip is already full.')
        return redirect('rides:driver_dashboard')

    remaining_ids = list(
        trip.route_sequence.filter(passed=False)
        .order_by('order')
        .values_list('node_id', flat=True)
    )
    det = calculate_detour(remaining_ids, carpool_req.pickup_node_id, carpool_req.destination_node_id)
    if not det:
        messages.error(request, 'Cannot serve this passenger — no viable detour.')
        return redirect('rides:driver_dashboard')

    confirmed_pax = []
    for cr in trip.accepted_passengers.filter(status='confirmed'):
        try:
            p_idx = det['new_route'].index(cr.pickup_node_id)
            d_idx = det['new_route'].index(cr.destination_node_id, p_idx)
            confirmed_pax.append({'pickup_index': p_idx, 'dropoff_index': d_idx})
        except ValueError:
            pass

    fare = calculate_fare(
        det['new_route'], det['pickup_index'], det['dropoff_index'], confirmed_pax
    )

    # Create offer
    CarpoolOffer.objects.create(
        request=carpool_req, trip=trip,
        detour_nodes=det['detour_nodes'], fare=fare,
    )

    # Auto-confirm — driver accepted, passenger is on board
    carpool_req.status        = 'confirmed'
    carpool_req.confirmed_trip = trip
    carpool_req.save(update_fields=['status', 'confirmed_trip'])

    messages.success(
        request,
        'Ride accepted! {} is confirmed. Fare: ${}'.format(
            carpool_req.passenger.username, fare
        )
    )
    return redirect('rides:driver_dashboard')


# ---------------------------------------------------------------------------
# Passenger views
# ---------------------------------------------------------------------------

@_passenger_required
def passenger_dashboard(request):
    active_requests = CarpoolRequest.objects.filter(
        passenger=request.user,
        status__in=['pending', 'confirmed'],
    ).order_by('-created_at')
    past_requests = CarpoolRequest.objects.filter(
        passenger=request.user,
        status__in=['completed', 'cancelled'],
    ).order_by('-created_at')[:10]

    try:
        wallet = request.user.wallet
    except Exception:
        wallet = None

    return render(request, 'rides/passenger_dashboard.html', {
        'active_requests': active_requests,
        'past_requests': past_requests,
        'wallet': wallet,
    })


@_passenger_required
def submit_request(request):
    nodes = Node.objects.all().order_by('name')
    if request.method == 'POST':
        pickup_id = request.POST.get('pickup_node')
        dest_id = request.POST.get('destination_node')

        if not pickup_id or not dest_id:
            messages.error(request, 'Please select both pickup and destination nodes.')
            return render(request, 'rides/submit_request.html', {'nodes': nodes})

        if pickup_id == dest_id:
            messages.error(request, 'Pickup and destination must be different.')
            return render(request, 'rides/submit_request.html', {'nodes': nodes})

        # Check a path exists
        path = get_shortest_path(int(pickup_id), int(dest_id))
        if not path:
            messages.error(request, 'No route found between those nodes.')
            return render(request, 'rides/submit_request.html', {'nodes': nodes})

        req = CarpoolRequest.objects.create(
            passenger=request.user,
            pickup_node_id=int(pickup_id),
            destination_node_id=int(dest_id),
        )
        messages.success(request, 'Carpool request submitted! Waiting for driver offers.')
        return redirect('rides:request_detail', request_id=req.id)

    return render(request, 'rides/submit_request.html', {'nodes': nodes})


@_passenger_required
def request_detail(request, request_id):
    carpool_req = get_object_or_404(CarpoolRequest, pk=request_id, passenger=request.user)
    offers = carpool_req.offers.select_related('trip__driver').order_by('fare')
    return render(request, 'rides/request_detail.html', {
        'request': carpool_req,
        'offers': offers,
    })


@_passenger_required
@require_POST
@transaction.atomic
def confirm_offer(request, request_id):
    carpool_req = get_object_or_404(CarpoolRequest, pk=request_id, passenger=request.user)
    if carpool_req.status != 'pending':
        messages.error(request, 'Request is no longer pending.')
        return redirect('rides:request_detail', request_id=request_id)

    offer_id = request.POST.get('offer_id')
    offer = get_object_or_404(CarpoolOffer, pk=offer_id, request=carpool_req)

    # Check wallet
    try:
        wallet = request.user.wallet
        if wallet.balance < offer.fare:
            messages.error(
                request,
                f'Insufficient wallet balance. You need ${offer.fare} but have ${wallet.balance}. '
                'Please top up your wallet.'
            )
            return redirect('rides:request_detail', request_id=request_id)
    except Exception:
        messages.error(request, 'Wallet not found. Please contact support.')
        return redirect('rides:request_detail', request_id=request_id)

    # Check trip still has capacity
    trip = offer.trip
    confirmed_count = trip.accepted_passengers.filter(status='confirmed').count()
    if confirmed_count >= trip.max_passengers:
        messages.error(request, 'Sorry, that trip is now full.')
        return redirect('rides:request_detail', request_id=request_id)

    carpool_req.status = 'confirmed'
    carpool_req.confirmed_trip = trip
    carpool_req.save(update_fields=['status', 'confirmed_trip'])
    messages.success(request, f'Carpool confirmed with {trip.driver.username}! Fare: ${offer.fare}')
    return redirect('rides:passenger_dashboard')


@_passenger_required
@require_POST
def cancel_request(request, request_id):
    carpool_req = get_object_or_404(CarpoolRequest, pk=request_id, passenger=request.user)
    if carpool_req.status not in ('pending', 'confirmed'):
        messages.error(request, 'This request cannot be cancelled.')
    else:
        carpool_req.status = 'cancelled'
        carpool_req.confirmed_trip = None
        carpool_req.save(update_fields=['status', 'confirmed_trip'])
        messages.success(request, 'Request cancelled.')
    return redirect('rides:passenger_dashboard')
