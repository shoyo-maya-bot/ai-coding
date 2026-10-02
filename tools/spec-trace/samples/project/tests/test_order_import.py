from order_import import OrderValidator, import_orders


class TestOrderValidator:
    def test_required(self):
        assert OrderValidator().validate({"order_no": "", "quantity": "0"}) == ["order_no は必須", "quantity は 1 以上"]


def test_import_is_idempotent():
    table = {}
    rows = [{"order_no": "A1", "quantity": "1"}]
    assert import_orders(rows, table) == 1
    assert import_orders(rows, table) == 0
