from summarize import summarize


def test_small_sample(tmp_path):
    path = tmp_path / "sample.log"
    path.write_text(
        '2026-01-01T00:00:00Z ERROR request_id=1 code=E_X msg="boom"\n'
        '2026-01-01T00:00:01Z INFO  request_id=2 msg="fine"\n'
    )
    assert summarize(path) == {"total_errors": 1, "by_code": {"E_X": 1}}
