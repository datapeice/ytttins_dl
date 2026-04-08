package me.datapeice.ytttins.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import me.datapeice.ytttins.config.BotConfig;
import okhttp3.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.*;
import java.net.URI;
import java.nio.file.*;
import java.util.*;
import java.util.concurrent.TimeUnit;
import java.util.function.Consumer;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * HTTP client for the <a href="https://github.com/imputnet/cobalt">Cobalt API</a>.
 *
 * <p>Equivalent to {@code services/cobalt_client.py} in the Python version.
 *
 * <h3>Cobalt API response types handled</h3>
 * <ul>
 *   <li>{@code redirect} – direct CDN link</li>
 *   <li>{@code tunnel}   – proxied through Cobalt's /tunnel endpoint</li>
 *   <li>{@code picker}   – multiple files (e.g. TikTok slideshow)</li>
 *   <li>{@code error}    – Cobalt returned an error</li>
 * </ul>
 */
@Service
public class CobaltClient {

    private static final Logger log = LoggerFactory.getLogger(CobaltClient.class);
    private static final MediaType JSON = MediaType.parse("application/json; charset=utf-8");

    private final BotConfig config;
    private final OkHttpClient http;
    private final ObjectMapper mapper = new ObjectMapper();

    public CobaltClient(BotConfig config) {
        this.config = config;
        this.http = new OkHttpClient.Builder()
                .connectTimeout(30, TimeUnit.SECONDS)
                .readTimeout(600, TimeUnit.SECONDS)    // 10 minutes for large files
                .writeTimeout(60, TimeUnit.SECONDS)
                .followRedirects(true)
                .build();
    }

    // ─── Public API ───────────────────────────────────────────────────────────────

    /**
     * Downloads media via the Cobalt API.
     *
     * @param url              source media URL
     * @param quality          requested quality ("max", "2160", "1440", "1080", etc.)
     * @param isAudio          {@code true} to download audio-only (MP3 @ 320 kbps)
     * @param progressCallback called with status updates; may be null
     * @return download result with file path(s) and metadata
     */
    public DownloaderService.DownloadResult downloadMedia(
            String url,
            String quality,
            boolean isAudio,
            Consumer<String> progressCallback) throws Exception {

        if (!config.isCobaltEnabled() || config.getCobaltApiUrl().isBlank()) {
            throw new IllegalStateException("Cobalt API is not configured");
        }

        log.info("Cobalt: downloading {} (quality={}, audio={})", url, quality, isAudio);

        Map<String, Object> requestBody = new LinkedHashMap<>();
        requestBody.put("url", url);
        requestBody.put("videoQuality", quality);
        requestBody.put("youtubeVideoCodec", "h264");
        requestBody.put("downloadMode", isAudio ? "audio" : "auto");
        requestBody.put("alwaysProxy", false);
        if (isAudio) {
            requestBody.put("audioFormat", "mp3");
            requestBody.put("audioBitrate", "320");
        }

        String cobaltBase = config.getCobaltApiUrl();
        while (cobaltBase.endsWith("/")) cobaltBase = cobaltBase.substring(0, cobaltBase.length() - 1);
        JsonNode response = postJson(cobaltBase + "/", requestBody);
        String status = response.path("status").asText();
        log.info("Cobalt response status: {}", status);

        return switch (status) {
            case "redirect", "tunnel" -> {
                String fileUrl = response.path("url").asText();
                yield downloadFile(fileUrl, response, progressCallback, url);
            }
            case "picker" -> handlePicker(response);
            case "error" -> {
                String code = response.path("error").path("code").asText("unknown");
                String msg = response.path("error").path("context").asText("Unknown error");
                throw new RuntimeException("Cobalt error: " + code + " – " + msg);
            }
            default -> throw new RuntimeException("Unknown Cobalt status: " + status);
        };
    }

    // ─── JSON request ─────────────────────────────────────────────────────────────

    private JsonNode postJson(String url, Map<String, Object> body) throws IOException {
        String json = mapper.writeValueAsString(body);
        Request.Builder builder = new Request.Builder()
                .url(url)
                .post(RequestBody.create(json, JSON))
                .header("Accept", "application/json")
                .header("Content-Type", "application/json");

        if (config.getCobaltApiKey() != null && !config.getCobaltApiKey().isBlank()) {
            builder.header("Authorization", "Api-Key " + config.getCobaltApiKey());
        }

        try (Response resp = http.newCall(builder.build()).execute()) {
            String responseBody = resp.body() != null ? resp.body().string() : "";
            if (!resp.isSuccessful()) {
                throw new IOException("Cobalt API error " + resp.code() + ": " + responseBody);
            }
            return mapper.readTree(responseBody);
        }
    }

    // ─── File download ────────────────────────────────────────────────────────────

