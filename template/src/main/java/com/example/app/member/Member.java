package com.example.app.member;

/**
 * 会員.
 *
 * @param id 会員 ID
 * @param name 氏名
 * @param email メールアドレス（一意）
 */
public record Member(Long id, String name, String email) {}
