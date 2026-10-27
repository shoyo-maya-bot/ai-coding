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
 * 登録済みの注文番号でも、内容（会員・商品・数量）が違う行は「内容の違う重複」（conflict）として別に数え、行番号と理由を残す
 * （黙って捨てると、訂正や番号の付け間違いに気づけないため）。
 *
 * <p>CSV の値は {@code "} で囲んでもよい（RFC 4180 の形。値の中の {@code ,} と、{@code ""} と書いた {@code "}）。
 * 値の中の改行には対応しない（1 行ずつ読むため）。引用符が閉じていない行は形式エラーとして飛ばす。
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
        List<String> conflicts = new ArrayList<>();
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
            } else if (mapper.existsSame(order)) {
                duplicated++;
            } else {
                conflicts.add(lineNo + ": order_no " + order.orderNo()
                        + " は登録済みで、内容（member_id・product_code・quantity）が違います");
            }
        }
        return new ImportResult(imported, duplicated, List.copyOf(errors), List.copyOf(conflicts));
    }

    static Order parse(String line) {
        List<String> cols = splitCsv(line);
        if (cols.size() != 4) {
            throw new IllegalArgumentException("列数が 4 ではありません（" + cols.size() + " 列）");
        }
        String orderNo = code(cols.get(0), "order_no");
        long memberId = parseLong(cols.get(1), "member_id");
        String product = code(cols.get(2), "product_code");
        long quantity = parseLong(cols.get(3), "quantity");
        if (quantity < 1 || quantity > 999) {
            throw new IllegalArgumentException("quantity は 1〜999 です（" + quantity + "）");
        }
        return new Order(orderNo, memberId, product, (int) quantity);
    }

    /**
     * CSV の 1 行を値に分ける（RFC 4180 の引用符に対応. 値の中の改行は扱わない）.
     *
     * <p>{@code "a,b"} は 1 つの値 {@code a,b}、{@code "a""b"} は {@code a"b}。引用符の外の前後の空白はそのまま返す（呼び出し側で trim する）。
     *
     * @throws IllegalArgumentException 引用符が閉じていない・閉じた引用符の後ろに区切り以外の文字がある
     */
    static List<String> splitCsv(String line) {
        List<String> values = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        int i = 0;
        int n = line.length();
        while (true) {
            // 引用符の前の空白は飛ばしてよい（" A001" のような書き方）
            int q = skipSpaces(line, i);
            if (q < n && line.charAt(q) == '"') {
                i = readQuoted(line, q + 1, cur);
            } else {
                i = readUnquoted(line, i, cur);
            }
            values.add(cur.toString());
            cur.setLength(0);
            if (i >= n) {
                return values;
            }
            i++; // 区切りの ,
        }
    }

    private static int skipSpaces(String line, int from) {
        int i = from;
        while (i < line.length() && line.charAt(i) == ' ') {
            i++;
        }
        return i;
    }

    /** 開いた引用符の次から読み、値を cur に足して、区切り（,）か行末の位置を返す（閉じた引用符の後ろの空白は飛ばす）. */
    private static int readQuoted(String line, int from, StringBuilder cur) {
        int n = line.length();
        int i = from;
        boolean closed = false;
        while (i < n) {
            char c = line.charAt(i++);
            if (c != '"') {
                cur.append(c);
            } else if (i < n && line.charAt(i) == '"') {
                cur.append('"');
                i++;
            } else {
                closed = true;
                break;
            }
        }
        if (!closed) {
            throw new IllegalArgumentException(
                    "引用符（\"）が閉じていません（値の中の改行には対応していません）");
        }
        i = skipSpaces(line, i);
        if (i < n && line.charAt(i) != ',') {
            throw new IllegalArgumentException("閉じた引用符（\"）の後ろに区切り（,）以外の文字があります");
        }
        return i;
    }

    /** 引用符で囲まない値を読み、cur に足して、区切り（,）か行末の位置を返す. */
    private static int readUnquoted(String line, int from, StringBuilder cur) {
        int n = line.length();
        int i = from;
        while (i < n && line.charAt(i) != ',') {
            char c = line.charAt(i++);
            if (c == '"') {
                throw new IllegalArgumentException("引用符（\"）は値の全体を囲むときだけ使えます");
            }
            cur.append(c);
        }
        return i;
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
