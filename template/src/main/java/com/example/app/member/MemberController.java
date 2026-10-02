package com.example.app.member;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/** 会員 API（API ID: API0001 照会 / API0002 登録）. */
@RestController
@RequestMapping("/api/v1/members")
public class MemberController {

    private final MemberService service;

    public MemberController(MemberService service) {
        this.service = service;
    }

    /** 登録の入力. */
    public record RegisterRequest(
            @NotBlank @Size(max = 50) String name, @NotBlank @Email @Size(max = 254) String email) {}

    @GetMapping("/{id}")
    public Member get(@PathVariable("id") long id) {
        return service.get(id);
    }

    @PostMapping
    public ResponseEntity<Member> register(@Valid @RequestBody RegisterRequest req) {
        Member created = service.register(req.name(), req.email());
        return ResponseEntity.created(URI.create("/api/v1/members/" + created.id())).body(created);
    }
}
