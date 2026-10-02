package com.example.app.common;

/** 業務エラー. メッセージ ID（messages.properties のキー）と埋め込み値を持つ. */
public class BusinessException extends RuntimeException {

    private final String messageId;
    private final transient Object[] args;

    public BusinessException(String messageId, Object... args) {
        super(messageId);
        this.messageId = messageId;
        this.args = args.clone();
    }

    public String getMessageId() {
        return messageId;
    }

    public Object[] getArgs() {
        return args.clone();
    }
}
