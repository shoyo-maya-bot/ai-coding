package com.example.app.batch;

import com.example.app.common.MessageIds;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.ExitCodeGenerator;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

/**
 * バッチとして起動したのに、指定のジョブ ID に当たるジョブが無いときに異常終了させる.
 *
 * <p>これが無いと、ジョブ ID の誤りや指定漏れでも何も実行せずに終了コード 0 で終わり、
 * スケジューラからは正常終了に見えてしまう。
 */
@Component
@Profile("batch")
public class BatchJobGuard implements ApplicationRunner, ExitCodeGenerator {

    private static final Logger log = LoggerFactory.getLogger(BatchJobGuard.class);

    private final String requested;
    private final List<BatchJob> jobs;
    private int exitCode = BatchJob.OK;

    @Autowired
    public BatchJobGuard(@Value("${app.batch.job:}") String requested, ObjectProvider<BatchJob> jobs) {
        this(requested, jobs.orderedStream().toList());
    }

    BatchJobGuard(String requested, List<BatchJob> jobs) {
        this.requested = requested == null ? "" : requested.trim();
        this.jobs = List.copyOf(jobs);
    }

    @Override
    public void run(ApplicationArguments args) {
        boolean found = jobs.stream().anyMatch(j -> j.jobId().equals(requested));
        if (!found) {
            log.error("{} ジョブ ID が不正です app.batch.job={}",
                    MessageIds.BATCH_UNKNOWN_JOB, requested.isEmpty() ? "(未指定)" : requested);
            exitCode = BatchJob.ERROR;
        }
    }

    @Override
    public int getExitCode() {
        return exitCode;
    }
}
