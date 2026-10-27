package com.example.app.order;

import java.util.List;

/**
 * 取込結果.
 *
 * @param imported 登録した件数
 * @param duplicated 登録済みで内容も同じため飛ばした件数（再実行など。正常）
 * @param errors 形式エラーで飛ばした行（"行番号: 理由"）
 * @param conflicts 登録済みの注文番号で内容（会員・商品・数量）が違うため飛ばした行（"行番号: 理由"）
 */
public record ImportResult(int imported, int duplicated, List<String> errors, List<String> conflicts) {

    public ImportResult {
        errors = List.copyOf(errors);
        conflicts = List.copyOf(conflicts);
    }

    /** 内容の違う重複が無いときの結果. */
    public ImportResult(int imported, int duplicated, List<String> errors) {
        this(imported, duplicated, errors, List.of());
    }

    public boolean hasErrors() {
        return !errors.isEmpty();
    }

    /** 内容の違う重複があったか（取り込まずに飛ばしたので、人が確かめる必要がある）. */
    public boolean hasConflicts() {
        return !conflicts.isEmpty();
    }

    /** 内容の違う重複の件数. */
    public int conflicted() {
        return conflicts.size();
    }
}
