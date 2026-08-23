#!/usr/bin/env bash
set -euo pipefail

cat << 'PYEOF' > processor.py
"""Refactored payment processor using Strategy/Provider pattern."""

from typing import Protocol, Dict, Optional, runtime_checkable


@runtime_checkable
class PaymentProvider(Protocol):
    def process_payment(self, amount: float, currency: str) -> str:
        ...

    def refund(self, transaction_id: str) -> bool:
        ...

    def generate_receipt(self, transaction_id: str, amount: float) -> str:
        ...

    def handles_transaction(self, transaction_id: str) -> bool:
        ...


class StripeProvider:
    def __init__(self, env: str = "prod"):
        self.env = env

    def process_payment(self, amount: float, currency: str) -> str:
        if amount < 0.50:
            raise ValueError("Stripe minimum is 0.50")
        return f"trx_stripe_{self.env}_{amount}_{currency}"

    def refund(self, transaction_id: str) -> bool:
        return True

    def generate_receipt(self, transaction_id: str, amount: float) -> str:
        return f"Stripe Receipt [{transaction_id}]: ${amount:.2f}"

    def handles_transaction(self, transaction_id: str) -> bool:
        return transaction_id.startswith("trx_stripe")


class PayPalProvider:
    def __init__(self, env: str = "prod"):
        self.env = env

    def process_payment(self, amount: float, currency: str) -> str:
        if currency not in ['USD', 'EUR']:
            raise ValueError("PayPal only supports USD/EUR here")
        return f"trx_paypal_{self.env}_{amount}_{currency}"

    def refund(self, transaction_id: str) -> bool:
        return True

    def generate_receipt(self, transaction_id: str, amount: float) -> str:
        return f"PayPal Receipt [{transaction_id}]: ${amount:.2f}"

    def handles_transaction(self, transaction_id: str) -> bool:
        return transaction_id.startswith("trx_paypal")


def _default_providers(env: str) -> Dict[str, PaymentProvider]:
    return {
        "stripe": StripeProvider(env=env),
        "paypal": PayPalProvider(env=env),
    }


class PaymentProcessor:
    def __init__(self, api_key: str, env: str = "prod", providers: Optional[Dict[str, PaymentProvider]] = None):
        self.api_key = api_key
        self.env = env
        self.providers = dict(providers) if providers is not None else _default_providers(self.env)

    def _get_provider_for_trx(self, transaction_id: str) -> PaymentProvider:
        for provider in self.providers.values():
            if provider.handles_transaction(transaction_id):
                return provider
        raise ValueError("Unknown transaction format")

    def process_payment(self, amount: float, currency: str, method: str) -> str:
        """Process a payment and return a transaction ID."""
        provider = self.providers.get(method)
        if not provider:
            raise ValueError(f"Unknown method {method}")
        return provider.process_payment(amount, currency)

    def refund(self, transaction_id: str) -> bool:
        """Refund a transaction."""
        provider = self._get_provider_for_trx(transaction_id)
        return provider.refund(transaction_id)

    def generate_receipt(self, transaction_id: str, amount: float) -> str:
        """Generate a receipt string."""
        provider = self._get_provider_for_trx(transaction_id)
        return provider.generate_receipt(transaction_id, amount)
PYEOF
chmod +x solutions/coding/strangler-fig-refactoring.sh
