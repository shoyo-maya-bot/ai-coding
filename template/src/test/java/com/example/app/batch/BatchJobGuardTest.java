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

    @Test
    void jobIdIsMatchedIgnoringCaseLikeConditionalOnProperty() {
        // 後退: job0001 でも @ConditionalOnProperty（havingValue は大文字小文字を区別しない）でジョブが登録されて取込が走るのに、
        // ここだけ equals で比べていたため、取込の後に「ジョブ ID が不正」で 8 を返していた
        for (String requested : new String[] {"job0001", "Job0001"}) {
            BatchJobGuard guard = new BatchJobGuard(requested, List.of(job0001));
            guard.run(new DefaultApplicationArguments());
            assertThat(guard.getExitCode()).as("app.batch.job=%s", requested).isZero();
        }
    }

    @Test
    void surroundingSpacesAreNotTrimmed() {
        // 後退: 前後の空白を取り除いて比べていたため、" JOB0001"（実際にはジョブは登録されず何も動かない）が 0 になっていた.
        // ここでは比べ方だけを見るため、JOB0001 のジョブを渡しても 8 になることを確かめる（実際の登録との一致は OrderImportJobRegistrationTest）
        for (String requested : new String[] {" JOB0001", "JOB0001 "}) {
            BatchJobGuard guard = new BatchJobGuard(requested, List.of(job0001));
            guard.run(new DefaultApplicationArguments());
            assertThat(guard.getExitCode()).as("app.batch.job=[%s]", requested).isEqualTo(BatchJob.ERROR);
        }
    }
}
