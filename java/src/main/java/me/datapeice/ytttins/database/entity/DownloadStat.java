package me.datapeice.ytttins.database.entity;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Aggregate download counter per content type ("Video" or "Music").
 *
 * <p>Equivalent to {@code DownloadStat} model in {@code database/models.py}.
 */
@Entity
@Table(name = "download_stats")
@Getter
@Setter
@NoArgsConstructor
public class DownloadStat {

    /** Primary key — either {@code "Video"} or {@code "Music"}. */
    @Id
    @Column(name = "content_type", nullable = false)
    private String contentType;

    @Column(nullable = false)
    private long count = 0;

    public DownloadStat(String contentType) {
        this.contentType = contentType;
    }

    public void increment() {
        this.count++;
    }
}
