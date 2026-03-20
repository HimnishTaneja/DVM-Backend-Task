import json
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .models import Node, Edge
from .services import build_graph, get_shortest_path


def _require_admin(view_func):
    """Decorator: user must be staff OR have role='admin'."""
    from functools import wraps
    from users.models import CustomUser

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('users:login')
        if not (request.user.is_staff or request.user.role == CustomUser.IS_ADMIN):
            messages.error(request, 'Admin access required.')
            return redirect('users:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped


@_require_admin
def network_overview(request):
    """Show all nodes and edges; admin can manage the graph here."""
    nodes = Node.objects.all().order_by('name')
    edges = Edge.objects.select_related('from_node', 'to_node').all()

    # Build JSON for D3 visualisation
    nodes_json = [{'id': n.id, 'name': n.name} for n in nodes]
    edges_json = [
        {'source': e.from_node.id, 'target': e.to_node.id}
        for e in edges
    ]

    return render(request, 'network/overview.html', {
        'nodes': nodes,
        'edges': edges,
        'nodes_json': json.dumps(nodes_json),
        'edges_json': json.dumps(edges_json),
    })


@_require_admin
@require_POST
def add_node(request):
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    if not name:
        messages.error(request, 'Node name is required.')
    elif Node.objects.filter(name=name).exists():
        messages.error(request, f'Node "{name}" already exists.')
    else:
        Node.objects.create(name=name, description=description)
        messages.success(request, f'Node "{name}" added.')
    return redirect('network:overview')


@_require_admin
@require_POST
def delete_node(request, node_id):
    node = get_object_or_404(Node, pk=node_id)
    name = node.name
    node.delete()
    messages.success(request, f'Node "{name}" deleted.')
    return redirect('network:overview')


@_require_admin
@require_POST
def add_edge(request):
    from_id = request.POST.get('from_node')
    to_id = request.POST.get('to_node')
    if not from_id or not to_id:
        messages.error(request, 'Both nodes are required.')
        return redirect('network:overview')
    if from_id == to_id:
        messages.error(request, 'Self-loops are not allowed.')
        return redirect('network:overview')
    from_node = get_object_or_404(Node, pk=from_id)
    to_node = get_object_or_404(Node, pk=to_id)
    if Edge.objects.filter(from_node=from_node, to_node=to_node).exists():
        messages.error(request, f'Edge {from_node} → {to_node} already exists.')
    else:
        Edge.objects.create(from_node=from_node, to_node=to_node)
        messages.success(request, f'Edge {from_node} → {to_node} added.')
    return redirect('network:overview')


@_require_admin
@require_POST
def delete_edge(request, edge_id):
    edge = get_object_or_404(Edge, pk=edge_id)
    label = str(edge)
    edge.delete()
    messages.success(request, f'Edge "{label}" deleted.')
    return redirect('network:overview')


def graph_data_api(request):
    """JSON endpoint for D3 graph rendering (no auth required for viewing)."""
    nodes = list(Node.objects.values('id', 'name', 'description'))
    edges = list(
        Edge.objects.values('id', 'from_node_id', 'to_node_id')
    )
    return JsonResponse({'nodes': nodes, 'edges': edges})
