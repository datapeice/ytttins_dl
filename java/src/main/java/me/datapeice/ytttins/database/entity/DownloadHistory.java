package me.datapeice.ytttins.database.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDateTime;

/**
 * A single download event recorded for admin history and analytics.
 *
 * <p>Equivalent to {@code DownloadHistory} model in {@code database/models.py}.
 */
@Entity
@Table(name = "download_history")
@Getter
@Setter
@NoArgsConstructor
public class DownloadHistory {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "user_id")
    private Long userId;

    private String username;

    private String platform;

    @Column(name = "content_type")
    private String contentType;

    @Column(columnDefinition = "TEXT")
    private String url;

    private String title;

    private LocalDateTime timestamp = LocalDateTime.now();
}
