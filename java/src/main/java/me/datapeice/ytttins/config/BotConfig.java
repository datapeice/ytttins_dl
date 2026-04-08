package me.datapeice.ytttins.config;

import io.github.cdimascio.dotenv.Dotenv;
import io.github.cdimascio.dotenv.DotenvException;
import lombok.Getter;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import jakarta.annotation.PostConstruct;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Central configuration bean.
 *
 * <p>Values are resolved in the following priority order (highest first):
 * <ol>
 *   <li>JVM system properties / OS environment variables</li>
 *   <li>Spring {@code application.yml} / {@code application.properties}</li>
 *   <li>{@code .env} file in the working directory (dev convenience)</li>
 * </ol>
 *
 * <p>Equivalent to {@code config.py} in the Python version.
 */
@Getter
@Configuration
public class BotConfig {

    private static final Logger log = LoggerFactory.getLogger(BotConfig.class);

    // ─── Required ────────────────────────────────────────────────────────────────

    @Value("${bot.token}")
    private String botToken;

    @Value("${bot.admin-username:}")
    private String adminUsername;

    // ─── Webhook ─────────────────────────────────────────────────────────────────

    /** External URL that Telegram calls (e.g. https://bot.example.com).  Empty → polling mode. */
    @Value("${bot.webhook-host:}")
    private String webhookHost;

    /**
     * Internal URL that the local Telegram Bot API server uses to reach the bot
     * inside a Docker network (e.g. http://bot-container:8443).
     */
    @Value("${bot.webhook-internal-host:}")
    private String webhookInternalHost;

    @Value("${server.port:8443}")
    private int webappPort;

    // ─── Local Telegram Bot API ───────────────────────────────────────────────────

    @Value("${telegram.api-url:https://api.telegram.org}")
    private String telegramApiUrl;

    // ─── Cobalt API ───────────────────────────────────────────────────────────────

    @Value("${cobalt.enabled:false}")
    private boolean cobaltEnabled;

    @Value("${cobalt.api-url:}")
    private String cobaltApiUrl;

    @Value("${cobalt.api-key:}")
    private String cobaltApiKey;

    // ─── Proxy ────────────────────────────────────────────────────────────────────

    @Value("${proxy.socks:}")
    private String socksProxy;

    @Value("${proxy.http:}")
    private String httpProxy;

    // ─── Whitelist ────────────────────────────────────────────────────────────────

    /** Semicolon-separated initial whitelist loaded at startup (ENV: WHITELISTED). */
    @Value("${bot.whitelisted:}")
    private String whitelistedEnv;

    /** When true every user must be whitelisted; when false the bot is open. */
    public boolean isWhitelistEnabled() {
        return whitelistedEnv != null && !whitelistedEnv.isBlank();
    }

    // ─── Cookies ─────────────────────────────────────────────────────────────────

    /** Raw Netscape-format YouTube cookies injected via environment variable. */
    @Value("${bot.cookies-content:}")
    private String cookiesContent;

    // ─── Filesystem paths ─────────────────────────────────────────────────────────

    private Path baseDir;
    private Path downloadsDir;
    private Path dataDir;
    private Path logDir;

    @PostConstruct
    void initDirectories() throws IOException {
        baseDir = Paths.get(System.getProperty("user.dir"));
        downloadsDir = baseDir.resolve("downloads");
        dataDir = baseDir.resolve("data");
        logDir = baseDir.resolve("logs");

        Files.createDirectories(downloadsDir);
        Files.createDirectories(dataDir);
        Files.createDirectories(logDir);

        log.info("Directories initialised: downloads={} data={} logs={}", downloadsDir, dataDir, logDir);
    }

    // ─── dotenv support ──────────────────────────────────────────────────────────

    /**
     * Loads a {@code .env} file from the current working directory so that
     * developers can run the bot locally without setting OS environment variables.
     * The values are pushed into {@link System#setProperty} so that Spring's
     * {@code @Value} resolution picks them up automatically.
     */
    @Bean
    public static Dotenv dotenv() {
        try {
            Dotenv dotenv = Dotenv.configure().ignoreIfMissing().load();
            dotenv.entries().forEach(e -> {
                if (System.getenv(e.getKey()) == null) {
                    System.setProperty(e.getKey(), e.getValue());
                }
            });
            return dotenv;
        } catch (DotenvException e) {
            LoggerFactory.getLogger(BotConfig.class).warn(".env file not found or unreadable: {}", e.getMessage());
            return Dotenv.configure().ignoreIfMissing().load();
        }
    }
}
