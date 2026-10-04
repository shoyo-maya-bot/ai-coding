package com.example.app.order;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class OrderImportServiceTest {

    private final FakeOrderMapper mapper = new FakeOrderMapper();
    private final OrderImportService service = new OrderImportService(mapper);

    @Test
    void importsValidLinesAndSkipsDuplicates() {
        List<String> lines = List.of(
                "﻿" + OrderImportService.HEADER,
                "A001,1,P-01,2",
                "A002,1,P-02,1",
                "",
                "A001,1,P-01,2");

        ImportResult r = service.importLines(lines);

        assertThat(r.imported()).isEqualTo(2);
        assertThat(r.duplicated()).isEqualTo(1);
        assertThat(r.errors()).isEmpty();
    }

    @Test
    void rerunIsIdempotent() {
        List<String> lines = List.of(OrderImportService.HEADER, "A001,1,P-01,2");
        service.importLines(lines);

        ImportResult second = service.importLines(lines);

        assertThat(second.imported()).isZero();
        assertThat(second.duplicated()).isEqualTo(1);
    }

    @Test
    void badLinesAreReportedWithLineNumbersAndOthersContinue() {
        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER, "A001,x,P-01,2", "A002,1,P-02,0", "A003,1,P-03,5"));

        assertThat(r.imported()).isEqualTo(1);
        assertThat(r.errors()).containsExactly("2: member_id が数値ではありません", "3: quantity は 1〜999 です（0）");
    }

    @Test
    void unknownMemberSkipsOnlyThatLine() {
        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER, "A001,1,P-01,1", "A002,999,P-01,1", "A003,1,P-02,1"));

        assertThat(r.imported()).isEqualTo(2);
        assertThat(r.errors()).containsExactly("3: member_id の会員が存在しません（999）");
        assertThat(mapper.stored).containsExactlyInAnyOrder("A001", "A003");
        assertThat(mapper.memberLookups).as("同じ会員は 1 回だけ確かめる").isEqualTo(2);
    }

    @Test
    void tooLongCodeSkipsOnlyThatLine() {
        String longNo = "A".repeat(21);
        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER, longNo + ",1,P-01,1", "A002,1,P-01,1"));

        assertThat(r.imported()).isEqualTo(1);
        assertThat(r.errors()).containsExactly("2: order_no は 20 文字以内です（21 文字）");
    }

    @Test
    void wrongHeaderIsRejected() {
        assertThatThrownBy(() -> service.importLines(List.of("no,member")))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("見出し行");
    }

    @ParameterizedTest
    @CsvSource(delimiter = '|', value = {
        "A001,1,P-01        | 列数が 4 ではありません（3 列）",
        "' ,1,P-01,1'       | order_no が空です",
        "'A001,1, ,1'       | product_code が空です",
        "A001,1,P-01,1000   | quantity は 1〜999 です（1000）",
        "A001,1,P-01234567890123456789,1 | product_code は 20 文字以内です（22 文字）"
    })
    void parseRejects(String line, String message) {
        assertThatThrownBy(() -> OrderImportService.parse(line)).hasMessage(message);
    }

    @Test
    void parseAcceptsExactlyTwentyChars() {
        String twenty = "B".repeat(20);
        assertThat(OrderImportService.parse(twenty + ",1," + twenty + ",1").orderNo()).isEqualTo(twenty);
    }
}
