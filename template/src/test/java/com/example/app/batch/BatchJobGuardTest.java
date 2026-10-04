package com.example.app.batch;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;

class BatchJobGuardTest {

    private final BatchJob job0001 = () -> "JOB0001";

    @Test
    void okWhenRequestedJobExists() {
        BatchJobGuard guard = new BatchJobGuard("JOB0001", List.of(job0001));
        guard.run(new DefaultApplicationArguments());
        assertThat(guard.getExitCode()).isZero();
    }

    @Test
    void errorWhenJobIdIsWrongOrMissing() {
        // ジョブ ID が誤っていると @ConditionalOnProperty でジョブの Bean 自体が作られない
        for (String requested : new String[] {"JOB9999", "", null}) {
            BatchJobGuard guard = new BatchJobGuard(requested, List.of());
            guard.run(new DefaultApplicationArguments());
            assertThat(guard.getExitCode()).as("app.batch.job=%s", requested).isEqualTo(BatchJob.ERROR);
        }
    }
}
