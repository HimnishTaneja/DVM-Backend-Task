from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from .models import Wallet, Transaction


@login_required
def wallet_view(request):
    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.order_by('-timestamp')[:30]
    return render(request, 'billing/wallet.html', {
        'wallet': wallet,
        'transactions': transactions,
    })


@login_required
@require_POST
def top_up(request):
    amount_str = request.POST.get('amount', '0')
    try:
        amount = Decimal(amount_str)
        if amount <= 0:
            raise ValueError
    except (InvalidOperation, ValueError):
        messages.error(request, 'Invalid amount. Please enter a positive number.')
        return redirect('billing:wallet')

    if amount > 10000:
        messages.error(request, 'Maximum single top-up is $10,000.')
        return redirect('billing:wallet')

    wallet, _ = Wallet.objects.get_or_create(user=request.user)
    wallet.balance += amount
    wallet.save(update_fields=['balance'])
    Transaction.objects.create(
        wallet=wallet,
        amount=amount,
        transaction_type='deposit',
        description=f'Wallet top-up of ${amount}',
    )
    messages.success(request, f'${amount:.2f} added to your wallet. New balance: ${wallet.balance:.2f}')
    return redirect('billing:wallet')
