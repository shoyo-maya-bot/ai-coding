package com.example.app.order.batch;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

/** s3://bucket/key は S3（ローカルではエミュレータ）から、それ以外はローカルファイルから読む. */
@Component
public class DefaultFileFetcher implements FileFetcher {

    private final S3Client s3;

    public DefaultFileFetcher(S3Client s3) {
        this.s3 = s3;
    }

    @Override
    public List<String> readLines(String location) throws IOException {
        if (!location.startsWith("s3://")) {
            return Files.readAllLines(Path.of(location), StandardCharsets.UTF_8);
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
        try (ResponseInputStream<GetObjectResponse> in = s3.getObject(req);
                BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            return reader.lines().toList();
        }
    }
}
