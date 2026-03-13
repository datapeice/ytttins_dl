package me.datapeice.ytttins.handler;

import me.datapeice.ytttins.config.BotConfig;
import me.datapeice.ytttins.database.service.StorageService;
import me.datapeice.ytttins.service.DownloaderService;
import me.datapeice.ytttins.service.DownloaderService.DownloadResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.meta.api.methods.AnswerCallbackQuery;
import org.telegram.telegrambots.meta.api.methods.send.*;
import org.telegram.telegrambots.meta.api.methods.updatingmessages.EditMessageText;
import org.telegram.telegrambots.meta.api.objects.CallbackQuery;
import org.telegram.telegrambots.meta.api.objects.InputFile;
import org.telegram.telegrambots.meta.api.objects.Message;
import org.telegram.telegrambots.meta.api.objects.User;
import org.telegram.telegrambots.meta.api.objects.media.InputMediaPhoto;
import org.telegram.telegrambots.meta.api.objects.media.InputMediaVideo;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.InlineKeyboardButton;
import org.telegram.telegrambots.meta.bots.AbsSender;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;

import java.io.File;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

/**
 * Handles all incoming messages and callback queries from regular (non-admin) users.
 *
 * <p>Equivalent to {@code handlers/user.py} in the Python version.
 *
 * <h3>Flow</h3>
 * <ol>
 *   <li>{@code /start} → welcome message</li>
 *   <li>URL message → whitelist check → platform detection →
 *       (YouTube: format selection keyboard) → download → upload to Telegram</li>
 *   <li>Callback {@code format:audio:<id>} → download as MP3</li>
 *   <li>Callback {@code format:video:<id>} → quality selection keyboard</li>
 *   <li>Callback {@code dl_res:<id>:<height>} → download at given resolution</li>
 * </ol>
 */
@Component
public class UserHandler {

    private static final Logger log = LoggerFactory.getLogger(UserHandler.class);

    private static final Pattern URL_PATTERN =
            Pattern.compile("https?://[^\\s<>\"]+|www\\.[^\\s<>\"]+");

    /** In-memory URL cache keyed by short request ID (mirrors Python url_cache dict). */
    private final Map<String, String> urlCache = new ConcurrentHashMap<>();

    private final BotConfig config;
    private final DownloaderService downloader;
    private final StorageService storage;

    public UserHandler(BotConfig config, DownloaderService downloader, StorageService storage) {
        this.config = config;
        this.downloader = downloader;
        this.storage = storage;
    }

    // ─── Public entry points ─────────────────────────────────────────────────────

    public void handleMessage(AbsSender bot, Message message) {
        String text = message.getText();
        if (text == null) return;

        if (text.startsWith("/start")) {
            sendStart(bot, message);
            return;
        }

        if (!URL_PATTERN.matcher(text).find()) {
            sendText(bot, message.getChatId(), "Please send a valid URL.");
            return;
        }

        handleUrl(bot, message, text.trim());
    }

    public void handleCallback(AbsSender bot, CallbackQuery callback) {
        String data = callback.getData();
        if (data == null) return;

        answerCallback(bot, callback.getId());

        if (data.startsWith("format:")) {
            handleFormatSelection(bot, callback, data);
        } else if (data.startsWith("dl_res:")) {
            handleResolutionSelection(bot, callback, data);
        }
    }

    // ─── /start ──────────────────────────────────────────────────────────────────

    private void sendStart(AbsSender bot, Message message) {
        String text = """
                Hello! Send me a link to download video from:
                - YouTube / YouTube Music 🎵
                - TikTok
                - Instagram
                - Twitter/X
                - Reddit
                - Facebook
                - Vimeo
                - Twitch
                - Pinterest
                - VK / Dailymotion
                - And 1800+ other sites!

                Developed by @datapeice""";
        sendText(bot, message.getChatId(), text);
    }

    // ─── URL handling ─────────────────────────────────────────────────────────────

