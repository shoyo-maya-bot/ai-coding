package com.example.app.order;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.app.order.batch.DefaultFileFetcher;
import com.example.app.order.batch.OrderImportJob;
import java.io.IOException;
import java.io.ByteArrayInputStream;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import software.amazon.awssdk.core.ResponseInputStream;
import software.amazon.awssdk.http.AbortableInputStream;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectResponse;

class OrderImportJobTest {

    private final OrderImportService service = new OrderImportService(new FakeOrderMapper());

    @Test
    void exitCodeZeroWhenAllLinesValid() {
        OrderImportJob job = new OrderImportJob(loc -> List.of(OrderImportService.HEADER, "A1,1,P,1"), service);
        job.run(new DefaultApplicationArguments("--input=orders.csv"));
        assertThat(job.getExitCode()).isZero();
    }

    @Test
    void exitCodeFourWhenSomeLinesSkipped() {
        OrderImportJob job = new OrderImportJob(loc -> List.of(OrderImportService.HEADER, "bad"), service);
        job.run(new DefaultApplicationArguments("--input=orders.csv"));
        assertThat(job.getExitCode()).isEqualTo(4);
    }

    @Test
    void exitCodeSixWhenSameOrderNoHasDifferentContent() {
        // 後退: 内容の違う重複を duplicated として黙って捨て、終了コード 0 で終わっていた
        FakeOrderMapper mapper = new FakeOrderMapper();
        OrderImportService svc = new OrderImportService(mapper);
        svc.importLines(List.of(OrderImportService.HEADER, "A1,1,P,1"));

        OrderImportJob job = new OrderImportJob(loc -> List.of(OrderImportService.HEADER, "A1,1,P,2"), svc);
        job.run(new DefaultApplicationArguments("--input=orders.csv"));
        assertThat(job.getExitCode()).isEqualTo(OrderImportJob.CONFLICT).isEqualTo(6);

        // 形式エラーもあるときは、内容の違う重複（6）を優先する
        OrderImportJob both = new OrderImportJob(loc -> List.of(OrderImportService.HEADER, "A1,1,P,3", "bad"), svc);
        both.run(new DefaultApplicationArguments("--input=orders.csv"));
        assertThat(both.getExitCode()).isEqualTo(6);

        // 同じ内容の重複（再実行）は 0 のまま
        OrderImportJob rerun = new OrderImportJob(loc -> List.of(OrderImportService.HEADER, "A1,1,P,1"), svc);
        rerun.run(new DefaultApplicationArguments("--input=orders.csv"));
        assertThat(rerun.getExitCode()).isZero();
    }

    @Test
    void exitCodeEightWhenInputMissingOrUnreadable() {
        OrderImportJob noArg = new OrderImportJob(loc -> List.of(), service);
        noArg.run(new DefaultApplicationArguments());
        assertThat(noArg.getExitCode()).isEqualTo(8);

        OrderImportJob broken = new OrderImportJob(loc -> {
            throw new IOException("not found");
        }, service);
        broken.run(new DefaultApplicationArguments("--input=s3://b/k"));
        assertThat(broken.getExitCode()).isEqualTo(8);
    }

    @Test
    void exitCodeEightWhenS3ObjectIsNotValidUtf8() {
        byte[] body = {'o', 'r', 'd', 'e', 'r', '\n', 'A', (byte) 0xFF, ',', '1', '\n'};
        S3Client s3 = new S3Client() {
            @Override
            public ResponseInputStream<GetObjectResponse> getObject(GetObjectRequest request) {
                return new ResponseInputStream<>(GetObjectResponse.builder().build(),
                        AbortableInputStream.create(new ByteArrayInputStream(body)));
            }

            @Override
            public String serviceName() {
                return "s3";
            }

            @Override
            public void close() {}
        };
        FakeOrderMapper mapper = new FakeOrderMapper();
        OrderImportJob job = new OrderImportJob(new DefaultFileFetcher(s3, 1024), new OrderImportService(mapper));
        job.run(new DefaultApplicationArguments("--input=s3://b/orders.csv"));
        assertThat(job.getExitCode()).isEqualTo(8);
        assertThat(mapper.stored).isEmpty(); // 化けた行を取り込まない
    }
}
