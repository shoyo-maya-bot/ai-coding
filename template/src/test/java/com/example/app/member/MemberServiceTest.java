package com.example.app.member;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.app.common.BusinessException;
import com.example.app.common.MessageIds;
import com.example.app.common.NotFoundException;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;

class MemberServiceTest {

    /** DB を使わない差し替え用の Mapper. */
    static class InMemoryMapper implements MemberMapper {
        final Map<Long, Member> rows = new HashMap<>();
        long seq = 0;

        @Override
        public Optional<Member> findById(long id) {
            return Optional.ofNullable(rows.get(id));
        }

        @Override
        public boolean existsByEmail(String email) {
            return rows.values().stream().anyMatch(m -> m.email().equals(email));
        }

        @Override
        public int insert(MemberRecord member) {
            member.setId(++seq);
            rows.put(member.getId(), member.toMember());
            return 1;
        }
    }

    private final InMemoryMapper mapper = new InMemoryMapper();
    private final MemberService service = new MemberService(mapper);

    @Test
    void register_normalizesEmailAndAssignsId() {
        Member m = service.register(" 山田 太郎 ", " Taro@Example.COM ");

        assertThat(m.id()).isEqualTo(1L);
        assertThat(m.name()).isEqualTo("山田 太郎");
        assertThat(m.email()).isEqualTo("taro@example.com");
    }

    @Test
    void register_rejectsDuplicateEmailIgnoringCase() {
        service.register("A", "a@example.com");

        assertThatThrownBy(() -> service.register("B", "A@EXAMPLE.com"))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getMessageId())
                .isEqualTo(MessageIds.EMAIL_ALREADY_USED);
    }

    @Test
    void register_duplicateErrorDoesNotCarryEmail() {
        // 後退: 409 の応答（メッセージの埋め込み値）に、入力したメールアドレスをそのまま入れていた
        service.register("A", "a@example.com");

        assertThatThrownBy(() -> service.register("B", "a@example.com"))
                .isInstanceOf(BusinessException.class)
                .satisfies(e -> assertThat(((BusinessException) e).getArgs()).isEmpty())
                .satisfies(e -> assertThat(e.getMessage()).doesNotContain("a@example.com"));
    }

    @Test
    void register_concurrentDuplicateBecomesBusinessError() {
        // 事前の確認をすり抜けた（同時に登録された）ケース: DB の一意制約で失敗しても 409 の業務エラーにする
        MemberMapper racing = new InMemoryMapper() {
            @Override
            public int insert(MemberRecord member) {
                throw new DuplicateKeyException("member_email_key");
            }
        };

        assertThatThrownBy(() -> new MemberService(racing).register("A", "a@example.com"))
                .isInstanceOf(BusinessException.class)
                .extracting(e -> ((BusinessException) e).getMessageId())
                .isEqualTo(MessageIds.EMAIL_ALREADY_USED);
    }

    @Test
    void get_throwsNotFoundForUnknownId() {
        assertThatThrownBy(() -> service.get(99))
                .isInstanceOf(NotFoundException.class)
                .extracting(e -> ((NotFoundException) e).getMessageId())
                .isEqualTo(MessageIds.MEMBER_NOT_FOUND);
    }
}
