"""Reservation ledger for an explicitly injected, retry-free transport.

This is not a provider tokenizer or a provider integration. Callers must supply
a reliable upper bound including the complete serialized request. Unknown usage
retains its reservation. Physical retries must re-enter ``send``.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Union


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(name + ' must be a nonnegative integer')


def _money(value):
    if isinstance(value, bool):
        raise ValueError('invalid price')
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('invalid price') from None
    if not number.is_finite() or number < 0:
        raise ValueError('price must be finite and nonnegative')
    return number


@dataclass(frozen=True, init=False)
class PriceQuote:
    input_per_million: Decimal
    output_per_million: Decimal
    source: str
    currency: str
    pricing_version: str

    def __init__(self, input_per_million: Union[Decimal, int, float, str],
                 output_per_million: Union[Decimal, int, float, str], source: str,
                 currency: str, pricing_version: str):
        object.__setattr__(self, 'input_per_million', _money(input_per_million))
        object.__setattr__(self, 'output_per_million', _money(output_per_million))
        if not isinstance(source, str) or not source.strip():
            raise ValueError('a traceable price source is required')
        if not isinstance(currency, str) or not currency.strip() or not isinstance(pricing_version, str) or not pricing_version.strip():
            raise ValueError('currency and pricing version are required')
        object.__setattr__(self, 'source', source)
        object.__setattr__(self, 'currency', currency)
        object.__setattr__(self, 'pricing_version', pricing_version)

    def cost(self, inputs, outputs):
        return (self.input_per_million * inputs + self.output_per_million * outputs) / 1000000


class BudgetExceeded(RuntimeError):
    pass


class BudgetLedger:
    def __init__(self, max_requests=0, max_tokens=0, max_cost=None, price=None):
        _integer(max_requests, 'max_requests')
        _integer(max_tokens, 'max_tokens')
        if price is not None and not isinstance(price, PriceQuote):
            raise ValueError('price must be a PriceQuote or null')
        self.max_requests, self.max_tokens = max_requests, max_tokens
        self.max_cost = None if max_cost is None else _money(max_cost)
        self.price = price
        self.requests, self.reserved_tokens = 0, 0
        self.reserved_cost = Decimal(0) if price is not None else None
        self.events = []
        self._lock = RLock()
        self.strict_cap_valid = True

    def send(self, transport, payload, *, input_token_upper_bound, max_output_tokens,
             reliable_tokenizer, sdk_retries=0):
        with self._lock:
            return self._send(transport, payload, input_token_upper_bound=input_token_upper_bound,
                              max_output_tokens=max_output_tokens, reliable_tokenizer=reliable_tokenizer,
                              sdk_retries=sdk_retries)

    def _send(self, transport, payload, *, input_token_upper_bound, max_output_tokens,
              reliable_tokenizer, sdk_retries):
        if not self.strict_cap_valid:
            raise BudgetExceeded('provider bound invalidated; further sends blocked')
        _integer(input_token_upper_bound, 'input_token_upper_bound')
        _integer(max_output_tokens, 'max_output_tokens')
        if reliable_tokenizer is not True:
            raise ValueError('a reliable full-request tokenizer bound is required')
        if type(sdk_retries) is not int or sdk_retries != 0:
            raise ValueError('hidden SDK retries must be disabled')
        if self.max_cost is not None and self.price is None:
            raise ValueError('priced budget requires an explicit price quote')
        tokens = input_token_upper_bound + max_output_tokens
        cost = None if self.price is None else self.price.cost(input_token_upper_bound, max_output_tokens)
        if self.requests + 1 > self.max_requests or self.reserved_tokens + tokens > self.max_tokens:
            raise BudgetExceeded('request or token budget exhausted before dispatch')
        if self.max_cost is not None:
            if self.reserved_cost is None or cost is None:
                raise ValueError('money budget requires a valid reservation quote')
            if self.reserved_cost + cost > self.max_cost:
                raise BudgetExceeded('price budget exhausted before dispatch')
        # Reserve before crossing the transport boundary, including failed sends.
        self.requests += 1
        self.reserved_tokens += tokens
        if cost is not None:
            self.reserved_cost += cost
        event = dict(request=self.requests, status='unknown', reserved_tokens=tokens,
                     actual_tokens=None, actual_cost=None)
        self.events.append(event)
        try:
            result = transport(payload, max_output_tokens=max_output_tokens, sdk_retries=0)
        except Exception:
            event['status'] = 'transport_error'
            raise
        usage = result.get('usage') if isinstance(result, dict) else None
        if usage is None:
            return result  # Reservation remains consumed; actuals remain unknown.
        try:
            inputs, outputs = usage['input_tokens'], usage['output_tokens']
            _integer(inputs, 'usage.input_tokens')
            _integer(outputs, 'usage.output_tokens')
        except (KeyError, TypeError, ValueError):
            event['status'] = 'invalid_usage'
            raise ValueError('invalid usage; reservation retained')
        actual_cost = None if self.price is None else self.price.cost(inputs, outputs)
        event.update(actual_tokens=inputs + outputs,
                     actual_cost=None if actual_cost is None else str(actual_cost))
        if inputs > input_token_upper_bound or outputs > max_output_tokens:
            # A broken provider/bound cannot retroactively be called a hard cap.
            self.reserved_tokens += max(0, inputs + outputs - tokens)
            if actual_cost is not None:
                self.reserved_cost += max(Decimal(0), actual_cost - cost)
            event['status'] = 'bound_breached'
            self.strict_cap_valid = False
            raise BudgetExceeded('transport exceeded bound; strict-cap guarantee invalid')
        self.reserved_tokens -= tokens - inputs - outputs
        if cost is not None:
            self.reserved_cost -= cost - actual_cost
        event['status'] = 'accounted'
        return result

    def report(self):
        return dict(physical_requests=self.requests, charged_tokens=self.reserved_tokens,
                    charged_cost=None if self.reserved_cost is None else str(self.reserved_cost),
                    currency=None if self.price is None else self.price.currency,
                    pricing_version=None if self.price is None else self.price.pricing_version,
                    price_source=None if self.price is None else self.price.source,
                    strict_cap_valid=self.strict_cap_valid,
                    usage_complete=all(e['status'] == 'accounted' for e in self.events),
                    events=list(self.events))