package com.example.app.common;

import java.util.List;
import java.util.Locale;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.MessageSource;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

/**
 * 例外を API のエラー応答（ステータス + メッセージ ID）に変換する.
 *
 * <p>どの失敗でも {@link ErrorResponse} の形で返す（利用側が 1 つの形だけを扱えばよいように）。
 * 想定外のエラーは 500 と APPE9999 だけを返し、例外の中身はログにだけ出す。
 */
@RestControllerAdvice
public class ApiExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(ApiExceptionHandler.class);

    private final MessageSource messages;

    public ApiExceptionHandler(MessageSource messages) {
        this.messages = messages;
    }

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<ErrorResponse> notFound(NotFoundException e) {
        return body(HttpStatus.NOT_FOUND, e.getMessageId(), e.getArgs(), List.of());
    }

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> business(BusinessException e) {
        log.warn("business error: {}", e.getMessageId());
        return body(HttpStatus.CONFLICT, e.getMessageId(), e.getArgs(), List.of());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> invalid(MethodArgumentNotValidException e) {
        List<String> details = e.getBindingResult().getFieldErrors().stream()
                .map(f -> f.getField() + ": " + f.getDefaultMessage())
                .sorted()
                .toList();
        return body(HttpStatus.BAD_REQUEST, MessageIds.INVALID_INPUT, new Object[0], details);
    }

    /** パスやクエリの型違い（例: /members/abc）. */
    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ErrorResponse> typeMismatch(MethodArgumentTypeMismatchException e) {
        return body(HttpStatus.BAD_REQUEST, MessageIds.INVALID_INPUT, new Object[0],
                List.of(e.getName() + ": 形式が正しくありません"));
    }

    /** 本文が JSON として読めない・型が合わない. */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> unreadable(HttpMessageNotReadableException e) {
        return body(HttpStatus.BAD_REQUEST, MessageIds.INVALID_INPUT, new Object[0],
                List.of("body: JSON の形式が正しくありません"));
    }

    /**
     * それ以外のすべて.
     *
     * <p>Spring MVC の標準の例外（未対応のメソッド・存在しないパスなど、{@code org.springframework.web.ErrorResponse} を実装するもの）は
     * そのステータスを使う。DB 障害などの想定外のエラーは 500。
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> unexpected(Exception e) {
        if (e instanceof org.springframework.web.ErrorResponse framework
                && framework.getStatusCode().is4xxClientError()) {
            return body(framework.getStatusCode(), MessageIds.REQUEST_REJECTED, new Object[0], List.of());
        }
        log.error("{} 想定外のエラー", MessageIds.SYSTEM_ERROR, e);
        return body(HttpStatus.INTERNAL_SERVER_ERROR, MessageIds.SYSTEM_ERROR, new Object[0], List.of());
    }

    private ResponseEntity<ErrorResponse> body(HttpStatusCode status, String id, Object[] args, List<String> details) {
        String text = messages.getMessage(id, args, id, Locale.JAPANESE);
        return ResponseEntity.status(status).body(new ErrorResponse(id, text, details));
    }
}