    private void handleUrl(AbsSender bot, Message message, String url) {
        // Whitelist check
        if (storage.isWhitelistEnabled()) {
            String username = message.getFrom().getUserName();
            if (username == null || !storage.isWhitelisted(username)) {
                sendText(bot, message.getChatId(), "⛔ Sorry, this bot is private. You are not in the whitelist.");
                return;
            }
        }

        String platform = downloader.getPlatform(url);
        if ("unknown".equals(platform)) {
            sendText(bot, message.getChatId(), "Sorry, this platform is not supported.");
            return;
        }

        // YouTube (non-music) → ask for format first
        if ("youtube".equals(platform) && !downloader.isYoutubeMusic(url)) {
            String requestId = UUID.randomUUID().toString().substring(0, 8);
            urlCache.put(requestId, url);

            InlineKeyboardMarkup keyboard = buildFormatKeyboard(requestId);
            sendWithKeyboard(bot, message.getChatId(), "Choose download format:", keyboard);
            return;
        }

        // All other platforms → download immediately
        Message statusMsg = sendTextAndGetMessage(bot, message.getChatId(), "⏳ Starting...");
        boolean isMusic = downloader.isYoutubeMusic(url);

        CompletableFuture.runAsync(() ->
                performDownloadAndUpload(bot, message, statusMsg, url, isMusic, null));
    }

    // ─── Callback: format selection ───────────────────────────────────────────────

    private void handleFormatSelection(AbsSender bot, CallbackQuery callback, String data) {
        // data = "format:<audio|video>:<requestId>"
        String[] parts = data.split(":", 3);
        if (parts.length < 3) return;

        String formatType = parts[1];
        String requestId = parts[2];
        String url = urlCache.get(requestId);
        if (url == null) {
            editMessageText(bot, callback.getMessage().getChatId(),
                    (int) callback.getMessage().getMessageId(),
                    "⚠️ Request expired. Please send the link again.");
            return;
        }

        if ("video".equals(formatType)) {
            // Show resolution keyboard
            InlineKeyboardMarkup keyboard = buildResolutionKeyboard(requestId);
            editMessageWithKeyboard(bot, callback.getMessage().getChatId(),
                    (int) callback.getMessage().getMessageId(),
                    "Select video quality:", keyboard);
            return;
        }

        // audio
        Message statusMsg = (Message) callback.getMessage();
        editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(), "⏳ Starting...");

