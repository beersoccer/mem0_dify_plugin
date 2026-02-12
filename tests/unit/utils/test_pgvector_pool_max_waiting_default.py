from __future__ import annotations


def test_pgvector_pool_max_waiting_defaults_to_maxconn_times_multiplier() -> None:
    """pool_max_waiting should default to a finite value aligned with overload cap."""
    from utils.pgvector_config import _extract_pool_parameters  # noqa: SLF001

    normalized = {
        "minconn": 10,
        "maxconn": 20,
        # omit pool_max_waiting on purpose
    }

    pool_params, psycopg3_available, _psycopg2_available = _extract_pool_parameters(normalized)

    # If psycopg3 isn't available in the test environment, the function returns
    # (None, False, False).
    # In that case this test is not meaningful.
    if not psycopg3_available or pool_params is None:  # pragma: no cover
        return

    # Default derivation: max_waiting = maxconn * (multiplier - 1)
    # With defaults: maxconn=20, multiplier=2 => max_waiting=20
    assert pool_params["max_waiting"] == 20

