package com.example.app.member;

import com.example.app.common.BusinessException;
import com.example.app.common.MessageIds;
import com.example.app.common.NotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 会員の業務ロジック. */
@Service
public class MemberService {

    private final MemberMapper mapper;

    public MemberService(MemberMapper mapper) {
        this.mapper = mapper;
    }

    @Transactional(readOnly = true)
    public Member get(long id) {
        return mapper.findById(id).orElseThrow(() -> new NotFoundException(MessageIds.MEMBER_NOT_FOUND, id));
    }

    @Transactional
    public Member register(String name, String email) {
        String normalized = email.trim().toLowerCase(java.util.Locale.ROOT);
        if (mapper.existsByEmail(normalized)) {
            throw new BusinessException(MessageIds.EMAIL_ALREADY_USED, normalized);
        }
        MemberRecord rec = new MemberRecord(name.trim(), normalized);
        mapper.insert(rec);
        return rec.toMember();
    }
}
