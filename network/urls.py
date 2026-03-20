from django.urls import path
from . import views

app_name = 'network'

urlpatterns = [
    path('', views.network_overview, name='overview'),
    path('nodes/add/', views.add_node, name='add_node'),
    path('nodes/<int:node_id>/delete/', views.delete_node, name='delete_node'),
    path('edges/add/', views.add_edge, name='add_edge'),
    path('edges/<int:edge_id>/delete/', views.delete_edge, name='delete_edge'),
    path('api/graph/', views.graph_data_api, name='graph_api'),
]
