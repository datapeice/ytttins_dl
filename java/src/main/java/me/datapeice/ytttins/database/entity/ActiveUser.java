package me.datapeice.ytttins.database.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Tracks which users were active on a given day (one row per user per day).
 *
 * <p>Equivalent to {@code ActiveUser} model in {@code database/models.py}.
 */
@Entity
@Table(name = "active_users",
        uniqueConstraints = @UniqueConstraint(columnNames = {"user_id", "date"}))
@Getter
@Setter
@NoArgsConstructor
public class ActiveUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id", nullable = false)
    private Long userId;

    /**
     * ISO-8601 date string (YYYY-MM-DD) — same format used by the Python version.
     */
    @Column(nullable = false)
    private String date;

    public ActiveUser(Long userId, String date) {
        this.userId = userId;
        this.date = date;
    }
}
