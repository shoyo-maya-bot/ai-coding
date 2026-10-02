package com.example.app.order.batch;

import java.io.IOException;
import java.util.List;

/** 入力ファイルを行の並びとして読む（s3:// とローカルパスを同じ形で扱う）. */
public interface FileFetcher {

    List<String> readLines(String location) throws IOException;
}
