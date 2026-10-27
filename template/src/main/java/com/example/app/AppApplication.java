package com.example.app;

import com.example.app.batch.BatchJob;
import java.util.Arrays;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

/**
 * アプリの起動クラス.
 *
 * <p>既定は API（Web サーバー）として起動する。プロファイル batch を付けるとバッチとして起動し、
 * ジョブの終了コードでプロセスを終える。
 *
 * <p>バッチとして起動するときに起動そのものが失敗した（DB につながらない・設定の誤りなどで Spring の起動が例外で終わった）ときも、
 * README の終了コードの決まりどおり 8（異常）で終える（何もしないと JVM の既定の 1 になる）。
 * バッチかどうかは、起動前に分かる値（引数 {@code --spring.profiles.active=…}・システムプロパティ・環境変数
 * {@code SPRING_PROFILES_ACTIVE}）で決める。
 */
@SpringBootApplication
public class AppApplication {

    public static void main(String[] args) {
        boolean batch = batchRequested(
                args, System.getProperty("spring.profiles.active"), System.getenv("SPRING_PROFILES_ACTIVE"));
        ConfigurableApplicationContext ctx;
        try {
            ctx = SpringApplication.run(AppApplication.class, args);
        } catch (RuntimeException | Error e) {
            // Spring が原因をログに出している. バッチなら終了コードを決まりどおりにする
            if (batch) {
                System.exit(startupFailureExitCode());
            }
            throw e;
        }
        if (ctx.getEnvironment().matchesProfiles("batch")) {
            System.exit(SpringApplication.exit(ctx));
        }
    }

    /** バッチの起動が失敗したときの終了コード（異常 8）. */
    static int startupFailureExitCode() {
        return BatchJob.ERROR;
    }

    /**
     * 起動前に、プロファイル batch が指定されているか. Spring と同じく、引数 → システムプロパティ → 環境変数の順に、最初に見つかった指定を使う.
     *
     * @param args 起動引数（{@code --spring.profiles.active=cloud,batch} など）
     * @param sysProp システムプロパティ {@code spring.profiles.active}（無ければ null）
     * @param env 環境変数 {@code SPRING_PROFILES_ACTIVE}（無ければ null）
     */
    static boolean batchRequested(String[] args, String sysProp, String env) {
        String fromArgs = null;
        for (String a : args == null ? new String[0] : args) {
            if (a.startsWith("--spring.profiles.active=")) {
                fromArgs = a.substring("--spring.profiles.active=".length());
            }
        }
        String active = fromArgs != null ? fromArgs : sysProp != null ? sysProp : env;
        return active != null && Arrays.stream(active.split(",")).map(String::trim).anyMatch("batch"::equals);
    }
}
