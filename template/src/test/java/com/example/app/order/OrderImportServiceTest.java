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
    void sameOrderNoWithDifferentContentIsCountedAsConflict() {
        // 後退: 内容の違う重複を、同じ内容の重複（duplicated）と区別せずに黙って捨てていた
        service.importLines(List.of(OrderImportService.HEADER, "A001,1,P-01,2"));

        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER,
                "A001,1,P-01,2",   // 同じ内容: 再実行による重複
                "A001,1,P-01,3",   // 数量が違う
                "A001,2,P-01,2",   // 会員が違う
                "A002,1,P-02,1"));

        assertThat(r.imported()).isEqualTo(1);
        assertThat(r.duplicated()).isEqualTo(1);
        assertThat(r.conflicted()).isEqualTo(2);
        assertThat(r.conflicts()).containsExactly(
                "3: order_no A001 は登録済みで、内容（member_id・product_code・quantity）が違います",
                "4: order_no A001 は登録済みで、内容（member_id・product_code・quantity）が違います");
        assertThat(r.errors()).isEmpty();
        assertThat(mapper.orders.get("A001").quantity()).as("登録済みの内容は変えない").isEqualTo(2);
    }

    @Test
    void conflictWithinTheSameFileIsDetected() {
        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER, "B001,1,P-01,1", "B001,1,P-99,1"));

        assertThat(r.imported()).isEqualTo(1);
        assertThat(r.duplicated()).isZero();
        assertThat(r.conflicts()).containsExactly(
                "3: order_no B001 は登録済みで、内容（member_id・product_code・quantity）が違います");
    }

    @Test
    void quotedValuesAreUnquoted() {
        // 後退: split(",") で分けていたため、引用符で囲んだ値（"P,01" など）が列数の誤りや引用符付きの値になっていた
        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER, "\"A001\",1,\"P,01\",2", "A002,\"1\",\"P\"\"02\",1"));

        assertThat(r.errors()).isEmpty();
        assertThat(mapper.orders.get("A001")).isEqualTo(new Order("A001", 1, "P,01", 2));
        assertThat(mapper.orders.get("A002")).isEqualTo(new Order("A002", 1, "P\"02", 1));
    }

    @Test
    void lineWithBrokenQuotesIsSkippedWithClearMessage() {
        ImportResult r = service.importLines(List.of(
                OrderImportService.HEADER, "\"A001,1,P-01,2", "A002,1,P-02,1"));

        assertThat(r.imported()).isEqualTo(1);
        assertThat(r.errors()).containsExactly("2: 引用符（\"）が閉じていません（値の中の改行には対応していません）");
    }

    @ParameterizedTest
    @CsvSource(delimiter = '|', quoteCharacter = '`', value = {
        "a,b,c                | a;b;c",
        "\"a,b\",c          | a,b;c",
        "\"a\"\"b\",c     | a\"b;c",
        "a,,c                 | a;;c",
        "a,                   | a;",
        " \"a\" , b         | a; b",
        "\"\",x             | ;x"
    })
    void splitCsvHandlesQuotes(String line, String joined) {
        assertThat(String.join(";", OrderImportService.splitCsv(line))).isEqualTo(joined);
    }

    @ParameterizedTest
    @CsvSource(delimiter = '|', quoteCharacter = '`', value = {
        "\"abc               | 引用符（\"）が閉じていません（値の中の改行には対応していません）",
        "\"a\"b,c           | 閉じた引用符（\"）の後ろに区切り（,）以外の文字があります",
        "a\"b,c              | 引用符（\"）は値の全体を囲むときだけ使えます"
    })
    void splitCsvRejectsBrokenQuotes(String line, String message) {
        assertThatThrownBy(() -> OrderImportService.splitCsv(line))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage(message);
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

    @ParameterizedTest(name = "parseRejects [{index}] {arguments}")
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
