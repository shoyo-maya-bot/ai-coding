package com.example.app.order.batch;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.app.batch.BatchJob;
import com.example.app.batch.BatchJobGuard;
import com.example.app.order.FakeOrderMapper;
import com.example.app.order.OrderImportService;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.DefaultApplicationArguments;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.env.MapPropertySource;

/**
 * JOB0001 をどの起動のときに登録するか.
 *
 * <p>後退: {@code @ConditionalOnProperty(app.batch.job=JOB0001)} だけを見ていたため、プロファイル batch を付けずに
 * {@code --app.batch.job=JOB0001} を渡すと、API（Web）として起動したまま取込が走った（終了コードも返らない）。
 */
class OrderImportJobRegistrationTest {

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withBean(FileFetcher.class, () -> loc -> List.of())
            .withBean(OrderImportService.class, () -> new OrderImportService(new FakeOrderMapper()))
            .withUserConfiguration(OrderImportJob.class);

    @Test
    void notRegisteredWithoutBatchProfile() {
        runner.withPropertyValues("app.batch.job=JOB0001")
                .run(ctx -> assertThat(ctx).doesNotHaveBean(OrderImportJob.class));
        runner.withPropertyValues("app.batch.job=JOB0001", "spring.profiles.active=local")
                .run(ctx -> assertThat(ctx).doesNotHaveBean(OrderImportJob.class));
    }

    @Test
    void registeredWithBatchProfileAndJobId() {
        runner.withPropertyValues("app.batch.job=JOB0001", "spring.profiles.active=local,batch")
                .run(ctx -> assertThat(ctx).hasSingleBean(OrderImportJob.class));
    }

    @Test
    void notRegisteredForOtherJobId() {
        runner.withPropertyValues("app.batch.job=JOB9999", "spring.profiles.active=batch")
                .run(ctx -> assertThat(ctx).doesNotHaveBean(OrderImportJob.class));
    }

    /**
     * ジョブが登録される（＝取込が動く）ことと、{@link BatchJobGuard} が正常（0）と判断することが、どの値でも一致する.
     *
     * <p>後退: ジョブの登録（{@code @ConditionalOnProperty}. 大文字小文字を区別しない）と BatchJobGuard（equals、前後の空白を除く）で
     * 比べ方が違い、{@code job0001} は取込の後に 8、{@code " JOB0001"} は何も動かずに 0 になっていた。
     * 値は起動引数のとおりに渡す（withPropertyValues は前後の空白を取り除くので使わない）。
     */
    @Test
    void guardAgreesWithJobRegistration() {
        ApplicationContextRunner withGuard = runner.withUserConfiguration(BatchJobGuard.class);
        String[] values = {"JOB0001", "job0001", "Job0001", " JOB0001", "JOB0001 ", "JOB9999", "JOB00011", ""};
        for (String value : values) {
            Map<String, Object> props = Map.of("app.batch.job", value, "spring.profiles.active", "batch");
            withGuard.withInitializer(ctx -> ctx.getEnvironment().getPropertySources().addFirst(
                            new MapPropertySource("args", props)))
                    .run(ctx -> {
                        assertThat(ctx).hasNotFailed();
                        BatchJobGuard guard = ctx.getBean(BatchJobGuard.class);
                        guard.run(new DefaultApplicationArguments());
                        boolean registered = ctx.getBeansOfType(OrderImportJob.class).size() == 1;
                        assertThat(guard.getExitCode() == BatchJob.OK)
                                .as("app.batch.job=[%s] 登録=%s 終了コード=%d", value, registered, guard.getExitCode())
                                .isEqualTo(registered);
                    });
        }
    }
}
