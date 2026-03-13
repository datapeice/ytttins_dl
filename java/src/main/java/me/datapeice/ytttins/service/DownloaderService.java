package me.datapeice.ytttins.service;

import me.datapeice.ytttins.config.BotConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import jakarta.annotation.PostConstruct;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.Consumer;

/**
 * Core media download service — triple-fallback architecture matching
 * {@code services/downloader.py} in the Python version.
 *
 * <h3>Download order</h3>
 * <ol>
 *   <li>yt-dlp (primary, via {@link ProcessBuilder})</li>
 *   <li>yt-dlp + SOCKS5 proxy (if {@code proxy.socks} is configured)</li>
 *   <li>Cobalt API (if {@code cobalt.enabled=true})</li>
 *   <li>TikWM (TikTok only, last resort)</li>
 * </ol>
 *
 * <p>Special cases:
 * <ul>
 *   <li>Instagram → try Cobalt first (photos-only post)</li>
 *   <li>TikTok → dedicated method with photo-slideshow support</li>
 *   <li>Reddit short URLs → resolved to full URL before download</li>
 * </ul>
 */
@Service
public class DownloaderService {

    private static final Logger log = LoggerFactory.getLogger(DownloaderService.class);

    // ─── User-Agent pool ──────────────────────────────────────────────────────────
    private static final List<String> USER_AGENTS = List.of(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0"
    );

    // ─── Funny statuses (same as Python) ─────────────────────────────────────────
    private static final List<String> FUNNY_STATUSES = List.of(
            "💻 Hacking the Pentagon...",
            "🛡️ Fending off the FBI...",
            "🍕 Ordering pizza for the server's rats...",
            "🐈 Petting the server cat...",
            "🔥 Warming up the GPU...",
            "👀 Watching the video with the whole server...",
            "🚀 Preparing for takeoff...",
            "🧹 Sweeping up bits...",
            "🤔 Thinking about the meaning of life...",
            "📦 Packing pixels...",
            "📡 Searching for Elon Musk's satellites...",
            "🔌 Plugging the cable in deeper...",
            "☕ Drinking coffee, waiting for download...",
            "🔨 Fixing what isn't broken...",
            "🦖 Running away from dinosaurs...",
            "💿 Wiping the disk with alcohol...",
            "👾 Negotiating with reptilians...",
            "🇵🇱 Searching for Polish alt girls...",
            "🛃 Deporting migrants...",
            "🙏 Praying the server survives...",
            "📜 Signing a contract with Crowley..."
    );

    private static final Random RNG = new Random();

    private final BotConfig config;
    private final CobaltClient cobaltClient;
    private final TikTokScraper tikTokScraper;

    public DownloaderService(BotConfig config, CobaltClient cobaltClient, TikTokScraper tikTokScraper) {
        this.config = config;
        this.cobaltClient = cobaltClient;
        this.tikTokScraper = tikTokScraper;
    }

    // ─── Result DTO ───────────────────────────────────────────────────────────────

    /**
     * Download result — mirrors the Python {@code (file_path, thumb_path, metadata)} tuple.
     */
    public static class DownloadResult {
        private final List<Path> files;
        private final Path thumbnail;
        private final Map<String, String> metadata;

        public DownloadResult(Path singleFile, Path thumbnail, Map<String, String> metadata) {
            this.files = List.of(singleFile);
            this.thumbnail = thumbnail;
            this.metadata = Collections.unmodifiableMap(metadata);
        }

        public DownloadResult(List<Path> files, Path thumbnail, Map<String, String> metadata) {
            this.files = Collections.unmodifiableList(files);
            this.thumbnail = thumbnail;
            this.metadata = Collections.unmodifiableMap(metadata);
        }

        public boolean isMultiFile() {
            return files.size() > 1;
        }

        public Path getSingleFile() {
            return files.isEmpty() ? null : files.get(0);
        }

        public List<Path> getFiles() {
            return files;
        }

        public Path getThumbnail() {
            return thumbnail;
        }

        public Map<String, String> getMetadata() {
            return metadata;
        }
    }

    // ─── Platform detection ───────────────────────────────────────────────────────

    /** Detects the platform from a URL — mirrors Python {@code get_platform()}. */
    public String getPlatform(String url) {
        String u = url.toLowerCase();
        if (u.contains("youtube.com") || u.contains("youtu.be")) return "youtube";
        if (u.contains("tiktok.com")) return "tiktok";
        if (u.contains("instagram.com")) return "instagram";
        if (u.contains("reddit.com") || u.contains("redd.it")) return "reddit";
        if (u.contains("twitter.com") || u.contains("x.com") || u.contains("t.co")) return "twitter";
        if (u.contains("facebook.com") || u.contains("fb.watch") || u.contains("fb.com")) return "facebook";
        if (u.contains("vimeo.com")) return "vimeo";
        if (u.contains("twitch.tv")) return "twitch";
        if (u.contains("pinterest.com") || u.contains("pin.it")) return "pinterest";
        if (u.contains("vk.com") || u.contains("vk.ru")) return "vk";
        if (u.contains("dailymotion.com") || u.contains("dai.ly")) return "dailymotion";
        if (u.startsWith("https://") || u.startsWith("http://")) return "video";
        return "unknown";
    }

