from wordfreq import main


def test_top_option(capsys):
    main(["data/sample.txt", "--top", "2"])
    assert capsys.readouterr().out.strip().splitlines() == ["hat\t4", "the\t4"]
