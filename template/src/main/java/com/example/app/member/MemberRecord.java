package com.example.app.member;

/** 登録用の可変オブジェクト（MyBatis が採番した ID を書き戻すため）. */
public class MemberRecord {

    private Long id;
    private String name;
    private String email;

    public MemberRecord(String name, String email) {
        this.name = name;
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public void setId(Long id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public Member toMember() {
        return new Member(id, name, email);
    }
}
