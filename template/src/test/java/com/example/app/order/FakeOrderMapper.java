package com.example.app.order;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/** DB を使わない差し替え用の Mapper. 会員は ID 1〜9 だけが存在するものとする. */
public class FakeOrderMapper implements OrderMapper {

    /** 登録済みの注文（注文番号 → 注文）. */
    public final Map<String, Order> orders = new HashMap<>();
    /** 登録済みの注文番号. */
    public final Set<String> stored = orders.keySet();
    public int memberLookups = 0;

    @Override
    public int insertIfAbsent(Order order) {
        return orders.putIfAbsent(order.orderNo(), order) == null ? 1 : 0;
    }

    @Override
    public boolean existsSame(Order order) {
        return order.equals(orders.get(order.orderNo()));
    }

    @Override
    public boolean memberExists(long memberId) {
        memberLookups++;
        return memberId >= 1 && memberId <= 9;
    }
}
