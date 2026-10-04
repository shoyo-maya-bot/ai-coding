package com.example.app.batch;

/** バッチのジョブ. ジョブ ID（JOB + 4 桁）で起動対象を選ぶ（{@code --app.batch.job=JOB0001}）. */
public interface BatchJob {

    /** 終了コード: 正常. */
    int OK = 0;
    /** 終了コード: 警告（処理は続行した）. */
    int WARN = 4;
    /** 終了コード: 異常終了. */
    int ERROR = 8;

    String jobId();
}
