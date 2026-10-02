-- サンプルアプリのテーブル（初回起動時に実行）
CREATE TABLE member (
    id         BIGSERIAL PRIMARY KEY,
    name       VARCHAR(50)  NOT NULL,
    email      VARCHAR(254) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    order_no     VARCHAR(20) PRIMARY KEY,
    member_id    BIGINT      NOT NULL REFERENCES member (id),
    product_code VARCHAR(20) NOT NULL,
    quantity     INTEGER     NOT NULL CHECK (quantity BETWEEN 1 AND 999),
    imported_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
