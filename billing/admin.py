from django.contrib import admin
from .models import Wallet, Transaction


class TransactionInline(admin.TabularInline):
    model = Transaction
    extra = 0
    readonly_fields = ('amount', 'transaction_type', 'description', 'timestamp')
    ordering = ('-timestamp',)
    can_delete = False
    max_num = 20


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'transaction_count', 'created_at')
    search_fields = ('user__username', 'user__email')
    list_select_related = ('user',)
    readonly_fields = ('created_at',)
    inlines = (TransactionInline,)
    ordering = ('-balance',)

    def transaction_count(self, obj):
        return obj.transactions.count()
    transaction_count.short_description = 'Transactions'


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'wallet_user', 'transaction_type', 'amount', 'description', 'timestamp')
    list_filter = ('transaction_type',)
    search_fields = ('wallet__user__username', 'description')
    list_select_related = ('wallet__user',)
    readonly_fields = ('timestamp',)
    ordering = ('-timestamp',)

    def wallet_user(self, obj):
        return obj.wallet.user.username
    wallet_user.short_description = 'User'
