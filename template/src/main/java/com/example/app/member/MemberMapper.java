package com.example.app.member;

import java.util.Optional;
import org.apache.ibatis.annotations.Mapper;

/** 会員テーブルの SQL（本体は resources/mapper/MemberMapper.xml）. */
@Mapper
public interface MemberMapper {

    Optional<Member> findById(long id);

    boolean existsByEmail(String email);

    /** 登録し、採番された ID を member.id に入れる（useGeneratedKeys）. */
    int insert(MemberRecord member);
}
