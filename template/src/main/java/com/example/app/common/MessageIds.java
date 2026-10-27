package com.example.app.common;

/**
 * メッセージ ID の一覧（本文は messages.properties）.
 *
 * <p>形式: APP + 種別（I=情報 / W=警告 / E=エラー）+ 4 桁。実案件では社内のメッセージ体系に置き換える。
 */
public final class MessageIds {

    public static final String INVALID_INPUT = "APPE0001";
    public static final String MEMBER_NOT_FOUND = "APPE0002";
    public static final String EMAIL_ALREADY_USED = "APPE0003";
    /** API: 入力チェック以外の理由で受け付けられない（型違い・JSON の誤り・未対応のメソッドなど）. */
    public static final String REQUEST_REJECTED = "APPE0004";
    /** バッチ: 起動引数の誤り. */
    public static final String BATCH_INVALID_ARGS = "APPE0005";
    /** バッチ: ジョブ ID の誤り・未指定. */
    public static final String BATCH_UNKNOWN_JOB = "APPE0006";
    /** バッチ: 異常終了. */
    public static final String BATCH_FAILED = "APPE0007";
    /** API: DB など依存先に一時的につながらない（503）. */
    public static final String SERVICE_UNAVAILABLE = "APPE0008";
    /** 想定外のエラー（詳細はログにだけ出す）. */
    public static final String SYSTEM_ERROR = "APPE9999";
    public static final String IMPORT_STARTED = "APPI0001";
    public static final String IMPORT_FINISHED = "APPI0002";
    public static final String IMPORT_LINE_SKIPPED = "APPW0001";
    /** バッチ: 登録済みの注文番号で内容が違う行を飛ばした（終了コード 6）. */
    public static final String IMPORT_CONFLICT = "APPW0002";

    private MessageIds() {}
}
