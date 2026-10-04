package com.example.app.order;

import java.util.HashSet;
import java.util.Set;

/** DB を使わない差し替え用の Mapper. 会員は ID 1〜9 だけが存在するものとする. */
public class FakeOrderMapper implements OrderMapper {

    public final Set<String> stored = new HashSet<>();
    public int memberLookups = 0;

    @Override
    public int insertIfAbsent(Order order) {
        return stored.add(order.orderNo()) ? 1 : 0;
    }

    @Override
    public boolean memberExists(long memberId) {
        memberLookups++;
        return memberId >= 1 && memberId <= 9;
    }
}
