package com.example.app.order.batch;

import com.example.app.batch.BatchJob;
import com.example.app.common.MessageIds;
import com.example.app.order.ImportResult;
import com.example.app.order.OrderImportService;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

/**
 * 注文ファイル取込バッチ（ジョブ ID: JOB0001）.
 *
 * <p>起動例: {@code --spring.profiles.active=local,batch --app.batch.job=JOB0001 --input=s3://sample-bucket/orders.csv}
 *
 * <p>終了コード: 0 正常 / 4 形式エラーの行あり（取込は続行）/ 8 異常終了。実案件では運用設計の終了コード体系に合わせる。
 * ジョブ ID の誤り・未指定は {@link com.example.app.batch.BatchJobGuard} が 8 にする。
 *
 * <p>入力は全体をメモリに読み（上限 {@code app.batch.max-input-bytes}。{@link DefaultFileFetcher}）、ファイル全体を 1 トランザクションで登録する
 * （local/README.md の「取込の大きさとコミットの単位」）。
 */
@Component
@ConditionalOnProperty(name = "app.batch.job", havingValue = "JOB0001")
public class OrderImportJob implements BatchJob, ApplicationRunner, ExitCodeGenerator {

    static final String JOB_ID = "JOB0001";

    private static final Logger log = LoggerFactory.getLogger(OrderImportJob.class);

    private final FileFetcher fetcher;
    private final OrderImportService service;
    private int exitCode = OK;

    public OrderImportJob(FileFetcher fetcher, OrderImportService service) {
        this.fetcher = fetcher;
        this.service = service;
    }

    @Override
    public String jobId() {
        return JOB_ID;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> input = args.getOptionValues("input");
        if (input == null || input.size() != 1) {
            log.error("{} JOB0001 引数 --input=<s3://バケット/キー またはファイル> が必要です", MessageIds.BATCH_INVALID_ARGS);
            exitCode = ERROR;
            return;
        }
        log.info("{} JOB0001 開始 input={}", MessageIds.IMPORT_STARTED, input.get(0));
        try {
            ImportResult r = service.importLines(fetcher.readLines(input.get(0)));
            r.errors().forEach(e -> log.warn("{} {}", MessageIds.IMPORT_LINE_SKIPPED, e));
            log.info("{} JOB0001 終了 imported={} duplicated={} errors={}",
                    MessageIds.IMPORT_FINISHED, r.imported(), r.duplicated(), r.errors().size());
            exitCode = r.hasErrors() ? WARN : OK;
        } catch (Exception e) {
            log.error("{} JOB0001 異常終了", MessageIds.BATCH_FAILED, e);
            exitCode = ERROR;
        }
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
