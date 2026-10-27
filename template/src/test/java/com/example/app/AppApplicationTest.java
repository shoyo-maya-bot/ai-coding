package com.example.app;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/** 起動クラスの、起動前のバッチ判定と起動失敗時の終了コード. */
class AppApplicationTest {

    @Test
    @DisplayName("バッチの起動失敗はREADMEの決まりどおり終了コード8")
    void startupFailureExitsWithEight() {
        // 後退: 起動時の失敗（DB につながらない等）は JVM の既定の 1 で終わり、README の 8（異常）と合わなかった
        assertThat(AppApplication.startupFailureExitCode()).isEqualTo(8);
    }

    @Test
    @DisplayName("環境変数のプロファイルにbatchがあればバッチ")
    void batchProfileInEnvMeansBatch() {
        assertThat(AppApplication.batchRequested(new String[0], null, "cloud,batch")).isTrue();
        assertThat(AppApplication.batchRequested(new String[0], null, " cloud , batch ")).isTrue();
        assertThat(AppApplication.batchRequested(new String[0], null, "cloud")).isFalse();
        assertThat(AppApplication.batchRequested(new String[0], null, "batchx")).isFalse();
        assertThat(AppApplication.batchRequested(new String[0], null, null)).isFalse();
    }

    @Test
    @DisplayName("引数とシステムプロパティは環境変数より優先する")
    void argsAndSysPropTakePrecedenceOverEnv() {
        String[] args = {"--app.batch.job=JOB0001", "--spring.profiles.active=local,batch"};
        assertThat(AppApplication.batchRequested(args, null, "cloud")).isTrue();
        String[] localOnly = {"--spring.profiles.active=local"};
        assertThat(AppApplication.batchRequested(localOnly, null, "batch")).isFalse();
        assertThat(AppApplication.batchRequested(new String[0], "batch", "cloud")).isTrue();
        assertThat(AppApplication.batchRequested(new String[0], "cloud", "batch")).isFalse();
    }
}
