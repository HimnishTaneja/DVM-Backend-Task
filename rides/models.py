from django.db import models
from django.conf import settings
from network.models import Node

class Trip(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ]

    driver = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='trips_as_driver', on_delete=models.CASCADE)
    start_node = models.ForeignKey(Node, related_name='trips_starting', on_delete=models.CASCADE)
    end_node = models.ForeignKey(Node, related_name='trips_ending', on_delete=models.CASCADE)
    max_passengers = models.PositiveIntegerField(default=3)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='active')
    current_node = models.ForeignKey(Node, related_name='trips_currently_at', on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Trip {self.id} by {self.driver.username}: {self.start_node} -> {self.end_node}"

class TripSequence(models.Model):
    trip = models.ForeignKey(Trip, related_name='route_sequence', on_delete=models.CASCADE)
    node = models.ForeignKey(Node, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    passed = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']
        unique_together = ('trip', 'node')

    def __str__(self):
        return f"Trip {self.trip.id}: step {self.order} at {self.node.name}"

class CarpoolRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed')
    ]
    passenger = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='carpool_requests', on_delete=models.CASCADE)
    pickup_node = models.ForeignKey(Node, related_name='pickup_requests', on_delete=models.CASCADE)
    destination_node = models.ForeignKey(Node, related_name='dropoff_requests', on_delete=models.CASCADE)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_trip = models.ForeignKey(Trip, related_name='accepted_passengers', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"Req {self.id} by {self.passenger.username}"

class CarpoolOffer(models.Model):
    request = models.ForeignKey(CarpoolRequest, related_name='offers', on_delete=models.CASCADE)
    trip = models.ForeignKey(Trip, related_name='offers_made', on_delete=models.CASCADE)
    detour_nodes = models.IntegerField()
    fare = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Offer by Trip {self.trip.id} for Req {self.request.id}"
