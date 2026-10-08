package com.example.app.order.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.net.URI;
import org.junit.jupiter.api.Test;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetUrlRequest;

/** S3Config の単体テスト（クライアントを作るだけで、S3 にはつながない）. */
class S3ConfigTest {

    private static String url(S3Client s3) {
        GetUrlRequest req = GetUrlRequest.builder().bucket("sample-bucket").key("orders.csv").build();
        return s3.utilities().getUrl(req).toString();
    }

    @Test
    void endpointSetMeansEmulatorWithPathStyleAndStaticKeys() {
        try (S3Client s3 = new S3Config().s3Client("ap-northeast-1", "http://localhost:9090", "test", "secret")) {
            var conf = s3.serviceClientConfiguration();
            assertThat(conf.region()).isEqualTo(Region.AP_NORTHEAST_1);
            assertThat(conf.endpointOverride()).contains(URI.create("http://localhost:9090"));
            // バケット名がパスに入る形式（エミュレータ向け. upload-sample の URL と同じ）
            assertThat(url(s3)).isEqualTo("http://localhost:9090/sample-bucket/orders.csv");
            assertThat(conf.credentialsProvider()).isInstanceOf(StaticCredentialsProvider.class);
            var keys = conf.credentialsProvider().resolveIdentity().join();
            assertThat(keys.accessKeyId()).isEqualTo("test");
            assertThat(keys.secretAccessKey()).isEqualTo("secret");
        }
    }

    @Test
    void blankEndpointMeansRealS3WithDefaultCredentials() {
        try (S3Client s3 = new S3Config().s3Client("ap-northeast-1", " ", "test", "test")) {
            var conf = s3.serviceClientConfiguration();
            assertThat(conf.endpointOverride()).isEmpty();
            // 固定の鍵（test / test）を使わず、実行環境のロールなど標準の場所から探す
            assertThat(conf.credentialsProvider()).isInstanceOf(DefaultCredentialsProvider.class);
            assertThat(url(s3)).startsWith("https://sample-bucket.s3.ap-northeast-1.amazonaws.com/");
        }
    }

    @Test
    void regionIsConfigurable() {
        try (S3Client s3 = new S3Config().s3Client("us-west-2", "", "test", "test")) {
            assertThat(s3.serviceClientConfiguration().region()).isEqualTo(Region.US_WEST_2);
        }
    }
}
