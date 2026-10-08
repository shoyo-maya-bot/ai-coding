package com.example.app.order.batch;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.StringReader;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/**
 * s3://bucket/key は S3（ローカルではエミュレータ）から、それ以外はローカルファイルから読む.
 *
 * <p>ファイル全体をメモリに読むので、大きさに上限を設ける（{@code app.batch.max-input-bytes}。既定 64 MiB）。
 * 上限を超えたら読まずに {@link IOException} にする（JOB0001 は終了コード 8）。
 *
 * <p>文字コードは UTF-8。ローカルでも S3 でも、UTF-8 として正しくないバイト列があれば置き換えずに
 * {@link CharacterCodingException}（{@link IOException} の一種）にする（JOB0001 は終了コード 8）。
 */
@Component
public final class DefaultFileFetcher implements FileFetcher {

    /** 入力ファイルの大きさの上限の既定（64 MiB）. */
    public static final long DEFAULT_MAX_BYTES = 64L * 1024 * 1024;

    /** 上限に設定できる最大値（配列 1 つに読める大きさ）. */
    static final long MAX_CONFIGURABLE_BYTES = Integer.MAX_VALUE - 8;

    private final S3Client s3;
    private final long maxBytes;

    public DefaultFileFetcher(
            S3Client s3, @Value("${app.batch.max-input-bytes:" + DEFAULT_MAX_BYTES + "}") long maxBytes) {
        if (maxBytes < 1 || maxBytes > MAX_CONFIGURABLE_BYTES) {
            throw new IllegalArgumentException(
                    "app.batch.max-input-bytes は 1〜" + MAX_CONFIGURABLE_BYTES + " で指定してください: " + maxBytes);
        }
        this.s3 = s3;
        this.maxBytes = maxBytes;
    }

    @Override
    public List<String> readLines(String location) throws IOException {
        if (!location.startsWith("s3://")) {
            Path path = Path.of(location);
            checkSize(Files.size(path), location);
            return Files.readAllLines(path, StandardCharsets.UTF_8);
        }
        String rest = location.substring("s3://".length());
        int slash = rest.indexOf('/');
        if (slash <= 0 || slash == rest.length() - 1) {
            throw new IllegalArgumentException("s3://バケット/キー の形式で指定してください: " + location);
        }
        GetObjectRequest req = GetObjectRequest.builder()
                .bucket(rest.substring(0, slash))
                .key(rest.substring(slash + 1))
                .build();
        try (ResponseInputStream<GetObjectResponse> in = s3.getObject(req)) {
            Long length = in.response().contentLength();
            if (length != null && length > maxBytes) {
                in.abort(); // 残りを受け取らずに接続を閉じる
                checkSize(length, location);
            }
            // 大きさが分からない・実際と違う場合に備え、上限 + 1 バイトまでしか読まない
            byte[] bytes = in.readNBytes((int) maxBytes + 1);
            if (bytes.length > maxBytes) {
                in.abort();
                checkSize(bytes.length, location);
            }
            try (BufferedReader reader = new BufferedReader(new StringReader(decodeUtf8(bytes, location)))) {
                return reader.lines().toList();
            }
        }
    }

    /**
     * UTF-8 として厳密に読む（new String(bytes, UTF_8) と違い、不正なバイト列を U+FFFD に置き換えない）.
     * ローカルの {@link Files#readAllLines(Path, java.nio.charset.Charset)} と同じく
     * {@link java.nio.charset.MalformedInputException} 等にする.
     */
    static String decodeUtf8(byte[] bytes, String location) throws CharacterCodingException {
        try {
            return StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(bytes))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new InvalidUtf8Exception(location, e);
        }
    }

    /** 入力が UTF-8 として正しくない（場所をメッセージに入れる）. */
    static final class InvalidUtf8Exception extends CharacterCodingException {
        private static final long serialVersionUID = 1L;
        private final String message;

        InvalidUtf8Exception(String location, CharacterCodingException cause) {
            this.message = "入力ファイルが UTF-8 として正しくありません（" + cause + "）: " + location;
            initCause(cause);
        }

        @Override
        public String getMessage() {
            return message;
        }
    }

    private void checkSize(long size, String location) throws IOException {
        if (size > maxBytes) {
            throw new IOException("入力ファイルが上限 " + maxBytes + " バイトを超えています（" + size + " バイト以上）: " + location
                    + "。上限は app.batch.max-input-bytes で変えられます");
        }
    }
}
