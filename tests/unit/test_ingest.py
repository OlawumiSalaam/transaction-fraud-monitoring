"""Unit tests for the PaySim ingestion pipeline (FR-1).

Verifies that load_paysim_csv correctly maps PaySim column names to the
canonical schema, derives event_ts, detects merchant counterparties, nulls
destination balances for merchants, and produces stable txn_ids.

Verifies that ingest_to_db persists accounts, counterparties, and transactions
idempotently, and that sim_flagged is stored (never used as a feature).

Spec: FR-1, §6.2, §6.3, R1 (Addendum §5).
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from tfm.data.ingest import PAYSIM_BASE_EPOCH, ingest_to_db, load_paysim_csv
from tfm.persistence.models import Account, Counterparty, Transaction

# Minimal PaySim CSV fixture covering:
#   row 0 — PAYMENT to merchant M67890 (dest balances should be nulled)
#   row 1 — TRANSFER to peer C11111 (dest balances preserved)
#   row 2 — CASH_OUT fraud to peer C22222 (label=1)
#   row 3 — different account C99999, PAYMENT to merchant
_PAYSIM_CSV = """\
step,type,amount,nameOrig,oldbalanceOrg,newbalanceOrig,nameDest,oldbalanceDest,newbalanceDest,isFraud,isFlaggedFraud
1,PAYMENT,100.0,C12345,5000.0,4900.0,M67890,0.0,0.0,0,0
2,TRANSFER,500.0,C12345,4900.0,4400.0,C11111,1000.0,1500.0,0,0
3,CASH_OUT,4400.0,C12345,4400.0,0.0,C22222,0.0,4400.0,1,0
4,PAYMENT,50.0,C99999,200.0,150.0,M11111,0.0,0.0,0,0
"""


@pytest.fixture
def paysim_csv_path(tmp_path):
    p = tmp_path / "paysim_mini.csv"
    p.write_text(_PAYSIM_CSV)
    return p


@pytest.fixture
def loaded_df(paysim_csv_path):
    return load_paysim_csv(paysim_csv_path)


# ── load_paysim_csv ────────────────────────────────────────────────────────────


def test_load_returns_expected_row_count(loaded_df):
    assert len(loaded_df) == 4


def test_load_column_mapping_account_id(loaded_df):
    assert list(loaded_df["account_id"]) == ["C12345", "C12345", "C12345", "C99999"]


def test_load_column_mapping_counterparty_id(loaded_df):
    assert list(loaded_df["counterparty_id"]) == ["M67890", "C11111", "C22222", "M11111"]


def test_load_column_mapping_balances(loaded_df):
    row0 = loaded_df.iloc[0]
    assert row0["bal_orig_before"] == 5000.0
    assert row0["bal_orig_after"] == 4900.0


def test_load_label_mapping(loaded_df):
    assert int(loaded_df.iloc[2]["label"]) == 1
    assert int(loaded_df.iloc[0]["label"]) == 0


def test_load_sim_flagged_mapping(loaded_df):
    # isFlaggedFraud is 0 for all fixture rows; should be stored, never used as feature
    assert all(int(v) == 0 for v in loaded_df["sim_flagged"])


def test_load_txn_id_format(loaded_df):
    assert list(loaded_df["txn_id"]) == [
        "paysim-0000000",
        "paysim-0000001",
        "paysim-0000002",
        "paysim-0000003",
    ]


def test_load_txn_id_stable_on_reload(paysim_csv_path):
    df1 = load_paysim_csv(paysim_csv_path)
    df2 = load_paysim_csv(paysim_csv_path)
    assert list(df1["txn_id"]) == list(df2["txn_id"])


def test_load_event_ts_from_step(loaded_df):
    expected_ts_step1 = PAYSIM_BASE_EPOCH + timedelta(hours=1)
    assert loaded_df.iloc[0]["event_ts"] == expected_ts_step1


def test_load_event_ts_monotonic_with_step(loaded_df):
    ts_values = list(loaded_df["event_ts"])
    for a, b in zip(ts_values, ts_values[1:3], strict=False):  # rows 0–2 same account
        assert a <= b


def test_load_direction_column(loaded_df):
    assert all(d == "outbound" for d in loaded_df["direction"])


def test_load_merchant_detection_m_prefix(loaded_df):
    # rows 0 and 3 are merchant destinations
    assert bool(loaded_df.iloc[0]["is_merchant_dest"]) is True
    assert bool(loaded_df.iloc[1]["is_merchant_dest"]) is False
    assert bool(loaded_df.iloc[3]["is_merchant_dest"]) is True


def test_load_merchant_dest_balances_nulled(loaded_df):
    # Merchant destinations (rows 0, 3) must have null dest balances (R1 guard)
    def _null(val: object) -> bool:
        return val is None or pd.isna(val)  # type: ignore[arg-type]

    assert _null(loaded_df.iloc[0]["bal_dest_before"])
    assert _null(loaded_df.iloc[0]["bal_dest_after"])
    assert _null(loaded_df.iloc[3]["bal_dest_before"])


def test_load_peer_dest_balances_preserved(loaded_df):
    # Peer destination (row 1) must keep its balance signal
    assert loaded_df.iloc[1]["bal_dest_before"] == 1000.0
    assert loaded_df.iloc[1]["bal_dest_after"] == 1500.0


def test_load_missing_column_raises(tmp_path):
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("step,type,amount\n1,PAYMENT,100\n")
    with pytest.raises(ValueError, match="missing expected columns"):
        load_paysim_csv(bad_csv)


def test_load_preserves_all_required_canonical_columns(loaded_df):
    required = {
        "txn_id",
        "step",
        "event_ts",
        "type",
        "amount",
        "account_id",
        "counterparty_id",
        "direction",
        "bal_orig_before",
        "bal_orig_after",
        "bal_dest_before",
        "bal_dest_after",
        "sim_flagged",
        "label",
        "is_merchant_dest",
    }
    assert required.issubset(set(loaded_df.columns))


# ── ingest_to_db ────────────────────────────────────────────────────────────────


def test_ingest_inserts_accounts(session, loaded_df):
    ingest_to_db(loaded_df, session)
    account_ids = {a.account_id for a in session.query(Account).all()}
    assert "C12345" in account_ids
    assert "C99999" in account_ids


def test_ingest_inserts_counterparties(session, loaded_df):
    ingest_to_db(loaded_df, session)
    cp_ids = {c.counterparty_id for c in session.query(Counterparty).all()}
    assert "M67890" in cp_ids
    assert "C11111" in cp_ids


def test_ingest_merchant_counterparty_flag(session, loaded_df):
    ingest_to_db(loaded_df, session)
    m67890 = session.get(Counterparty, "M67890")
    c11111 = session.get(Counterparty, "C11111")
    assert m67890 is not None and m67890.is_merchant is True
    assert c11111 is not None and c11111.is_merchant is False


def test_ingest_returns_transaction_count(session, loaded_df):
    count = ingest_to_db(loaded_df, session)
    assert count == 4


def test_ingest_all_transactions_persisted(session, loaded_df):
    ingest_to_db(loaded_df, session)
    txns = session.query(Transaction).all()
    assert len(txns) == 4


def test_ingest_idempotent_on_reingest(session, loaded_df):
    count1 = ingest_to_db(loaded_df, session)
    count2 = ingest_to_db(loaded_df, session)
    assert count1 == 4
    assert count2 == 0  # second call inserts nothing new


def test_ingest_sim_flagged_stored(session, loaded_df):
    ingest_to_db(loaded_df, session)
    txn = session.get(Transaction, "paysim-0000000")
    assert txn is not None
    assert txn.sim_flagged is False


def test_ingest_label_stored(session, loaded_df):
    ingest_to_db(loaded_df, session)
    fraud_txn = session.get(Transaction, "paysim-0000002")
    assert fraud_txn is not None
    assert fraud_txn.label is True


def test_ingest_merchant_dest_null_balances_stored(session, loaded_df):
    ingest_to_db(loaded_df, session)
    txn = session.get(Transaction, "paysim-0000000")
    assert txn is not None
    assert txn.bal_dest_before is None
    assert txn.bal_dest_after is None
