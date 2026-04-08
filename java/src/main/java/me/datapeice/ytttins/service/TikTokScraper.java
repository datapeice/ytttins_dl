package me.datapeice.ytttins.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import me.datapeice.ytttins.config.BotConfig;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;

/**
 * TikTok metadata scraper using the <a href="https://www.tikwm.com/api/">TikWM API</a>.
 *
 * <p>Equivalent to {@code services/tiktok_scraper.py} in the Python version.
 *
 * <h3>Provided methods</h3>
 * <ul>
 *   <li>{@link #fetchMetadata(String)} – returns uploader, verified status, title, duration</li>
 *   <li>{@link #downloadViaTikWm(String)} – last-resort TikTok download via TikWM</li>
 *   <li>{@link #downloadImages(String)} – downloads slideshow images from TikTok</li>
 * </ul>
 */
@Service
public class TikTokScraper {

    private static final Logger log = LoggerFactory.getLogger(TikTokScraper.class);
    private static final String TIKWM_API = "https://www.tikwm.com/api/";

    private final BotConfig config;
    private final OkHttpClient http;
    private final ObjectMapper mapper = new ObjectMapper();

    public TikTokScraper(BotConfig config) {
        this.config = config;
        this.http = new OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(60, TimeUnit.SECONDS)
                .followRedirects(true)
                .build();
    }

    // ─── Metadata ─────────────────────────────────────────────────────────────────

    /**
     * Fetches TikTok video metadata via TikWM API.
     * Returns a map with keys: {@code uploader}, {@code verified}, {@code title}, {@code duration}.
     */
    public Map<String, String> fetchMetadata(String url) {
        Map<String, String> result = new HashMap<>();
        result.put("uploader", "Unknown");
        result.put("verified", "false");
        result.put("title", "");
        result.put("duration", "0");

        try {
            String apiUrl = TIKWM_API + "?url=" + java.net.URLEncoder.encode(url, "UTF-8") + "&count=12&cursor=0&web=1&hd=1";
            Request req = new Request.Builder().url(apiUrl)
                    .header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
                    .build();

            try (Response resp = http.newCall(req).execute()) {
                if (!resp.isSuccessful() || resp.body() == null) {
                    log.warn("TikWM API returned {}", resp.code());
                    return result;
                }
                JsonNode root = mapper.readTree(resp.body().string());
                JsonNode data = root.path("data");
                if (data.isMissingNode()) {
                    log.warn("TikWM: no data field in response");
                    return result;
                }

                // Uploader
                JsonNode authorNode = data.path("author");
                String nickname = authorNode.path("nickname").asText(null);
                String uniqueId = authorNode.path("unique_id").asText(null);
                if (nickname != null && !nickname.isBlank()) {
                    result.put("uploader", nickname);
                } else if (uniqueId != null && !uniqueId.isBlank()) {
                    result.put("uploader", uniqueId);
                }

                // Verified
                boolean verified = authorNode.path("verified").asBoolean(false);
                result.put("verified", String.valueOf(verified));

                // Title
                String title = data.path("title").asText(data.path("desc").asText(""));
                if (!title.isBlank()) result.put("title", title);

                // Duration
                int duration = data.path("duration").asInt(0);
                result.put("duration", String.valueOf(duration));

                log.debug("TikWM metadata: uploader={} verified={} title={}", result.get("uploader"), verified, title);
            }
        } catch (Exception e) {
            log.warn("TikWM metadata fetch failed: {}", e.getMessage());
        }

        return result;
    }

    // ─── Last-resort TikTok download ──────────────────────────────────────────────

