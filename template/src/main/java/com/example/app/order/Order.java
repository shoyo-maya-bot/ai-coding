package com.example.app.order;

/**
 * 注文（取込ファイルの 1 行）.
 *
 * @param orderNo 注文番号（一意。重複は取り込まない）
 * @param memberId 会員 ID
 * @param productCode 商品コード
 * @param quantity 数量（1 以上）
 */
public record Order(String orderNo, long memberId, String productCode, int quantity) {}
