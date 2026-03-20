from rest_framework import serializers
from .models import Trip, TripSequence, CarpoolRequest, CarpoolOffer
from network.models import Node


class NodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Node
        fields = ['id', 'name']


class TripSequenceSerializer(serializers.ModelSerializer):
    node = NodeSerializer(read_only=True)

    class Meta:
        model = TripSequence
        fields = ['order', 'node', 'passed']


class TripSerializer(serializers.ModelSerializer):
    start_node = NodeSerializer(read_only=True)
    end_node = NodeSerializer(read_only=True)
    current_node = NodeSerializer(read_only=True)
    route_sequence = TripSequenceSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = [
            'id', 'driver', 'start_node', 'end_node',
            'max_passengers', 'status', 'current_node',
            'created_at', 'route_sequence',
        ]


class CarpoolOfferSerializer(serializers.ModelSerializer):
    trip_id = serializers.IntegerField(source='trip.id', read_only=True)
    driver_username = serializers.CharField(source='trip.driver.username', read_only=True)

    class Meta:
        model = CarpoolOffer
        fields = ['id', 'trip_id', 'driver_username', 'detour_nodes', 'fare', 'created_at']


class CarpoolRequestSerializer(serializers.ModelSerializer):
    passenger_username = serializers.CharField(source='passenger.username', read_only=True)
    pickup_node = NodeSerializer(read_only=True)
    destination_node = NodeSerializer(read_only=True)
    offers = CarpoolOfferSerializer(many=True, read_only=True)

    class Meta:
        model = CarpoolRequest
        fields = [
            'id', 'passenger_username', 'pickup_node', 'destination_node',
            'status', 'created_at', 'offers',
        ]


class UpdateNodeSerializer(serializers.Serializer):
    node_id = serializers.IntegerField()

    def validate_node_id(self, value):
        if not Node.objects.filter(pk=value).exists():
            raise serializers.ValidationError('Node does not exist.')
        return value


class MakeOfferSerializer(serializers.Serializer):
    request_id = serializers.IntegerField()

    def validate_request_id(self, value):
        if not CarpoolRequest.objects.filter(pk=value, status='pending').exists():
            raise serializers.ValidationError('Carpool request not found or not pending.')
        return value
