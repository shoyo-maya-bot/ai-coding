package com.example.app.common;

import java.util.List;

/**
 * API のエラー応答.
 *
 * @param messageId メッセージ ID（例: APPE0001）
 * @param message 利用者向けメッセージ
 * @param details 入力チェックの項目別エラー（無ければ空）
 */
public record ErrorResponse(String messageId, String message, List<String> details) {

    public ErrorResponse {
        details = List.copyOf(details);
    }
}
