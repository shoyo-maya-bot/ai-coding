package com.example.app.member;

import com.example.app.common.BusinessException;
import com.example.app.common.MessageIds;
import com.example.app.common.NotFoundException;
import java.util.Locale;
import org.springframework.dao.DuplicateKeyException;
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
        // ID は文字列で渡す。数値のまま渡すと MessageFormat が「1,234」と桁区切りを入れる
        return mapper.findById(id)
                .orElseThrow(() -> new NotFoundException(MessageIds.MEMBER_NOT_FOUND, String.valueOf(id)));
    }

    @Transactional
    public Member register(String name, String email) {
        String normalized = email.trim().toLowerCase(Locale.ROOT);
        // 事前の確認は「よくある重複」を早く返すため。同時に登録されたときの最終的な判定は DB の一意制約に任せる
        if (mapper.existsByEmail(normalized)) {
            throw new BusinessException(MessageIds.EMAIL_ALREADY_USED, normalized);
        }
        MemberRecord rec = new MemberRecord(name.trim(), normalized);
        try {
            mapper.insert(rec);
        } catch (DuplicateKeyException e) {
            throw new BusinessException(MessageIds.EMAIL_ALREADY_USED, normalized);
        }
        return rec.toMember();
    }
}
