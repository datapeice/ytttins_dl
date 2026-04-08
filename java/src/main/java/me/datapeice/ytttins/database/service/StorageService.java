package me.datapeice.ytttins.database.service;

import me.datapeice.ytttins.config.BotConfig;
import me.datapeice.ytttins.database.entity.*;
import me.datapeice.ytttins.database.repository.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import jakarta.annotation.PostConstruct;
import java.time.LocalDate;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * Central data-persistence service.
 *
 * <p>Equivalent to {@code database/storage.py} ({@code Stats} class) in the Python version.
 *
 * <h3>Storage strategy</h3>
 * <p>The service always writes to the relational database (PostgreSQL in production,
 * H2 in development/test).  An in-memory cache is maintained for fast whitelist lookups
 * and download counter reads, mirroring the Python implementation's {@code defaultdict}.
 *
 * <p>Unlike the Python version there is no JSON file fallback; the JPA layer with
 * H2 provides equivalent local-dev functionality without the complexity of dual storage.
 */
@Service
public class StorageService {

    private static final Logger log = LoggerFactory.getLogger(StorageService.class);

    // ─── In-memory caches ─────────────────────────────────────────────────────────

    private final Set<String> whitelistedUsers = ConcurrentHashMap.newKeySet();
    private final Map<String, Long> downloadCounts = new ConcurrentHashMap<>();

    // ─── Repositories ─────────────────────────────────────────────────────────────

    private final WhitelistedUserRepository whitelistRepo;
    private final DownloadStatRepository statRepo;
    private final ActiveUserRepository activeUserRepo;
    private final DownloadHistoryRepository historyRepo;
    private final BotConfig config;

    public StorageService(
            WhitelistedUserRepository whitelistRepo,
            DownloadStatRepository statRepo,
            ActiveUserRepository activeUserRepo,
            DownloadHistoryRepository historyRepo,
            BotConfig config) {
        this.whitelistRepo = whitelistRepo;
        this.statRepo = statRepo;
        this.activeUserRepo = activeUserRepo;
        this.historyRepo = historyRepo;
        this.config = config;
    }

    // ─── Initialisation ───────────────────────────────────────────────────────────

    @PostConstruct
    void init() {
        // Load whitelist from DB
        whitelistRepo.findAll().forEach(u -> whitelistedUsers.add(u.getUsername()));

        // Load from ENV (WHITELISTED=user1;user2;...)
        String envList = config.getWhitelistedEnv();
        if (envList != null && !envList.isBlank()) {
            Arrays.stream(envList.split(";"))
                    .map(String::trim)
                    .filter(s -> !s.isBlank())
                    .forEach(whitelistedUsers::add);
        }

        // Load stat counters
        statRepo.findAll().forEach(s -> downloadCounts.put(s.getContentType(), s.getCount()));

        log.info("StorageService initialised: {} whitelisted users, counts={}", whitelistedUsers.size(), downloadCounts);
    }

    // ─── Whitelist ────────────────────────────────────────────────────────────────

    public boolean isWhitelistEnabled() {
        return config.isWhitelistEnabled() || !whitelistedUsers.isEmpty();
    }

    public boolean isWhitelisted(String username) {
        return username != null && whitelistedUsers.contains(username);
    }

    public Set<String> getWhitelistedUsers() {
        return Collections.unmodifiableSet(whitelistedUsers);
    }

    @Transactional
    public boolean addToWhitelist(String username) {
        if (whitelistedUsers.contains(username)) return false;
        whitelistedUsers.add(username);
        if (!whitelistRepo.existsByUsername(username)) {
            whitelistRepo.save(new WhitelistedUser(username));
        }
        return true;
    }

    @Transactional
    public boolean removeFromWhitelist(String username) {
        if (!whitelistedUsers.contains(username)) return false;
        whitelistedUsers.remove(username);
        whitelistRepo.deleteById(username);
        return true;
    }

    // ─── Downloads ────────────────────────────────────────────────────────────────

    @Transactional
    public void addDownload(String contentType, Long userId, String username,
                            String platform, String url, String title) {
        // Increment in-memory counter
        downloadCounts.merge(contentType, 1L, Long::sum);

        // Upsert DB counter
        DownloadStat stat = statRepo.findById(contentType).orElse(new DownloadStat(contentType));
        stat.increment();
        statRepo.save(stat);

        // Record history
        if (userId != null) {
            DownloadHistory history = new DownloadHistory();
            history.setUserId(userId);
            history.setUsername(username);
            history.setPlatform(platform);
            history.setContentType(contentType);
            history.setUrl(url);
            history.setTitle(title);
            historyRepo.save(history);
        }
    }

    // ─── Active users ─────────────────────────────────────────────────────────────

    @Transactional
    public void addActiveUser(Long userId) {
        if (userId == null) return;
        String today = LocalDate.now().toString();
        if (!activeUserRepo.existsByUserIdAndDate(userId, today)) {
            activeUserRepo.save(new ActiveUser(userId, today));
        }
    }

    // ─── Statistics ───────────────────────────────────────────────────────────────

    /**
     * Returns weekly statistics (last 7 days), matching the Python
     * {@code Stats.get_weekly_stats()} return value.
     */
    public WeeklyStats getWeeklyStats() {
        String weekAgo = LocalDate.now().minusDays(7).toString();
        List<Long> activeUserIds = activeUserRepo.findDistinctUserIdsSince(weekAgo);

        long videoCount = downloadCounts.getOrDefault("Video", 0L);
        long audioCount = downloadCounts.getOrDefault("Music", 0L);

        return new WeeklyStats(videoCount, audioCount, activeUserIds.size(), new HashSet<>(activeUserIds));
    }

    public record WeeklyStats(long videoCount, long audioCount, long activeUsersCount, Set<Long> activeUsers) {}

    // ─── User lookup ──────────────────────────────────────────────────────────────

    public String getUsernameById(Long userId) {
        return historyRepo.findFirstByUserIdOrderByTimestampDesc(userId)
                .map(DownloadHistory::getUsername)
                .orElse(null);
    }

    public List<Long> getAllUserIds() {
        return historyRepo.findDistinctUserIds();
    }
}
