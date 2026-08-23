# strangler-fig-refactoring

**dimension(s):** raw model, coding harness
**difficulty tier:** hard

## Instruction

The `processor.py` file contains a legacy monolith `PaymentProcessor` that handles Stripe and PayPal logic inline using many `if`/`elif` checks across multiple methods (`process_payment`, `refund`, and `generate_receipt`). This has become unmaintainable.

Your task is to refactor this monolith using the Strategy/Provider pattern. You must:
1. Create a decoupled `PaymentProvider` protocol (or abstract base class).
2. Extract the Stripe and PayPal logic into separate provider classes (`StripeProvider`, `PayPalProvider`).
3. Update `PaymentProcessor` to accept a dictionary mapping string provider names to their corresponding provider instances.
4. The `PaymentProcessor` methods must delegate to the appropriate provider without any `if type == 'stripe'` style checks.
5. **Crucial:** The public signature and behavior of `PaymentProcessor.__init__` and all its methods must remain completely backward-compatible for existing clients. You should default to initializing the built-in providers if none are passed in.

Do not break the existing semantics. Only standard library imports are allowed.

## Environment/setup

Fresh checkout containing:

```python
# processor.py
"""Legacy monolith payment processor."""

class PaymentProcessor:
    def __init__(self, api_key: str, env: str = "prod"):
        self.api_key = api_key
        self.env = env
        
    def process_payment(self, amount: float, currency: str, method: str) -> str:
        """Process a payment and return a transaction ID."""
        if method == 'stripe':
            if amount < 0.50:
                raise ValueError("Stripe minimum is 0.50")
            return f"trx_stripe_{self.env}_{amount}_{currency}"
        elif method == 'paypal':
            if currency not in ['USD', 'EUR']:
                raise ValueError("PayPal only supports USD/EUR here")
            return f"trx_paypal_{self.env}_{amount}_{currency}"
        else:
            raise ValueError(f"Unknown method {method}")
            
    def refund(self, transaction_id: str) -> bool:
        """Refund a transaction."""
        if transaction_id.startswith("trx_stripe"):
            # Stripe refund logic
            return True
        elif transaction_id.startswith("trx_paypal"):
            # PayPal refund logic
            return True
        else:
            raise ValueError("Unknown transaction format")
            
    def generate_receipt(self, transaction_id: str, amount: float) -> str:
        """Generate a receipt string."""
        if transaction_id.startswith("trx_stripe"):
            return f"Stripe Receipt [{transaction_id}]: ${amount:.2f}"
        elif transaction_id.startswith("trx_paypal"):
            return f"PayPal Receipt [{transaction_id}]: ${amount:.2f}"
        else:
            raise ValueError("Unknown transaction format")
```

## Constraints

- `PaymentProcessor` methods must have the exact same signatures and types.
- The default `PaymentProcessor(api_key)` constructor must still work without clients needing to pass provider instances explicitly, but it should be structured to allow dependency injection.
- Zero `if method == 'stripe'` or `if transaction_id.startswith("trx_stripe")` in `PaymentProcessor` methods.
- Standard library only.
