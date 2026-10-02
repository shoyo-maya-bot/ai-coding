package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

/**
 * アプリの起動クラス.
 *
 * <p>既定は API（Web サーバー）として起動する。プロファイル batch を付けるとバッチとして起動し、
 * ジョブの終了コードでプロセスを終える。
 */
@SpringBootApplication
public class AppApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext ctx = SpringApplication.run(AppApplication.class, args);
        if (ctx.getEnvironment().matchesProfiles("batch")) {
            System.exit(SpringApplication.exit(ctx));
        }
    }
}
