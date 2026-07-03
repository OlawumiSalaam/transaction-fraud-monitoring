"""Unit tests for the Canonical Evidence Schema (§6.2).

Verifies that entity types are correct, immutable (frozen), and that the
TransactionType enum covers the expected PaySim types.

Spec: §6.2, §3 (Canonical Evidence Schema principle), FR-1.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from tfm.schema.entities import (
    Account,
    AccountBehaviouralProfile,
    BeneficiaryRelationship,
    Counterparty,
    Transaction,
    TransactionType,
)
from tfm.schema.evidence import FeatureVector

_TS = datetime(2024, 1, 1, 1, 0, 0, tzinfo=UTC)


def test_transaction_type_covers_paysim_types() -> None:
    expected = {"PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"}
    assert {t.value for t in TransactionType} == expected


def test_transaction_type_fraud_types_present() -> None:
    assert TransactionType.TRANSFER == "TRANSFER"
    assert TransactionType.CASH_OUT == "CASH_OUT"


def test_transaction_is_frozen() -> None:
    txn = Transaction(
        txn_id="t1",
        step=1,
        event_ts=_TS,
        type=TransactionType.PAYMENT,
        amount=100.0,
        account_id="C1",
        counterparty_id="M1",
        direction="outbound",
        bal_orig_before=1000.0,
        bal_orig_after=900.0,
        bal_dest_before=None,
        bal_dest_after=None,
        sim_flagged=False,
        label=False,
    )
    with pytest.raises(ValidationError):
        txn.amount = 999.0  # type: ignore[misc]


def test_transaction_merchant_dest_allows_none_balances() -> None:
    txn = Transaction(
        txn_id="t1",
        step=1,
        event_ts=_TS,
        type=TransactionType.PAYMENT,
        amount=50.0,
        account_id="C1",
        counterparty_id="M1",
        direction="outbound",
        bal_orig_before=500.0,
        bal_orig_after=450.0,
        bal_dest_before=None,
        bal_dest_after=None,
        sim_flagged=False,
        label=False,
    )
    assert txn.bal_dest_before is None
    assert txn.bal_dest_after is None


def test_account_merchant_flag() -> None:
    merchant = Account(account_id="M123", first_seen_step=1, is_merchant=True)
    customer = Account(account_id="C456", first_seen_step=2, is_merchant=False)
    assert merchant.is_merchant is True
    assert customer.is_merchant is False


def test_account_is_frozen() -> None:
    acct = Account(account_id="C1", first_seen_step=1, is_merchant=False)
    with pytest.raises(ValidationError):
        acct.is_merchant = True  # type: ignore[misc]


def test_counterparty_merchant_flag() -> None:
    cp = Counterparty(counterparty_id="M1", is_merchant=True)
    assert cp.is_merchant is True


def test_account_behavioural_profile_frozen() -> None:
    profile = AccountBehaviouralProfile(
        account_id="C1",
        reference_txn_id="t1",
        txn_count_24h=3,
        amount_sum_24h=1500.0,
        distinct_counterparties_seen=2,
    )
    with pytest.raises(ValidationError):
        profile.txn_count_24h = 99  # type: ignore[misc]


def test_beneficiary_relationship_new_counterparty() -> None:
    rel = BeneficiaryRelationship(
        account_id="C1",
        counterparty_id="C2",
        reference_txn_id="t1",
        is_new_counterparty=True,
        prior_txn_count=0,
    )
    assert rel.is_new_counterparty is True
    assert rel.prior_txn_count == 0


def test_feature_vector_is_frozen() -> None:
    fv = FeatureVector(
        txn_id="t1",
        account_id="C1",
        counterparty_id="M1",
        amount=100.0,
        type_payment=True,
        type_transfer=False,
        type_cash_out=False,
        type_cash_in=False,
        type_debit=False,
        bal_orig_before=1000.0,
        bal_orig_after=900.0,
        bal_dest_before=None,
        bal_dest_after=None,
        frac_bal_orig_moved=0.1,
        orig_account_emptied=False,
        txn_count_24h=0,
        amount_sum_24h=0.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=0,
    )
    with pytest.raises(ValidationError):
        fv.amount = 999.0  # type: ignore[misc]


def test_feature_vector_none_fields_for_merchants() -> None:
    fv = FeatureVector(
        txn_id="t1",
        account_id="C1",
        counterparty_id="M1",
        amount=50.0,
        type_payment=True,
        type_transfer=False,
        type_cash_out=False,
        type_cash_in=False,
        type_debit=False,
        bal_orig_before=500.0,
        bal_orig_after=450.0,
        bal_dest_before=None,
        bal_dest_after=None,
        frac_bal_orig_moved=0.1,
        orig_account_emptied=False,
        txn_count_24h=0,
        amount_sum_24h=0.0,
        is_new_counterparty=True,
        distinct_counterparties_seen=0,
    )
    assert fv.bal_dest_before is None
    assert fv.bal_dest_after is None
