-- comic-generator 账户域建表（独立库，与主站 lunwen 完全隔离）。
-- 表名统一 comic_ 前缀；默认值面向内测：注册送积分、邀请返积分可后续在
-- comic_app_config 调整，无需改代码。
--
-- 字符集 utf8mb4；NOW() / FROM_UNIXTIME 等函数 MySQL/SQLite harness 两侧兼容。

CREATE TABLE IF NOT EXISTS comic_people (
    people_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
    people_name     VARCHAR(64)  NOT NULL,
    people_phone    VARCHAR(32)  NOT NULL,
    people_password CHAR(64)     NOT NULL COMMENT 'SHA256 hex，无盐',
    points          DECIMAL(12,2) NOT NULL DEFAULT 0 COMMENT '积分余额（权威存储）',
    people_status   VARCHAR(16)  NOT NULL DEFAULT 'PASS',
    frozen_datetime DATETIME     NULL,
    people_reason   VARCHAR(255) NULL,
    people_ip       VARCHAR(45)  NULL,
    people_datetime DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invitation_code VARCHAR(16)  NULL COMMENT '注册时填的邀请码',
    is_admin        TINYINT      NOT NULL DEFAULT 0,
    UNIQUE KEY uk_people_phone (people_phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comic_points (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    people_id   BIGINT       NOT NULL,
    old_num     DECIMAL(12,2) NOT NULL,
    update_num  DECIMAL(12,2) NOT NULL COMMENT '本次变动额（正数）',
    points_num  DECIMAL(12,2) NOT NULL COMMENT '变动后余额',
    receipts    CHAR(1)      NOT NULL COMMENT '+ 收入 / - 支出',
    consumption VARCHAR(64)  NOT NULL COMMENT '用途：注册送积分/漫画生成/邀请送积分/人工调整',
    remarks     VARCHAR(255) NULL,
    delete_flag TINYINT      NOT NULL DEFAULT 0,
    create_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_points_people (people_id, delete_flag)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comic_invitation_code (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    people_id       BIGINT      NOT NULL DEFAULT 0 COMMENT '0=平台匿名码，>0=用户名下码',
    invitation_code VARCHAR(16) NOT NULL,
    invalid         TINYINT     NOT NULL DEFAULT 1 COMMENT '1=可用，0=已核销',
    create_time     DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_invitation_code (invitation_code),
    KEY idx_invitation_owner (people_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comic_login_errorlog (
    id         BIGINT AUTO_INCREMENT PRIMARY KEY,
    `user`     VARCHAR(64)  NOT NULL,
    login_time DATETIME     NOT NULL,
    ip         VARCHAR(45)  NULL,
    disable    CHAR(1)      NOT NULL DEFAULT 'N' COMMENT 'Y=该记录触发锁定',
    KEY idx_login_err (user, login_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comic_project (
    project_id  VARCHAR(64) PRIMARY KEY COMMENT 'comic_YYYYMMDD_xxxxxx',
    people_id   BIGINT      NOT NULL,
    title       VARCHAR(255) NULL,
    create_time DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_project_owner (people_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS comic_app_config (
    id                      INT PRIMARY KEY DEFAULT 1,
    register_points         DECIMAL(12,2) NOT NULL DEFAULT 100 COMMENT '注册赠送积分',
    recommend_points        DECIMAL(12,2) NOT NULL DEFAULT 0   COMMENT '邀请人返积分（内测期0）',
    story_cost_per_1k_token DECIMAL(8,4)  NOT NULL DEFAULT 1.0 COMMENT '故事模型积分/千token',
    image_cost_per_unit     DECIMAL(8,4)  NOT NULL DEFAULT 1.0 COMMENT '每张生图积分',
    CHECK (id = 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 单行配置
INSERT INTO comic_app_config (id) VALUES (1)
ON DUPLICATE KEY UPDATE id = id;