    /**
     * Downloads a single file from a redirect/tunnel URL with progress updates.
     * Mirrors {@code _download_file()} in Python.
     */
    private DownloaderService.DownloadResult downloadFile(
            String fileUrl,
            JsonNode metadata,
            Consumer<String> progressCallback,
            String originalUrl) throws IOException {

        // Sanitise filename
        String rawFilename = metadata.path("filename").asText(
                "video_" + UUID.randomUUID().toString().substring(0, 8) + ".mp4");
        String filename = rawFilename.replaceAll("[^a-zA-Z0-9._\\- ]", "");
        Path filePath = config.getDownloadsDir().resolve(filename);

        log.info("Downloading file from Cobalt: {}", fileUrl);

        Request request = new Request.Builder().url(fileUrl).build();
        try (Response resp = http.newCall(request).execute()) {
            if (!resp.isSuccessful() || resp.body() == null) {
                throw new IOException("Cobalt download failed: HTTP " + resp.code());
            }
            try (InputStream in = resp.body().byteStream();
                 OutputStream out = Files.newOutputStream(filePath)) {
                byte[] buf = new byte[8192];
                int n;
                while ((n = in.read(buf)) != -1) out.write(buf, 0, n);
            }
        }

        if (!Files.exists(filePath) || Files.size(filePath) == 0) {
            throw new IOException("Downloaded file is empty or missing: " + filePath);
        }
        log.info("File downloaded: {} ({} bytes)", filePath, Files.size(filePath));

        // Build metadata
        String uploader = firstNonBlank(
                metadata.path("author").asText(null),
                metadata.path("uploader").asText(null),
                metadata.path("creator").asText(null)
        );
        if (uploader == null && originalUrl != null) {
            Matcher m = Pattern.compile("tiktok\\.com/@([^/?\\s]+)").matcher(originalUrl);
            if (m.find()) uploader = m.group(1);
        }
        uploader = uploader != null ? uploader : "Unknown";

        String title = metadata.path("title").asText(null);
        if (title == null) title = filename.replaceFirst("\\.[^.]+$", "");

        Map<String, String> meta = new HashMap<>();
        meta.put("title", title);
        meta.put("uploader", uploader);
        meta.put("webpage_url", originalUrl != null ? originalUrl : "");
        meta.put("duration", "0");
        meta.put("verified", "false");
        meta.put("codec", "h264");

        // Enrich TikTok metadata via TikWM
        return new DownloaderService.DownloadResult(filePath, null, meta);
    }

    // ─── Picker (multi-file) ──────────────────────────────────────────────────────

    /**
     * Handles Cobalt picker response (e.g. TikTok slideshow).
     * Mirrors {@code _handle_picker()} in Python.
     */
    private DownloaderService.DownloadResult handlePicker(JsonNode response) throws IOException {
        log.info("Cobalt returned picker (multiple files)");

        JsonNode pickerItems = response.path("picker");
        if (!pickerItems.isArray() || pickerItems.isEmpty()) {
            throw new IOException("Cobalt picker response is empty");
        }

        List<Path> filePaths = new ArrayList<>();
        for (int i = 0; i < pickerItems.size(); i++) {
            JsonNode item = pickerItems.get(i);
            String itemUrl = item.path("url").asText(null);
            if (itemUrl == null) continue;

            String mime = item.path("mime").asText(item.path("type").asText(null));
            String ext = guessExtension(itemUrl, mime);
            String filename = "picker_" + i + ext;

            try {
                DownloaderService.DownloadResult r = downloadFile(
                        itemUrl,
                        mapper.createObjectNode().put("filename", filename),
                        null,
                        null);
                filePaths.add(r.getSingleFile());
            } catch (Exception e) {
                log.error("Failed to download picker item {}: {}", i, e.getMessage());
            }
        }

        if (filePaths.isEmpty()) throw new IOException("All picker items failed to download");

        String title = response.path("title").asText("Carousel Media");
        String uploader = firstNonBlank(
                response.path("author").asText(null),
                response.path("uploader").asText(null),
                response.path("creator").asText(null));

        Map<String, String> meta = new HashMap<>();
        meta.put("title", title);
        meta.put("uploader", uploader != null ? uploader : "Unknown");
        meta.put("webpage_url", response.path("url").asText(""));
        meta.put("count", String.valueOf(filePaths.size()));

        return new DownloaderService.DownloadResult(filePaths, null, meta);
    }

    // ─── Helpers ──────────────────────────────────────────────────────────────────

    private String guessExtension(String url, String mime) {
        if (url != null) {
            try {
                String path = new URI(url).getPath();
                int dot = path.lastIndexOf('.');
                if (dot >= 0) {
                    String ext = path.substring(dot).toLowerCase();
                    if (!ext.isBlank()) return ext;
                }
            } catch (Exception ignored) {}
        }
        if (mime != null) {
            String m = mime.toLowerCase();
            if (m.contains("jpeg")) return ".jpg";
            if (m.contains("png")) return ".png";
            if (m.contains("webp")) return ".webp";
            if (m.contains("mp4")) return ".mp4";
            if (m.contains("mp3")) return ".mp3";
            if (m.contains("m4a")) return ".m4a";
        }
        return ".bin";
    }

    private String firstNonBlank(String... values) {
        for (String v : values) {
            if (v != null && !v.isBlank()) return v;
        }
        return null;
    }
}
