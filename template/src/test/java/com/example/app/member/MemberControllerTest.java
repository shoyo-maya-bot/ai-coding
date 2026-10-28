package com.example.app.member;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.app.common.ApiExceptionHandler;
import java.sql.SQLTransientConnectionException;
import java.util.Locale;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.ResourceBundleMessageSource;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.http.MediaType;
import org.springframework.jdbc.CannotGetJdbcConnectionException;
import org.springframework.transaction.CannotCreateTransactionException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

/** Spring を起動せずに、コントローラと例外ハンドラの組み合わせを確かめる. */
class MemberControllerTest {

    private MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = build(new MemberServiceTest.InMemoryMapper());
    }

    private MockMvc build(MemberMapper mapper) {
        StaticMessageSource messages = new StaticMessageSource();
        messages.addMessage("APPE0002", Locale.JAPANESE, "会員が見つかりません（会員ID: {0}）。");
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        MemberService service = new MemberService(mapper);
        return MockMvcBuilders.standaloneSetup(new MemberController(service))
                .setControllerAdvice(new ApiExceptionHandler(messages))
                .setValidator(validator)
                .build();
    }

    @Test
    void registerThenGet() throws Exception {
        mvc.perform(post("/api/v1/members")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"山田\",\"email\":\"yamada@example.com\"}"))
                .andExpect(status().isCreated())
                .andExpect(header().string("Location", "/api/v1/members/1"))
                .andExpect(jsonPath("$.id").value(1));

        mvc.perform(get("/api/v1/members/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.email").value("yamada@example.com"));
    }

    @Test
    void duplicateEmailReturns409WithoutTheAddress() throws Exception {
        // 後退: 409 の message に「（yamada@example.com）」とメールアドレスを入れて返していた
        ResourceBundleMessageSource real = new ResourceBundleMessageSource();
        real.setBasename("messages");
        real.setDefaultEncoding("UTF-8");
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        MockMvc withRealMessages = MockMvcBuilders
                .standaloneSetup(new MemberController(new MemberService(new MemberServiceTest.InMemoryMapper())))
                .setControllerAdvice(new ApiExceptionHandler(real))
                .setValidator(validator)
                .build();
        String body = "{\"name\":\"山田\",\"email\":\"yamada@example.com\"}";
        withRealMessages.perform(post("/api/v1/members").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isCreated());

        String response = withRealMessages
                .perform(post("/api/v1/members").contentType(MediaType.APPLICATION_JSON).content(body))
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.messageId").value("APPE0003"))
                .andExpect(jsonPath("$.message").value("このメールアドレスでは登録できません。"))
                .andReturn().getResponse().getContentAsString(java.nio.charset.StandardCharsets.UTF_8);
        assertThat(response).doesNotContain("yamada@example.com").doesNotContain("yamada");
    }

    @Test
    void notFoundReturns404WithMessageId() throws Exception {
        mvc.perform(get("/api/v1/members/42"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.messageId").value("APPE0002"))
                .andExpect(jsonPath("$.message").value("会員が見つかりません（会員ID: 42）。"));
    }

    @Test
    void invalidInputReturns400() throws Exception {
        mvc.perform(post("/api/v1/members")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"name\":\"\",\"email\":\"not-an-email\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.messageId").value("APPE0001"))
                .andExpect(jsonPath("$.details.length()").value(2));
    }

    @Test
    void notFoundMessageHasNoThousandsSeparator() throws Exception {
        mvc.perform(get("/api/v1/members/1234"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.message").value("会員が見つかりません（会員ID: 1234）。"));
    }

    @Test
    void wrongIdTypeReturns400InSameShape() throws Exception {
        mvc.perform(get("/api/v1/members/abc"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.messageId").value("APPE0001"))
                .andExpect(jsonPath("$.details[0]").value("id: 形式が正しくありません"));
    }

    @Test
    void brokenJsonReturns400InSameShape() throws Exception {
        mvc.perform(post("/api/v1/members").contentType(MediaType.APPLICATION_JSON).content("{\"name\":"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.messageId").value("APPE0001"));
    }

    @Test
    void unsupportedMethodKeepsStatusAndShape() throws Exception {
        mvc.perform(post("/api/v1/members/1"))
                .andExpect(status().isMethodNotAllowed())
                .andExpect(jsonPath("$.messageId").value("APPE0004"));
    }

    @Test
    void unexpectedErrorReturns500WithoutDetails() throws Exception {
        MockMvc broken = build(new MemberServiceTest.InMemoryMapper() {
            @Override
            public Optional<Member> findById(long id) {
                throw new IllegalStateException("connection refused: secret-host:5432");
            }
        });
        broken.perform(get("/api/v1/members/1"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.messageId").value("APPE9999"))
                .andExpect(jsonPath("$.details.length()").value(0));
    }

    @Test
    void databaseDownReturns503() throws Exception {
        MockMvc down = build(new MemberServiceTest.InMemoryMapper() {
            @Override
            public Optional<Member> findById(long id) {
                throw new CannotGetJdbcConnectionException("Failed to obtain JDBC Connection",
                        new SQLTransientConnectionException("Connection refused"));
            }
        });
        down.perform(get("/api/v1/members/1"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.messageId").value("APPE0008"))
                .andExpect(jsonPath("$.details.length()").value(0));
    }

    @Test
    void transactionCannotStartReturns503() throws Exception {
        MockMvc down = build(new MemberServiceTest.InMemoryMapper() {
            @Override
            public Optional<Member> findById(long id) {
                throw new CannotCreateTransactionException("Could not open JDBC Connection for transaction",
                        new java.net.ConnectException("Connection refused"));
            }
        });
        down.perform(get("/api/v1/members/1"))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.messageId").value("APPE0008"));
    }
}
