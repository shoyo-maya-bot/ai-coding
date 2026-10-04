package com.example.app.order;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 注文ファイル取込（JOB0001）の業務ロジック.
 *
 * <p>入力: CSV（1 行目は見出し {@code order_no,member_id,product_code,quantity}）。
 * 形式エラーの行・存在しない会員の行は飛ばして続行し、結果に行番号と理由を残す。登録済みの注文番号は飛ばす（冪等）。
 *
 * <p>DB の制約（桁数・外部キー）に当たる誤りは、登録の前にここで確かめる。DB の例外に任せると、
 * 1 行の誤りでトランザクション全体が取り消されてしまうため。
 */
@Service
public class OrderImportService {

    static final String HEADER = "order_no,member_id,product_code,quantity";

    /** orders.order_no・orders.product_code の桁数（local/db/init/01_schema.sql の VARCHAR(20)）. */
    static final int CODE_MAX_LENGTH = 20;

    private final OrderMapper mapper;

    public OrderImportService(OrderMapper mapper) {
        this.mapper = mapper;
    }

    @Transactional
    public ImportResult importLines(List<String> lines) {
        if (lines.isEmpty() || !HEADER.equals(stripBom(lines.get(0)).trim())) {
            throw new IllegalArgumentException("見出し行が不正です（期待値: " + HEADER + "）");
        }
        int imported = 0;
        int duplicated = 0;
        List<String> errors = new ArrayList<>();
        Map<Long, Boolean> memberCache = new HashMap<>();
        for (int i = 1; i < lines.size(); i++) {
            String line = lines.get(i);
            if (line.isBlank()) {
                continue;
            }
            int lineNo = i + 1;
            Order order;
            try {
                order = parse(line);
            } catch (IllegalArgumentException e) {
                errors.add(lineNo + ": " + e.getMessage());
                continue;
            }
            if (!memberCache.computeIfAbsent(order.memberId(), mapper::memberExists)) {
                errors.add(lineNo + ": member_id の会員が存在しません（" + order.memberId() + "）");
                continue;
            }
            if (mapper.insertIfAbsent(order) == 1) {
                imported++;
            } else {
                duplicated++;
            }
        }
        return new ImportResult(imported, duplicated, List.copyOf(errors));
    }

    static Order parse(String line) {
        String[] cols = line.split(",", -1);
        if (cols.length != 4) {
            throw new IllegalArgumentException("列数が 4 ではありません（" + cols.length + " 列）");
        }
        String orderNo = code(cols[0], "order_no");
        long memberId = parseLong(cols[1], "member_id");
        String product = code(cols[2], "product_code");
        long quantity = parseLong(cols[3], "quantity");
        if (quantity < 1 || quantity > 999) {
            throw new IllegalArgumentException("quantity は 1〜999 です（" + quantity + "）");
        }
        return new Order(orderNo, memberId, product, (int) quantity);
    }

    private static String code(String value, String name) {
        String v = value.trim();
        if (v.isEmpty()) {
            throw new IllegalArgumentException(name + " が空です");
        }
        if (v.length() > CODE_MAX_LENGTH) {
            throw new IllegalArgumentException(
                    name + " は " + CODE_MAX_LENGTH + " 文字以内です（" + v.length() + " 文字）");
        }
        return v;
    }

    private static long parseLong(String value, String name) {
        try {
            return Long.parseLong(value.trim());
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException(name + " が数値ではありません", e);
        }
    }

    private static String stripBom(String s) {
        return s.startsWith("﻿") ? s.substring(1) : s;
    }
}
