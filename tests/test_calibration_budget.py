from decimal import Decimal

import pytest

from scripts.calibration_budget import BudgetExceeded, BudgetLedger, PriceQuote


def send(ledger, transport, **overrides):
    args = dict(input_token_upper_bound=10, max_output_tokens=5,
                reliable_tokenizer=True, sdk_retries=0)
    args.update(overrides)
    return ledger.send(transport, {'synthetic': True}, **args)


def test_budget_blocks_before_second_physical_send_and_retains_unknown_usage():
    calls = []
    def fake(*args, **kwargs):
        calls.append(kwargs)
        return {}
    ledger = BudgetLedger(2, 20)
    send(ledger, fake)
    with pytest.raises(BudgetExceeded):
        send(ledger, fake)
    assert len(calls) == 1 and calls[0]['sdk_retries'] == 0
    assert ledger.report()['charged_tokens'] == 15
    assert ledger.report()['events'][0]['actual_tokens'] is None
    assert ledger.report()['charged_cost'] is None


def test_each_explicit_retry_consumes_a_request_and_reservation():
    calls = []
    def failing(*args, **kwargs):
        calls.append(1)
        raise OSError('synthetic failure')
    ledger = BudgetLedger(2, 100)
    for _ in range(2):
        with pytest.raises(OSError):
            send(ledger, failing)
    with pytest.raises(BudgetExceeded):
        send(ledger, failing)
    assert len(calls) == 2 and ledger.report()['charged_tokens'] == 30


@pytest.mark.parametrize('overrides', [dict(reliable_tokenizer=False),
    dict(sdk_retries=2), dict(input_token_upper_bound=None), dict(max_output_tokens=True)])
def test_unreliable_bounds_and_hidden_retries_never_dispatch(overrides):
    with pytest.raises(ValueError):
        send(BudgetLedger(1, 100), lambda *a, **k: pytest.fail('must not send'), **overrides)


def test_unknown_price_cannot_become_free_or_satisfy_a_priced_cap():
    with pytest.raises(ValueError):
        send(BudgetLedger(1, 100, max_cost=1), lambda *a, **k: pytest.fail('must not send'))
    with pytest.raises(ValueError):
        PriceQuote(float('nan'), 0, 'fixture', 'USD', 'synthetic-v1')


def test_price_reservation_is_checked_before_send_and_reconciled_after_usage():
    price = PriceQuote(1, 2, 'synthetic quote, USD/million tokens; not a provider price', 'USD', 'synthetic-v1')
    with pytest.raises(BudgetExceeded):
        send(BudgetLedger(1, 100, max_cost='0.000019', price=price),
             lambda *a, **k: pytest.fail('must not send'))
    ledger = BudgetLedger(1, 100, max_cost='0.00002', price=price)
    send(ledger, lambda *a, **k: {'usage': {'input_tokens': 3, 'output_tokens': 2}})
    assert ledger.reserved_tokens == 5 and ledger.reserved_cost == Decimal('.000007')


def test_provider_overrun_is_recorded_as_breach_not_successful_hard_cap():
    ledger = BudgetLedger(2, 30)
    with pytest.raises(BudgetExceeded, match='strict-cap'):
        send(ledger, lambda *a, **k: {'usage': {'input_tokens': 40, 'output_tokens': 8}})
    assert ledger.reserved_tokens == 48
    assert ledger.report()['events'][0]['status'] == 'bound_breached'
    with pytest.raises(BudgetExceeded):
        send(ledger, lambda *a, **k: pytest.fail('must not send'))


def test_invalid_usage_does_not_refund_reservation():
    ledger = BudgetLedger(1, 15)
    with pytest.raises(ValueError):
        send(ledger, lambda *a, **k: {'usage': {'input_tokens': True, 'output_tokens': 0}})
    assert ledger.reserved_tokens == 15


def test_broken_provider_bound_blocks_all_later_sends_even_with_budget_remaining():
    ledger = BudgetLedger(5, 1000)
    with pytest.raises(BudgetExceeded):
        send(ledger, lambda *a, **k: {'usage': {'input_tokens': 11, 'output_tokens': 1}})
    with pytest.raises(BudgetExceeded, match='invalidated'):
        send(ledger, lambda *a, **k: pytest.fail('a breached bound is no longer reliable'))