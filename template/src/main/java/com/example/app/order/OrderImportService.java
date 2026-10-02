package com.example.app.order;

import java.util.ArrayList;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 注文ファイル取込（JOB0001）の業務ロジック.
 *
 * <p>入力: CSV（1 行目は見出し {@code order_no,member_id,product_code,quantity}）。
 * 形式エラーの行は飛ばして続行し、結果に行番号と理由を残す。登録済みの注文番号は飛ばす（冪等）。
 */
@Service
public class OrderImportService {

    static final String HEADER = "order_no,member_id,product_code,quantity";

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
        String orderNo = cols[0].trim();
        if (orderNo.isEmpty()) {
            throw new IllegalArgumentException("order_no が空です");
        }
        long memberId = parseLong(cols[1], "member_id");
        String product = cols[2].trim();
        if (product.isEmpty()) {
            throw new IllegalArgumentException("product_code が空です");
        }
        long quantity = parseLong(cols[3], "quantity");
        if (quantity < 1 || quantity > 999) {
            throw new IllegalArgumentException("quantity は 1〜999 です（" + quantity + "）");
        }
        return new Order(orderNo, memberId, product, (int) quantity);
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
