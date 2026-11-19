from app.data_processing import BatchProcessor


def test_outside_both_bounds_and_valid_negative_index():
    processor = BatchProcessor()
    assert processor.process_batch(["first", "last"], -3) is None
    assert processor.process_batch(["first", "last"], 2) is None
    assert processor.process_batch(["first", "last"], -1) == "last"
