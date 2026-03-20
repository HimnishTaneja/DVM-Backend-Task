from django.contrib import admin
from django.utils.html import format_html
from .models import Trip, TripSequence, CarpoolRequest, CarpoolOffer


class TripSequenceInline(admin.TabularInline):
    model = TripSequence
    extra = 0
    readonly_fields = ('node', 'order', 'passed')
    ordering = ('order',)
    can_delete = False


class CarpoolOfferInline(admin.TabularInline):
    model = CarpoolOffer
    extra = 0
    readonly_fields = ('trip', 'detour_nodes', 'fare', 'created_at')
    can_delete = False


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ('id', 'driver', 'start_node', 'end_node', 'status_badge',
                    'max_passengers', 'confirmed_count', 'current_node', 'created_at')
    list_filter = ('status',)
    search_fields = ('driver__username', 'start_node__name', 'end_node__name')
    list_select_related = ('driver', 'start_node', 'end_node', 'current_node')
    readonly_fields = ('created_at',)
    inlines = (TripSequenceInline,)
    ordering = ('-created_at',)

    def status_badge(self, obj):
        colors = {'active': '#059669', 'completed': '#2563eb', 'cancelled': '#dc2626'}
        c = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color:{}; font-weight:600;">{}</span>', c, obj.get_status_display()
        )
    status_badge.short_description = 'Status'

    def confirmed_count(self, obj):
        return obj.accepted_passengers.filter(status='confirmed').count()
    confirmed_count.short_description = 'Passengers'


@admin.register(CarpoolRequest)
class CarpoolRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'passenger', 'pickup_node', 'destination_node',
                    'status', 'offers_count', 'confirmed_trip', 'created_at')
    list_filter = ('status',)
    search_fields = ('passenger__username', 'pickup_node__name', 'destination_node__name')
    list_select_related = ('passenger', 'pickup_node', 'destination_node', 'confirmed_trip')
    readonly_fields = ('created_at',)
    inlines = (CarpoolOfferInline,)
    ordering = ('-created_at',)

    def offers_count(self, obj):
        return obj.offers.count()
    offers_count.short_description = 'Offers'


@admin.register(CarpoolOffer)
class CarpoolOfferAdmin(admin.ModelAdmin):
    list_display = ('id', 'trip', 'request', 'detour_nodes', 'fare', 'created_at')
    list_select_related = ('trip__driver', 'request__passenger')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)
