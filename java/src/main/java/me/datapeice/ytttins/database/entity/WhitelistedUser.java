package me.datapeice.ytttins.database.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * Whitelisted Telegram user — only users in this table may use the bot
 * when whitelist mode is active.
 *
 * <p>Equivalent to {@code WhitelistedUser} model in {@code database/models.py}.
 */
@Entity
@Table(name = "whitelisted_users")
@Getter
@Setter
@NoArgsConstructor
public class WhitelistedUser {

    @Id
    @Column(nullable = false, unique = true)
    private String username;

    @Column(name = "added_at")
    private LocalDateTime addedAt = LocalDateTime.now();

    public WhitelistedUser(String username) {
        this.username = username;
    }
}
