package com.example.app.common;

/** 対象データが存在しない. */
public class NotFoundException extends BusinessException {

    public NotFoundException(String messageId, Object... args) {
        super(messageId, args);
    }
}
