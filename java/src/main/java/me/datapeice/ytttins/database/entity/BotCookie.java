package me.datapeice.ytttins.database.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * YouTube cookies in Netscape format, stored in the database so they
 * survive container restarts and can be updated via the admin panel.
 *
 * <p>Equivalent to {@code Cookie} model in {@code database/models.py}.
 * <br>Named {@code BotCookie} to avoid clash with {@code javax.servlet.http.Cookie}.
 */
@Entity
@Table(name = "cookies")
@Getter
@Setter
@NoArgsConstructor
public class BotCookie {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** Full contents of a Netscape-format {@code cookies.txt} file. */
    @Column(columnDefinition = "TEXT")
    private String content;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt = LocalDateTime.now();
}
