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
}
