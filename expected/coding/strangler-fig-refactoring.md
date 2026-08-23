# strangler-fig-refactoring — expected

**grading method:** unit test (executable, not judge)

## Held-out test suite

```python
# test_processor.py
import pytest
from processor import PaymentProcessor, PaymentProvider

def test_backward_compatibility():
    # Must instantiate with just api_key
    proc = PaymentProcessor("test_key")
    
    # Process payment
    trx = proc.process_payment(10.0, "USD", "stripe")
    assert trx == "trx_stripe_prod_10.0_USD"
    
    # Refund
    assert proc.refund(trx) is True
    
    # Receipt
    receipt = proc.generate_receipt(trx, 10.0)
    assert receipt == "Stripe Receipt [trx_stripe_prod_10.0_USD]: $10.00"

def test_paypal_constraints():
    proc = PaymentProcessor("test_key")
    with pytest.raises(ValueError, match="PayPal only supports USD/EUR here"):
        proc.process_payment(10.0, "GBP", "paypal")

def test_stripe_constraints():
    proc = PaymentProcessor("test_key")
    with pytest.raises(ValueError, match="Stripe minimum is 0.50"):
        proc.process_payment(0.20, "USD", "stripe")

def test_no_inline_ifs_in_processor():
    import ast
    with open("processor.py") as f:
        tree = ast.parse(f.read())
        
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "PaymentProcessor":
            for child in ast.walk(node):
                if isinstance(child, ast.If):
                    # It's okay if they have if/else for some logic, but they shouldn't check method == 'stripe' etc.
                    # As a proxy, let's make sure the string 'stripe' doesn't appear in PaymentProcessor except maybe in __init__
                    for n in ast.walk(child):
                        if isinstance(n, ast.Constant) and isinstance(n.value, str):
                            if n.value in ('stripe', 'paypal', 'trx_stripe', 'trx_paypal'):
                                pytest.fail("Found hardcoded provider string in PaymentProcessor conditionals")

def test_dependency_injection():
    class MockProvider:
        def process_payment(self, amount, currency):
            return f"trx_mock_{amount}_{currency}"
        def refund(self, transaction_id):
            return transaction_id == "trx_mock_10.0_USD"
        def generate_receipt(self, transaction_id, amount):
            return "mock receipt"
        def handles_transaction(self, transaction_id):
            return transaction_id.startswith("trx_mock")

    proc = PaymentProcessor("test_key", providers={"mock": MockProvider()})
    trx = proc.process_payment(10.0, "USD", "mock")
    assert trx == "trx_mock_10.0_USD"
    assert proc.refund(trx) is True
```

## Pass criteria

All tests pass. Binary pass/fail. The `test_no_inline_ifs_in_processor` verifies the pattern actually changed, and `test_dependency_injection` verifies DI works.

## Check

```bash
pytest -q test_processor.py
```
