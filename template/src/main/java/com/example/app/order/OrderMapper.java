package com.example.app.order;

import org.apache.ibatis.annotations.Mapper;

/** 注文テーブルの SQL（本体は resources/mapper/OrderMapper.xml）. */
@Mapper
public interface OrderMapper {

    /**
     * 注文番号が未登録なら登録する（再実行しても重複しない＝冪等）.
     *
     * @return 登録した件数（既にあれば 0）
     */
    int insertIfAbsent(Order order);

    /** 会員が存在するか（外部キー違反で取込全体が取り消されないよう、登録の前に確かめる）. */
    boolean memberExists(long memberId);
}
