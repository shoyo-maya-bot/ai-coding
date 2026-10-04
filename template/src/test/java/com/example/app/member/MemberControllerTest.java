package com.example.app.member;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.example.app.common.ApiExceptionHandler;
import java.util.Locale;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.http.MediaType;
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
}
