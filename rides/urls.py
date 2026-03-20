from django.urls import path
from . import views, api_views

app_name = 'rides'

urlpatterns = [
    # --- Driver SSR ---
    path('driver/', views.driver_dashboard, name='driver_dashboard'),
    path('driver/trip/new/', views.publish_trip, name='publish_trip'),
    path('driver/trip/<int:trip_id>/', views.trip_detail, name='trip_detail'),
    path('driver/trip/<int:trip_id>/cancel/', views.cancel_trip, name='cancel_trip'),
    path('driver/trip/<int:trip_id>/requests/', views.driver_requests, name='driver_requests'),
    path('driver/trip/<int:trip_id>/offer/', views.make_offer_view, name='make_offer_view'),
    path('driver/trip/<int:trip_id>/accept/<int:request_id>/', views.accept_request, name='accept_request'),

    # --- Passenger SSR ---
    path('passenger/', views.passenger_dashboard, name='passenger_dashboard'),
    path('passenger/request/new/', views.submit_request, name='submit_request'),
    path('passenger/request/<int:request_id>/', views.request_detail, name='request_detail'),
    path('passenger/request/<int:request_id>/confirm/', views.confirm_offer, name='confirm_offer'),
    path('passenger/request/<int:request_id>/cancel/', views.cancel_request, name='cancel_request'),

    # --- Driver DRF API ---
    path('api/trip/<int:trip_id>/update-node/', api_views.update_current_node, name='api_update_node'),
    path('api/trip/<int:trip_id>/requests/', api_views.trip_carpool_requests, name='api_trip_requests'),
    path('api/trip/<int:trip_id>/make-offer/', api_views.make_offer, name='api_make_offer'),
    path('api/trip/<int:trip_id>/complete/', api_views.complete_trip, name='api_complete_trip'),

    # --- Public polling endpoints (no auth) ---
    path('api/trip/<int:trip_id>/status/', api_views.trip_status, name='api_trip_status'),
    path('api/trips/active/', api_views.active_trips_map, name='api_active_trips'),
]