    public boolean isYoutubeMusic(String url) {
        return url.toLowerCase().contains("music.youtube.com");
    }

    // ─── Main download orchestrator ───────────────────────────────────────────────

    /**
     * Downloads media using the triple-fallback strategy.
     *
     * @param url              source URL
     * @param isMusic          {@code true} to extract audio (MP3)
     * @param videoHeight      desired video height (null = best quality)
     * @param progressCallback called with status strings during download (may be null)
     */
    public DownloadResult downloadMedia(
            String url,
            boolean isMusic,
            Integer videoHeight,
            Consumer<String> progressCallback) throws Exception {

        // Resolve TikTok short URLs
        if (url.contains("vm.tiktok.com") || url.contains("vt.tiktok.com") || url.contains("/t/")) {
            url = resolveRedirect(url);
        }

        // Resolve Reddit short URLs
        if (url.contains("reddit.com") && url.contains("/s/")) {
            url = unshortenRedditUrl(url);
        }

        String platform = getPlatform(url);

        // Strip query params (except YouTube and Instagram)
        if (url.contains("?") && !platform.equals("youtube") && !platform.equals("instagram")) {
            url = url.split("\\?")[0];
        }

        // Show funny status
        if (progressCallback != null) {
            progressCallback.accept("🎬 " + FUNNY_STATUSES.get(RNG.nextInt(FUNNY_STATUSES.size())));
        }

        // ── Instagram: try Cobalt first ──────────────────────────────────────────
        if ("instagram".equals(platform) && config.isCobaltEnabled()) {
            try {
                log.info("[COBALT] Instagram-first attempt: {}", url);
                return cobaltClient.downloadMedia(url, "1080", isMusic, progressCallback);
            } catch (Exception e) {
                log.warn("[COBALT] Instagram-first failed: {}", e.getMessage());
            }
        }

        // ── METHOD 1: yt-dlp ─────────────────────────────────────────────────────
        String ytdlpError = null;
        try {
            log.info("[YT-DLP] Attempting: {}", url);
            if ("tiktok".equals(platform)) {
                return downloadTikTok(url, false);
            }
            return downloadWithYtDlp(url, isMusic, videoHeight, false);
        } catch (Exception e) {
            ytdlpError = e.getMessage();
            log.warn("[YT-DLP] Failed: {}", ytdlpError);
        }

        // ── METHOD 1.5: yt-dlp + proxy ───────────────────────────────────────────
        if (config.getSocksProxy() != null && !config.getSocksProxy().isBlank()) {
            try {
                log.info("[YT-DLP+PROXY] Attempting with SOCKS proxy");
                if ("tiktok".equals(platform)) {
                    return downloadTikTok(url, true);
                }
                return downloadWithYtDlp(url, isMusic, videoHeight, true);
            } catch (Exception e) {
                log.warn("[YT-DLP+PROXY] Failed: {}", e.getMessage());
            }
        }

        // ── METHOD 2: Cobalt API ──────────────────────────────────────────────────
        if (config.isCobaltEnabled()) {
            try {
                log.info("[COBALT] Attempting: {}", url);
                return cobaltClient.downloadMedia(url, "1080", isMusic, progressCallback);
            } catch (Exception e) {
                log.warn("[COBALT] Failed: {}", e.getMessage());
            }
        }

        // ── METHOD 3: TikWM (TikTok only) ────────────────────────────────────────
        if ("tiktok".equals(platform)) {
            try {
                log.info("[TIKWM] Attempting TikTok download via TikWM...");
                return tikTokScraper.downloadViaTikWm(url);
            } catch (Exception e) {
                log.error("[TIKWM] Failed: {}", e.getMessage());
            }
        }

        throw new RuntimeException("All download methods failed. YT-DLP error: " + ytdlpError);
    }

    // ─── yt-dlp download ──────────────────────────────────────────────────────────

