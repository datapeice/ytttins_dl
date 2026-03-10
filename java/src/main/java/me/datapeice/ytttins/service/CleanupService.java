package me.datapeice.ytttins.service;

import me.datapeice.ytttins.config.BotConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.time.Duration;
import java.time.Instant;

/**
 * Periodically removes stale files from the downloads directory.
 *
 * <p>Equivalent to {@code cleanup.py} in the Python version.
 * Files older than {@link #MAX_AGE} are deleted every {@link #INTERVAL_MS} milliseconds.
 */
@Service
public class CleanupService {

    private static final Logger log = LoggerFactory.getLogger(CleanupService.class);

    /** Files older than this duration are removed. */
    private static final Duration MAX_AGE = Duration.ofMinutes(10);

    /** How often to run cleanup (milliseconds). 60 000 = every minute. */
    private static final long INTERVAL_MS = 60_000L;

    private final BotConfig config;

    public CleanupService(BotConfig config) {
        this.config = config;
    }

    /**
     * Scheduled task — runs every minute and deletes downloads older than 10 minutes.
     * Uses {@code fixedDelay} so consecutive runs don't overlap.
     */
    @Scheduled(fixedDelay = INTERVAL_MS)
    public void deleteOldFiles() {
        Path downloadsDir = config.getDownloadsDir();
        if (!Files.exists(downloadsDir)) return;

        Instant cutoff = Instant.now().minus(MAX_AGE);
        int deleted = 0;

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(downloadsDir)) {
            for (Path file : stream) {
                if (!Files.isRegularFile(file)) continue;
                try {
                    BasicFileAttributes attrs = Files.readAttributes(file, BasicFileAttributes.class);
                    if (attrs.lastModifiedTime().toInstant().isBefore(cutoff)) {
                        Files.delete(file);
                        deleted++;
                        log.debug("Deleted old file: {}", file.getFileName());
                    }
                } catch (IOException e) {
                    log.warn("Could not process file {}: {}", file, e.getMessage());
                }
            }
        } catch (IOException e) {
            log.error("Cleanup scan failed: {}", e.getMessage());
        }

        if (deleted > 0) {
            log.info("🧹 Cleanup: deleted {} stale file(s) from {}", deleted, downloadsDir);
        }
    }
}