    /**
     * Downloads a TikTok video via TikWM as a last resort.
     * Mirrors {@code download_tikwm()} in Python.
     */
    public DownloaderService.DownloadResult downloadViaTikWm(String url) throws Exception {
        log.info("[TIKWM] Downloading: {}", url);

        String apiUrl = TIKWM_API + "?url=" + java.net.URLEncoder.encode(url, "UTF-8") + "&count=12&cursor=0&web=1&hd=1";
        Request req = new Request.Builder().url(apiUrl)
                .header("User-Agent", "Mozilla/5.0")
                .build();

        String hdPlay;
        Map<String, String> meta;

        try (Response resp = http.newCall(req).execute()) {
            if (!resp.isSuccessful() || resp.body() == null) {
                throw new IOException("TikWM API returned " + resp.code());
            }
            JsonNode root = mapper.readTree(resp.body().string());
            JsonNode data = root.path("data");
            if (data.isMissingNode()) throw new IOException("TikWM: no data field");

            // Prefer HD download URL
            hdPlay = data.path("hdplay").asText(data.path("play").asText(null));
            if (hdPlay == null || hdPlay.isBlank()) throw new IOException("TikWM: no download URL");

            meta = extractMeta(data, url);
        }

        // Download the file
        Path filePath = config.getDownloadsDir().resolve("tikwm_" + UUID.randomUUID().toString().substring(0, 8) + ".mp4");
        downloadBinaryFile(hdPlay, filePath);

        return new DownloaderService.DownloadResult(filePath, null, meta);
    }

    // ─── Slideshow images ─────────────────────────────────────────────────────────

    /**
     * Downloads TikTok slideshow images from TikWM.
     * Mirrors {@code download_tiktok_images()} in Python.
     */
    public List<Path> downloadImages(String url) throws Exception {
        log.info("[TIKWM] Downloading slideshow images for: {}", url);

        String apiUrl = TIKWM_API + "?url=" + java.net.URLEncoder.encode(url, "UTF-8") + "&count=12&cursor=0&web=1&hd=1";
        Request req = new Request.Builder().url(apiUrl)
                .header("User-Agent", "Mozilla/5.0")
                .build();

        List<String> imageUrls = new ArrayList<>();

        try (Response resp = http.newCall(req).execute()) {
            if (!resp.isSuccessful() || resp.body() == null) {
                throw new IOException("TikWM API returned " + resp.code());
            }
            JsonNode root = mapper.readTree(resp.body().string());
            JsonNode data = root.path("data");
            JsonNode images = data.path("images");
            if (images.isArray()) {
                for (JsonNode img : images) {
                    String imgUrl = img.asText(null);
                    if (imgUrl != null && !imgUrl.isBlank()) imageUrls.add(imgUrl);
                }
            }
        }

        if (imageUrls.isEmpty()) throw new IOException("No images found in TikWM response");

        List<Path> paths = new ArrayList<>();
        for (int i = 0; i < imageUrls.size(); i++) {
            Path imgPath = config.getDownloadsDir().resolve("slide_" + i + "_" + UUID.randomUUID().toString().substring(0, 6) + ".jpg");
            downloadBinaryFile(imageUrls.get(i), imgPath);
            paths.add(imgPath);
        }
        return paths;
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────────

    private void downloadBinaryFile(String url, Path dest) throws IOException {
        Request req = new Request.Builder().url(url)
                .header("User-Agent", "Mozilla/5.0")
                .build();
        try (Response resp = http.newCall(req).execute()) {
            if (!resp.isSuccessful() || resp.body() == null) {
                throw new IOException("HTTP " + resp.code() + " downloading " + url);
            }
            try (InputStream in = resp.body().byteStream();
                 OutputStream out = Files.newOutputStream(dest)) {
                in.transferTo(out);
            }
        }
        if (Files.size(dest) == 0) {
            Files.deleteIfExists(dest);
            throw new IOException("Downloaded file is empty: " + dest);
        }
    }

    private Map<String, String> extractMeta(JsonNode data, String originalUrl) {
        Map<String, String> meta = new HashMap<>();

        JsonNode author = data.path("author");
        String nickname = author.path("nickname").asText(author.path("unique_id").asText("Unknown"));
        meta.put("uploader", nickname.isBlank() ? "Unknown" : nickname);
        meta.put("verified", String.valueOf(author.path("verified").asBoolean(false)));

        String title = data.path("title").asText(data.path("desc").asText("TikTok Video"));
        meta.put("title", title.isBlank() ? "TikTok Video" : title);
        meta.put("duration", String.valueOf(data.path("duration").asInt(0)));
        meta.put("webpage_url", originalUrl);

        return meta;
    }
}