    /**
     * Downloads via yt-dlp command-line, retrying with different User-Agents on 403.
     * Mirrors {@code _download_local_ytdlp()} in Python.
     */
    private DownloadResult downloadWithYtDlp(
            String url, boolean isMusic, Integer videoHeight, boolean useProxy) throws Exception {

        String uniqueId = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        Path outputDir = config.getDownloadsDir();
        String outputTemplate = outputDir + "/%(title)s_%(id)s_" + uniqueId + ".%(ext)s";
        Path cookieFile = config.getDataDir().resolve("cookies.txt");

        Exception lastError = null;

        for (int attempt = 0; attempt < USER_AGENTS.size(); attempt++) {
            String userAgent = USER_AGENTS.get(attempt);
            try {
                List<String> cmd = buildYtDlpCommand(url, outputTemplate, cookieFile,
                        userAgent, isMusic, videoHeight, useProxy);

                log.debug("[YT-DLP] Command (attempt {}): {}", attempt + 1, String.join(" ", cmd));
                ProcessBuilder pb = new ProcessBuilder(cmd);
                pb.redirectErrorStream(true);

                Process process = pb.start();
                String output = new String(process.getInputStream().readAllBytes());
                int exitCode = process.waitFor();

                if (exitCode != 0) {
                    String err = output;
                    if (err.contains("403") || err.contains("Blocked") || err.contains("Forbidden")) {
                        log.warn("[YT-DLP] 403 on attempt {}/{}, retrying...", attempt + 1, USER_AGENTS.size());
                        lastError = new RuntimeException("HTTP 403: " + err.substring(0, Math.min(200, err.length())));
                        continue;
                    }
                    throw new RuntimeException("yt-dlp exited with code " + exitCode + ": "
                            + err.substring(0, Math.min(300, err.length())));
                }

                // Find downloaded file(s)
                List<Path> downloaded = findDownloadedFiles(outputDir, uniqueId);
                if (downloaded.isEmpty()) {
                    throw new RuntimeException("Download completed but file not found (id=" + uniqueId + ")");
                }

                // For Instagram playlists, return all files
                if (url.contains("instagram.com") && downloaded.size() > 1) {
                    return new DownloadResult(downloaded, null, defaultMetadata(url));
                }

                Path best = selectBestFile(downloaded);
                cleanupExtra(downloaded, best);

                Map<String, String> meta = defaultMetadata(url);
                return new DownloadResult(best, null, meta);

            } catch (RuntimeException e) {
                if (e.getMessage() != null && (e.getMessage().contains("403")
                        || e.getMessage().contains("Blocked")
                        || e.getMessage().contains("Forbidden"))) {
                    lastError = e;
                } else {
                    throw e;
                }
            }
        }

        throw lastError != null ? lastError : new RuntimeException("All user-agent attempts failed");
    }

    /**
     * TikTok-specific download with slideshow detection.
     * Mirrors {@code _download_local_tiktok()} in Python.
     */
    private DownloadResult downloadTikTok(String url, boolean useProxy) throws Exception {
        boolean isSlideshow = url.contains("/photo/");
        String uniqueId = UUID.randomUUID().toString().replace("-", "").substring(0, 8);
        Path outputDir = config.getDownloadsDir();
        String outputTemplate = outputDir + "/%(title)s_%(id)s_" + uniqueId + ".%(ext)s";
        Path cookieFile = config.getDataDir().resolve("cookies.txt");

        List<String> cmd = new ArrayList<>();
        cmd.add("yt-dlp");
        cmd.add("--no-playlist");
        cmd.add("-o"); cmd.add(outputTemplate);
        cmd.add("--user-agent"); cmd.add(USER_AGENTS.get(RNG.nextInt(USER_AGENTS.size())));

        if (Files.exists(cookieFile) && Files.size(cookieFile) > 0) {
            cmd.add("--cookies"); cmd.add(cookieFile.toString());
        }

        if (!isSlideshow) {
            cmd.add("-f"); cmd.add("bestvideo[ext=mp4][vcodec^=h264]+bestaudio/best[ext=mp4]/best");
            cmd.add("--merge-output-format"); cmd.add("mp4");
        }

        if (useProxy && config.getSocksProxy() != null) {
            cmd.add("--proxy"); cmd.add(config.getSocksProxy());
        }

        cmd.add(url);

        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.redirectErrorStream(true);
        Process process = pb.start();
        String output = new String(process.getInputStream().readAllBytes());
        int exitCode = process.waitFor();

        if (exitCode != 0) {
            throw new RuntimeException("TikTok yt-dlp failed: " + output.substring(0, Math.min(300, output.length())));
        }

        List<Path> downloaded = findDownloadedFiles(outputDir, uniqueId);
        if (downloaded.isEmpty()) throw new RuntimeException("TikTok file not found after download");

        if (isSlideshow || downloaded.size() > 1) {
            Map<String, String> meta = tikTokScraper.fetchMetadata(url);
            return new DownloadResult(downloaded, null, meta);
        }

        Path best = selectBestFile(downloaded);
        cleanupExtra(downloaded, best);
        Map<String, String> meta = tikTokScraper.fetchMetadata(url);
        return new DownloadResult(best, null, meta);
    }

