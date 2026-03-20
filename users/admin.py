from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'role_badge', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('role', 'is_staff', 'is_active')
    search_fields = ('username', 'email')
    ordering = ('-date_joined',)

    fieldsets = UserAdmin.fieldsets + (
        ('CarpoolNet Role', {'fields': ('role',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('CarpoolNet Role', {'fields': ('role',)}),
    )

    def role_badge(self, obj):
        colors = {'driver': '#2563eb', 'passenger': '#059669', 'admin': '#7c3aed'}
        icons = {'driver': '🚕', 'passenger': '👤', 'admin': '⚙️'}
        c = colors.get(obj.role, '#6b7280')
        icon = icons.get(obj.role, '')
        return format_html(
            '<span style="color:{}; font-weight:600;">{} {}</span>',
            c, icon, obj.get_role_display()
        )
    role_badge.short_description = 'Role'
