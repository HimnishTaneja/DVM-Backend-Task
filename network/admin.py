from django.contrib import admin
from .models import Node, Edge


@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'description', 'outgoing_count', 'incoming_count')
    search_fields = ('name', 'description')
    ordering = ('name',)

    def outgoing_count(self, obj):
        return obj.outgoing_edges.count()
    outgoing_count.short_description = 'Out Edges'

    def incoming_count(self, obj):
        return obj.incoming_edges.count()
    incoming_count.short_description = 'In Edges'


@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ('id', 'from_node', 'to_node')
    list_select_related = ('from_node', 'to_node')
    search_fields = ('from_node__name', 'to_node__name')
    autocomplete_fields = ('from_node', 'to_node')
