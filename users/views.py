from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.generic import CreateView, FormView
from django.urls import reverse_lazy

from .forms import RegisterForm
from .models import CustomUser


class LoginView(FormView):
    template_name = 'users/login.html'
    form_class = AuthenticationForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('users:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        login(self.request, form.get_user())
        return redirect('users:dashboard')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Sign In'
        return ctx


class RegisterView(CreateView):
    template_name = 'users/register.html'
    form_class = RegisterForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('users:dashboard')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend='django.contrib.auth.backends.ModelBackend')
        messages.success(self.request, f'Welcome, {user.username}! Your account has been created.')
        return redirect('users:dashboard')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['title'] = 'Create Account'
        return ctx


@login_required
def dashboard(request):
    """Role-based redirect to the correct dashboard."""
    user = request.user
    if user.role == CustomUser.IS_DRIVER:
        return redirect('rides:driver_dashboard')
    elif user.role == CustomUser.IS_PASSENGER:
        return redirect('rides:passenger_dashboard')
    else:
        # admin or staff → Django admin
        return redirect('admin:index')


def logout_view(request):
    logout(request)
    messages.info(request, 'You have been logged out.')
    return redirect('users:login')
