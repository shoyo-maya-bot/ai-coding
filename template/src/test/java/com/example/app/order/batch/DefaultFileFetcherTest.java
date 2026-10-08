package com.example.app.order.batch;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/** DefaultFileFetcher の単体テスト（S3 にはつながない. S3Client は getObject だけを持つ偽物）. */
class DefaultFileFetcherTest {

    /** getObject の要求を記録し、決まった中身を返す S3Client. */
    static final class FakeS3 implements S3Client {
        final List<GetObjectRequest> requests = new ArrayList<>();
        byte[] body = "order_no,member_id,product_code,quantity\nA1,1,P,1\n".getBytes(StandardCharsets.UTF_8);
        Long contentLength; // null なら応答に大きさを書かない
        boolean aborted;

        @Override
        public ResponseInputStream<GetObjectResponse> getObject(GetObjectRequest request) {
            requests.add(request);
            GetObjectResponse response = GetObjectResponse.builder().contentLength(contentLength).build();
            AbortableInputStream in = AbortableInputStream.create(new ByteArrayInputStream(body), () -> aborted = true);
            return new ResponseInputStream<>(response, in);
        }

        @Override
        public String serviceName() {
            return "s3";
        }

        @Override
        public void close() {}
    }

    private final FakeS3 s3 = new FakeS3();

    @Test
    void readsS3ObjectAndSplitsBucketAndKey() throws IOException {
        List<String> lines = new DefaultFileFetcher(s3, 1024).readLines("s3://sample-bucket/inbound/2026/orders.csv");
        assertThat(lines).containsExactly("order_no,member_id,product_code,quantity", "A1,1,P,1");
        assertThat(s3.requests).hasSize(1);
        assertThat(s3.requests.get(0).bucket()).isEqualTo("sample-bucket");
        assertThat(s3.requests.get(0).key()).isEqualTo("inbound/2026/orders.csv");
    }

    @ParameterizedTest
    @ValueSource(strings = {"s3://", "s3://bucket", "s3://bucket/", "s3:///key", "s3:///"})
    void rejectsMalformedS3LocationWithoutCallingS3(String location) {
        assertThatThrownBy(() -> new DefaultFileFetcher(s3, 1024).readLines(location))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("s3://バケット/キー");
        assertThat(s3.requests).isEmpty();
    }

    @Test
    void readsLocalFileWhenNotS3(@TempDir Path dir) throws IOException {
        Path file = dir.resolve("orders.csv");
        Files.writeString(file, "h\nx\n", StandardCharsets.UTF_8);
        assertThat(new DefaultFileFetcher(s3, 1024).readLines(file.toString())).containsExactly("h", "x");
        assertThat(s3.requests).isEmpty();
    }

    @Test
    void rejectsLocalFileOverLimit(@TempDir Path dir) throws IOException {
        Path file = dir.resolve("big.csv");
        Files.write(file, new byte[11]);
        assertThatThrownBy(() -> new DefaultFileFetcher(s3, 10).readLines(file.toString()))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("上限 10 バイト")
                .hasMessageContaining("app.batch.max-input-bytes");
    }

    @Test
    void acceptsFileExactlyAtLimit() throws IOException {
        s3.body = "abc\n".getBytes(StandardCharsets.UTF_8);
        s3.contentLength = 4L;
        assertThat(new DefaultFileFetcher(s3, 4).readLines("s3://b/k")).containsExactly("abc");
        assertThat(s3.aborted).isFalse();
    }

    @Test
    void rejectsS3ObjectWhoseContentLengthIsOverLimit() {
        s3.contentLength = 1_000_000_000L; // 応答の大きさだけで判断し、中身は読まない
        assertThatThrownBy(() -> new DefaultFileFetcher(s3, 1024).readLines("s3://b/k"))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("上限 1024 バイト");
        assertThat(s3.aborted).isTrue();
    }

    @Test
    void rejectsS3ObjectOverLimitEvenWithoutContentLength() {
        s3.body = new byte[2048];
        s3.contentLength = null;
        assertThatThrownBy(() -> new DefaultFileFetcher(s3, 1024).readLines("s3://b/k"))
                .isInstanceOf(IOException.class)
                .hasMessageContaining("上限 1024 バイト");
        assertThat(s3.aborted).isTrue();
    }

    @Test
    void rejectsInvalidLimit() {
        assertThatThrownBy(() -> new DefaultFileFetcher(s3, 0)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new DefaultFileFetcher(s3, Long.MAX_VALUE))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(DefaultFileFetcher.DEFAULT_MAX_BYTES).isEqualTo(64L * 1024 * 1024);
    }
}