        CompletableFuture.runAsync(() ->
                performDownloadAndUpload(bot, statusMsg, statusMsg, url, true, null));
    }

    // ─── Callback: resolution selection ──────────────────────────────────────────

    private void handleResolutionSelection(AbsSender bot, CallbackQuery callback, String data) {
        // data = "dl_res:<requestId>:<height>"
        String[] parts = data.split(":", 3);
        if (parts.length < 3) return;

        String requestId = parts[1];
        Integer height;
        try {
            height = Integer.parseInt(parts[2]);
        } catch (NumberFormatException e) {
            height = null;
        }

        String url = urlCache.get(requestId);
        if (url == null) {
            editMessageText(bot, callback.getMessage().getChatId(),
                    (int) callback.getMessage().getMessageId(),
                    "⚠️ Request expired. Please send the link again.");
            return;
        }

        Message statusMsg = (Message) callback.getMessage();
        editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(), "⏳ Starting...");

        final Integer finalHeight = height;
        CompletableFuture.runAsync(() ->
                performDownloadAndUpload(bot, statusMsg, statusMsg, url, false, finalHeight));
    }

    // ─── Core download + upload logic ─────────────────────────────────────────────

    /**
     * Downloads the URL and uploads the result to Telegram.
     *
     * @param originalMessage used to determine chat ID and user info for logging
     * @param statusMsg       the "⏳ Starting..." message that gets edited with progress
     */
    private void performDownloadAndUpload(
            AbsSender bot,
            Message originalMessage,
            Message statusMsg,
            String url,
            boolean isMusic,
            Integer videoHeight) {

        long chatId = originalMessage.getChatId();
        User from = originalMessage.getFrom();
        String platform = downloader.getPlatform(url);

        try {
            DownloadResult result = downloader.downloadMedia(
                    url, isMusic, videoHeight,
                    status -> editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(), status)
            );

            // Track stats
            storage.addActiveUser(from.getId());
            String contentType = isMusic ? "Music" : "Video";
            String storedName = from.getUserName() != null ? from.getUserName() : from.getFirstName();
            String title = result.isMultiFile()
                    ? result.getMetadata().getOrDefault("title", "TikTok Slideshow")
                    : result.getSingleFile().getFileName().toString().replaceFirst("\\.[^.]+$", "");

            storage.addDownload(contentType, from.getId(), storedName, platform, url, title);

            log.info("User: {} ({}, ID: {}) | Platform: {} | Type: {} | URL: {}",
                    from.getFirstName(), from.getUserName(), from.getId(), platform, contentType, url);

            if (result.isMultiFile()) {
                uploadMultiFile(bot, originalMessage, statusMsg, result, platform, url);
            } else {
                uploadSingleFile(bot, originalMessage, statusMsg, result, isMusic, platform, url);
            }

        } catch (Exception e) {
            log.error("Download error for URL {}: {}", url, e.getMessage(), e);
            String userError = buildUserErrorMessage(e.getMessage());
            editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(), userError);
        }
    }

    // ─── Upload helpers ───────────────────────────────────────────────────────────

    private void uploadSingleFile(AbsSender bot, Message originalMessage, Message statusMsg,
                                   DownloadResult result, boolean isMusic, String platform, String url) {
        editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(), "📤 Uploading to Telegram...");

        Path filePath = result.getSingleFile();
        Path thumbPath = result.getThumbnail();
        Map<String, String> meta = result.getMetadata();
        String caption = formatCaption(meta, platform, url);
        long chatId = originalMessage.getChatId();

        String ext = getExtension(filePath).toLowerCase();
        File file = filePath.toFile();

        try {
            if (List.of(".jpg", ".jpeg", ".png", ".webp").contains(ext)) {
                SendPhoto sp = new SendPhoto(String.valueOf(chatId), new InputFile(file));
                sp.setCaption(caption);
                sp.setParseMode("HTML");
                bot.execute(sp);

            } else if (isMusic) {
                SendAudio sa = new SendAudio(String.valueOf(chatId), new InputFile(file));
                sa.setCaption(caption);
                sa.setParseMode("HTML");
                sa.setDuration(parseDuration(meta.get("duration")));
                if (thumbPath != null) {
                    sa.setThumbnail(new InputFile(thumbPath.toFile()));
                }
                bot.execute(sa);

            } else {
                SendVideo sv = new SendVideo(String.valueOf(chatId), new InputFile(file));
                sv.setCaption(caption);
                sv.setParseMode("HTML");
                sv.setSupportsStreaming(true);
                sv.setDuration(parseDuration(meta.get("duration")));
                if (thumbPath != null) {
                    sv.setThumbnail(new InputFile(thumbPath.toFile()));
                }
                bot.execute(sv);
            }

            // Cleanup
            file.delete();
            if (thumbPath != null) thumbPath.toFile().delete();
            deleteMessage(bot, statusMsg.getChatId(), statusMsg.getMessageId());

        } catch (TelegramApiException e) {
            log.error("Failed to upload file to Telegram: {}", e.getMessage());
            editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(),
                    "❌ Failed to upload file to Telegram: " + e.getMessage());
        }
    }

    private void uploadMultiFile(AbsSender bot, Message originalMessage, Message statusMsg,
                                  DownloadResult result, String platform, String url) {
        editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(),
                "📤 Uploading slideshow to Telegram...");

        Map<String, String> meta = result.getMetadata();
        String caption = formatCaption(meta, platform, url);
        long chatId = originalMessage.getChatId();

        List<Path> imagePaths = new ArrayList<>();
        List<Path> videoPaths = new ArrayList<>();
        List<Path> audioPaths = new ArrayList<>();

        for (Path p : result.getFiles()) {
            String ext = getExtension(p).toLowerCase();
            if (List.of(".jpg", ".jpeg", ".png", ".webp").contains(ext)) imagePaths.add(p);
            else if (List.of(".mp4", ".mov", ".webm", ".mkv").contains(ext)) videoPaths.add(p);
            else if (List.of(".mp3", ".m4a", ".wav").contains(ext)) audioPaths.add(p);
        }

        List<Path> ordered = new ArrayList<>();
        ordered.addAll(imagePaths);
        ordered.addAll(videoPaths);
        ordered.sort(Comparator.comparing(p -> p.getFileName().toString()));

        // Build media group (max 10 per message)
        List<org.telegram.telegrambots.meta.api.objects.media.InputMedia> mediaGroup = new ArrayList<>();
        for (int i = 0; i < ordered.size(); i++) {
            Path p = ordered.get(i);
            String ext = getExtension(p).toLowerCase();
            boolean isFirst = (i == 0);

            if (List.of(".jpg", ".jpeg", ".png", ".webp").contains(ext)) {
                InputMediaPhoto photo = new InputMediaPhoto();
                photo.setMedia(p.toFile(), p.getFileName().toString());
                if (isFirst) {
                    photo.setCaption(caption);
                    photo.setParseMode("HTML");
                }
                mediaGroup.add(photo);
            } else {
                InputMediaVideo video = new InputMediaVideo();
                video.setMedia(p.toFile(), p.getFileName().toString());
                video.setSupportsStreaming(true);
                if (isFirst) {
                    video.setCaption(caption);
                    video.setParseMode("HTML");
                }
                mediaGroup.add(video);
            }
        }

        try {
            for (int i = 0; i < mediaGroup.size(); i += 10) {
                List<org.telegram.telegrambots.meta.api.objects.media.InputMedia> chunk =
                        mediaGroup.subList(i, Math.min(i + 10, mediaGroup.size()));
                SendMediaGroup smg = new SendMediaGroup(String.valueOf(chatId), chunk);
                bot.execute(smg);
            }

            // Send audio files separately
            for (Path audioPath : audioPaths) {
                SendAudio sa = new SendAudio(String.valueOf(chatId), new InputFile(audioPath.toFile()));
                bot.execute(sa);
                audioPath.toFile().delete();
            }

            // Cleanup
            for (Path p : result.getFiles()) p.toFile().delete();
            deleteMessage(bot, statusMsg.getChatId(), statusMsg.getMessageId());

        } catch (TelegramApiException e) {
            log.error("Failed to upload media group: {}", e.getMessage());
            editMessageText(bot, statusMsg.getChatId(), statusMsg.getMessageId(),
                    "❌ Failed to upload to Telegram: " + e.getMessage());
        }
    }

    // ─── Caption & metadata ───────────────────────────────────────────────────────

    /**
     * Telegram custom emoji ID for the verified checkmark (✓).
     * This is the Telegram animated emoji used in channel/user verified badges.
     * See: <a href="https://core.telegram.org/bots/api#formatting-options">Telegram formatting docs</a>
     */
    private static final String VERIFIED_EMOJI_ID = "5233582409416448551";

    /**
     * Builds a unified HTML caption (matches Python {@code format_caption()}).
     *
     * <pre>
     * 👤 UploaderName [✓] | <a href="url">Link</a>
     * Developed by @datapeice
     * </pre>
     */
    public String formatCaption(Map<String, String> metadata, String platform, String originalUrl) {
        String uploader = metadata.getOrDefault("uploader", "Unknown");
        String url = originalUrl != null && !originalUrl.isBlank()
                ? originalUrl : metadata.getOrDefault("webpage_url", "");

        // Strip leading @
        if (uploader.startsWith("@")) uploader = uploader.substring(1);

        // Escape HTML
        uploader = uploader.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;");

        boolean isVerified = "true".equalsIgnoreCase(metadata.get("verified"));
        if (isVerified) {
            uploader = uploader + " <tg-emoji emoji-id=\"" + VERIFIED_EMOJI_ID + "\">✓</tg-emoji>";
        }

        return "👤 " + uploader + " | <a href=\"" + url + "\">Link</a>\n"
                + "Developed by @datapeice";
    }

    // ─── Error message builder ────────────────────────────────────────────────────

    private String buildUserErrorMessage(String errorMsg) {
        if (errorMsg == null) return "❌ Unknown error occurred.";
        if (errorMsg.contains("Unsupported URL"))
            return "❌ This URL is not supported. Please try a different link.";
        if (errorMsg.contains("Private video") || errorMsg.contains("Login required"))
            return "❌ This video is private or requires login.";
        if (errorMsg.contains("Sign in to confirm"))
            return "⚠️ YouTube requires authentication (cookies). Please contact the bot admin.";
        return "```error\n" + errorMsg + "\n```\n\nContact the developer @datapeice";
    }

    // ─── Keyboards ────────────────────────────────────────────────────────────────

    private InlineKeyboardMarkup buildFormatKeyboard(String requestId) {
        InlineKeyboardButton audio = InlineKeyboardButton.builder()
                .text("🎵 Audio (MP3)").callbackData("format:audio:" + requestId).build();
        InlineKeyboardButton video = InlineKeyboardButton.builder()
                .text("🎥 Video").callbackData("format:video:" + requestId).build();

        return InlineKeyboardMarkup.builder()
                .keyboardRow(List.of(audio, video))
                .build();
    }

    private InlineKeyboardMarkup buildResolutionKeyboard(String requestId) {
        int[][] resolutions = {{1080, 1080}, {720, 720}, {480, 480}, {360, 360}};
        List<List<InlineKeyboardButton>> rows = new ArrayList<>();
        List<InlineKeyboardButton> row = new ArrayList<>();
        for (int[] res : resolutions) {
            row.add(InlineKeyboardButton.builder()
                    .text(res[0] + "p")
                    .callbackData("dl_res:" + requestId + ":" + res[1])
                    .build());
        }
        rows.add(row);
        return InlineKeyboardMarkup.builder().keyboard(rows).build();
    }

    // ─── Telegram API helpers ─────────────────────────────────────────────────────

    private void sendText(AbsSender bot, long chatId, String text) {
        try {
            bot.execute(new SendMessage(String.valueOf(chatId), text));
        } catch (TelegramApiException e) {
            log.error("sendText failed: {}", e.getMessage());
        }
    }

    private Message sendTextAndGetMessage(AbsSender bot, long chatId, String text) {
        try {
            return bot.execute(new SendMessage(String.valueOf(chatId), text));
        } catch (TelegramApiException e) {
            log.error("sendTextAndGet failed: {}", e.getMessage());
            return null;
        }
    }

    private void sendWithKeyboard(AbsSender bot, long chatId, String text, InlineKeyboardMarkup keyboard) {
        SendMessage msg = new SendMessage(String.valueOf(chatId), text);
        msg.setReplyMarkup(keyboard);
        try {
            bot.execute(msg);
        } catch (TelegramApiException e) {
            log.error("sendWithKeyboard failed: {}", e.getMessage());
        }
    }

    private void editMessageText(AbsSender bot, long chatId, int messageId, String text) {
        EditMessageText edit = new EditMessageText();
        edit.setChatId(chatId);
        edit.setMessageId(messageId);
        edit.setText(text);
        try {
            bot.execute(edit);
        } catch (TelegramApiException e) {
            // Silently ignore "message is not modified" errors
        }
    }

    private void editMessageWithKeyboard(AbsSender bot, long chatId, int messageId,
                                          String text, InlineKeyboardMarkup keyboard) {
        EditMessageText edit = new EditMessageText();
        edit.setChatId(chatId);
        edit.setMessageId(messageId);
        edit.setText(text);
        edit.setReplyMarkup(keyboard);
        try {
            bot.execute(edit);
        } catch (TelegramApiException e) {
            log.error("editMessageWithKeyboard failed: {}", e.getMessage());
        }
    }

    private void answerCallback(AbsSender bot, String callbackId) {
        try {
            bot.execute(new AnswerCallbackQuery(callbackId));
        } catch (TelegramApiException e) {
            log.warn("answerCallback failed: {}", e.getMessage());
        }
    }

    private void deleteMessage(AbsSender bot, long chatId, int messageId) {
        try {
            bot.execute(new org.telegram.telegrambots.meta.api.methods.updatingmessages.DeleteMessage(
                    String.valueOf(chatId), messageId));
        } catch (TelegramApiException e) {
            // Ignore
        }
    }

    // ─── Utilities ────────────────────────────────────────────────────────────────

    private String getExtension(Path p) {
        String name = p.getFileName().toString();
        int idx = name.lastIndexOf('.');
        return idx >= 0 ? name.substring(idx) : "";
    }

    private int parseDuration(String value) {
        if (value == null) return 0;
        try {
            return (int) Double.parseDouble(value);
        } catch (NumberFormatException e) {
            return 0;
        }
    }
}
