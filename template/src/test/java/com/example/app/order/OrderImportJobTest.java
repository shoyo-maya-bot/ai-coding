package com.example.app.order;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.app.order.batch.OrderImportJob;
import java.io.IOException;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

class OrderImportJobTest {

    private final OrderImportService service = new OrderImportService(o -> 1);

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
}