    // ─── yt-dlp command builder ───────────────────────────────────────────────────

    private List<String> buildYtDlpCommand(
            String url, String outputTemplate, Path cookieFile,
            String userAgent, boolean isMusic, Integer videoHeight, boolean useProxy) {

        List<String> cmd = new ArrayList<>();
        cmd.add("yt-dlp");
        cmd.add("--no-playlist");
        cmd.add("-o"); cmd.add(outputTemplate);
        cmd.add("--user-agent"); cmd.add(userAgent);
        cmd.add("--legacy-server-connect");

        if (Files.exists(cookieFile) && cookieFile.toFile().length() > 0) {
            cmd.add("--cookies"); cmd.add(cookieFile.toString());
        }

        if (isMusic) {
            cmd.add("-f"); cmd.add("bestaudio/best");
            cmd.add("-x");
            cmd.add("--audio-format"); cmd.add("mp3");
            cmd.add("--audio-quality"); cmd.add("0");
        } else if (videoHeight != null) {
            cmd.add("-f"); cmd.add("best[height=" + videoHeight + "]/best[height<=" + videoHeight + "]/best");
        } else {
            cmd.add("-f"); cmd.add("best[vcodec^=h264]/best[vcodec^=avc]/best");
        }

        if (useProxy && config.getSocksProxy() != null && !config.getSocksProxy().isBlank()) {
            cmd.add("--proxy"); cmd.add(config.getSocksProxy());
        }

        if (url.contains("reddit.com") || url.contains("redd.it")) {
            cmd.add("--extractor-args"); cmd.add("reddit:user_agent=" + userAgent);
        }

        cmd.add(url);
        return cmd;
    }

    // ─── File helpers ─────────────────────────────────────────────────────────────

    private List<Path> findDownloadedFiles(Path dir, String uniqueId) throws IOException {
        try (var stream = Files.list(dir)) {
            return stream
                    .filter(p -> p.getFileName().toString().contains(uniqueId))
                    .toList();
        }
    }

    private static final Set<String> VIDEO_EXTENSIONS =
            Set.of(".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi", ".flv", ".ts");

    private Path selectBestFile(List<Path> files) {
        // Prefer video files over others, then pick the largest
        List<Path> videoFiles = files.stream()
                .filter(p -> VIDEO_EXTENSIONS.contains(getExtension(p)))
                .toList();
        List<Path> candidates = videoFiles.isEmpty() ? files : videoFiles;
        return candidates.stream()
                .max(Comparator.comparingLong(p -> p.toFile().length()))
                .orElse(files.get(0));
    }

    private void cleanupExtra(List<Path> all, Path keep) {
        for (Path p : all) {
            if (!p.equals(keep)) {
                try { Files.deleteIfExists(p); } catch (IOException ignored) {}
            }
        }
    }

    private String getExtension(Path p) {
        String name = p.getFileName().toString();
        int idx = name.lastIndexOf('.');
        return idx >= 0 ? name.substring(idx).toLowerCase() : "";
    }

    // ─── Metadata helpers ─────────────────────────────────────────────────────────

    private Map<String, String> defaultMetadata(String url) {
        Map<String, String> meta = new HashMap<>();
        meta.put("title", "Media");
        meta.put("uploader", "Unknown");
        meta.put("webpage_url", url);
        meta.put("duration", "0");
        meta.put("verified", "false");
        return meta;
    }

    // ─── URL resolvers ────────────────────────────────────────────────────────────

    private String resolveRedirect(String url) {
        try {
            java.net.HttpURLConnection conn = (java.net.HttpURLConnection)
                    new java.net.URL(url).openConnection();
            conn.setInstanceFollowRedirects(true);
            conn.setRequestMethod("HEAD");
            conn.setConnectTimeout(5000);
            conn.setReadTimeout(5000);
            conn.getResponseCode();
            return conn.getURL().toString();
        } catch (Exception e) {
            log.warn("Failed to resolve redirect for {}: {}", url, e.getMessage());
            return url;
        }
    }

    private String unshortenRedditUrl(String url) {
        if (url.contains("/comments/")) return url;
        return resolveRedirect(url);
    }

    // ─── Cookie loading ───────────────────────────────────────────────────────────

    @PostConstruct
    void initCookies() {
        String content = config.getCookiesContent();
        if (content != null && !content.isBlank()) {
            Path cookiePath = config.getDataDir().resolve("cookies.txt");
            try {
                Files.writeString(cookiePath, content);
                log.info("Cookies written from environment variable");
            } catch (IOException e) {
                log.error("Failed to write cookies from env: {}", e.getMessage());
            }
        }
    }
}
