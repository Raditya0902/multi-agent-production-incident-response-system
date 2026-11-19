from app.data_processing import BatchProcessor


def test_empty_batch_returns_no_item():
    assert BatchProcessor().process_batch([], 0) is None
