import datetime as dt
import decimal

from eval.compare import compare


def test_scalar_exact_and_float_noise():
    assert compare([[120098.26999999952]], [[120098.27000000001]]) == (True, "exact")
    assert compare([[800]], [[800.0]]) == (True, "exact")
    assert compare([[800]], [[801]]) == (False, "none")


def test_rates_three_decimals():
    assert compare([[0.0381]], [[0.0383]])[0]
    assert not compare([[0.038]], [[0.040]])[0]
    assert not compare([[0.038]], [[3.8]])[0]  # percent vs fraction is wrong


def test_row_order_ignored_unless_order_matters():
    gold = [["North", 0.1], ["South", 0.2]]
    pred = [["South", 0.2], ["North", 0.1]]
    assert compare(gold, pred) == (True, "exact")
    assert compare(gold, pred, order_matters=True) == (False, "none")


def test_column_names_and_order_ignored():
    gold = [["2017-01", 10.0], ["2017-02", 20.0]]
    pred = [[10.0, "2017-01"], [20.0, "2017-02"]]
    assert compare(gold, pred) == (True, "exact")


def test_extra_columns_partial():
    gold = [["bed_bath_table"], ["health_beauty"]]
    pred = [["health_beauty", 1500.0], ["bed_bath_table", 1800.0]]
    assert compare(gold, pred) == (True, "partial")


def test_missing_column_or_rows_fails():
    assert compare([["a", 1]], [["a"]]) == (False, "none")
    assert compare([["a"], ["b"]], [["a"]]) == (False, "none")
    assert compare([["a"]], []) == (False, "none")


def test_null_and_types():
    assert compare([[None, 1]], [[None, 1]])[0]
    assert not compare([[None]], [[0]])[0]
    assert compare([["2018-01-01"]], [[dt.date(2018, 1, 1)]])[0]
    assert compare([["2018-01-01"]], [[dt.datetime(2018, 1, 1)]])[0]
    assert compare([[3.5]], [[decimal.Decimal("3.50")]])[0]
    assert compare([["SP"]], [["sp "]])[0]
    assert not compare([["1"]], [[1]])[0]


def test_duplicate_rows_need_distinct_matches():
    assert not compare([["a"], ["a"]], [["a"], ["b"]])[0]
