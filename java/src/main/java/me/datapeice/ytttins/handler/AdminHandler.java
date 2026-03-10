package me.datapeice.ytttins.handler;

import me.datapeice.ytttins.config.BotConfig;
import me.datapeice.ytttins.database.entity.BotCookie;
import me.datapeice.ytttins.database.entity.DownloadHistory;
import me.datapeice.ytttins.database.repository.CookieRepository;
import me.datapeice.ytttins.database.repository.DownloadHistoryRepository;
import me.datapeice.ytttins.database.service.StorageService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Component;
import org.telegram.telegrambots.meta.api.methods.AnswerCallbackQuery;
import org.telegram.telegrambots.meta.api.methods.GetFile;
import org.telegram.telegrambots.meta.api.methods.send.SendDocument;
import org.telegram.telegrambots.meta.api.methods.send.SendMessage;
import org.telegram.telegrambots.meta.api.methods.updatingmessages.DeleteMessage;
import org.telegram.telegrambots.meta.api.methods.updatingmessages.EditMessageText;
import org.telegram.telegrambots.meta.api.objects.*;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.InlineKeyboardMarkup;
import org.telegram.telegrambots.meta.api.objects.replykeyboard.buttons.InlineKeyboardButton;
import org.telegram.telegrambots.meta.bots.AbsSender;
import org.telegram.telegrambots.meta.exceptions.TelegramApiException;

import java.io.*;
import java.net.URL;
import java.nio.file.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * Handles admin commands and the interactive admin panel.
 *
 * <p>Equivalent to {@code handlers/admin.py} in the Python version.
 *
 * <h3>State machine</h3>
 * Because TelegramBots Java does not ship FSM support, a simple in-memory
 * {@link Map} ({@code adminState}) stores the current state for each admin chat.
 * States:
 * <ul>
 *   <li>{@code IDLE} – no pending input</li>
 *   <li>{@code BROADCAST_WAITING} – waiting for a broadcast message</li>
 *   <li>{@code COOKIE_CONFIRM_PENDING} – waiting for cookie confirm/cancel</li>
 * </ul>
 */
@Component
public class AdminHandler {

    private static final Logger log = LoggerFactory.getLogger(AdminHandler.class);
    private static final int HISTORY_PAGE_SIZE = 20;
    private static final DateTimeFormatter HIST_FMT = DateTimeFormatter.ofPattern("dd-MM HH:mm");

    // Simple FSM states
    private enum AdminState { IDLE, BROADCAST_WAITING }
    private final Map<Long, AdminState> adminState = new ConcurrentHashMap<>();
    private final Map<Long, String> cookieTempPath = new ConcurrentHashMap<>();

    private final BotConfig config;
    private final StorageService storage;
    private final CookieRepository cookieRepo;
    private final DownloadHistoryRepository historyRepo;

    public AdminHandler(BotConfig config, StorageService storage,
                        CookieRepository cookieRepo, DownloadHistoryRepository historyRepo) {
        this.config = config;
        this.storage = storage;
        this.cookieRepo = cookieRepo;
        this.historyRepo = historyRepo;
    }

    // ─── Public entry points ─────────────────────────────────────────────────────

    public void handleMessage(AbsSender bot, Message message) {
        String text = message.getText();
        if (text == null) return;

        long chatId = message.getChatId();
        AdminState state = adminState.getOrDefault(chatId, AdminState.IDLE);

        if (state == AdminState.BROADCAST_WAITING) {
            if ("/cancel".equals(text)) {
                adminState.put(chatId, AdminState.IDLE);
                sendText(bot, chatId, "❌ Broadcast cancelled.");
            } else {
                processBroadcast(bot, message);
            }
            return;
        }

        if (text.startsWith("/panel")) {
            sendAdminPanel(bot, message);
        } else if (text.startsWith("/whitelist ")) {
            handleWhitelistAdd(bot, message, text.substring(11).trim());
        } else if (text.startsWith("/unwhitelist ")) {
            handleWhitelistRemove(bot, message, text.substring(13).trim());
        } else if (text.toLowerCase().startsWith("add @")) {
            handleWhitelistAdd(bot, message, text.substring(5).trim());
        }
    }

    public void handleCallback(AbsSender bot, CallbackQuery callback) {
        answerCallback(bot, callback.getId());

        String data = callback.getData();
        if (data == null) return;

        if (data.startsWith("cookie:")) {
            handleCookieCallback(bot, callback, data.substring(7));
        } else if (data.startsWith("broadcast:")) {
            handleBroadcastConfirm(bot, callback, data.substring(10));
        } else if (data.startsWith("admin:")) {
            handleAdminAction(bot, callback, data.substring(6));
        }
    }

    public void handleDocument(AbsSender bot, Message message) {
        Document doc = message.getDocument();
        if (doc == null) return;

        if ("cookies.txt".equals(doc.getFileName())) {
            processCookieUpload(bot, message, doc);
        }
    }

    // ─── /panel ──────────────────────────────────────────────────────────────────

    private void sendAdminPanel(AbsSender bot, Message message) {
        String statsText = buildStatsText();
        InlineKeyboardMarkup keyboard = buildPanelKeyboard();
        SendMessage msg = new SendMessage(String.valueOf(message.getChatId()), statsText);
        msg.setParseMode("HTML");
        msg.setReplyMarkup(keyboard);
        try {
            bot.execute(msg);
        } catch (TelegramApiException e) {
            log.error("sendAdminPanel failed: {}", e.getMessage());
        }
    }

    // ─── Whitelist commands ───────────────────────────────────────────────────────

    private void handleWhitelistAdd(AbsSender bot, Message message, String username) {
        username = username.replaceFirst("^@", "");
        if (storage.addToWhitelist(username)) {
            sendText(bot, message.getChatId(), "✅ User @" + username + " has been added to the whitelist.");
        } else {
            sendText(bot, message.getChatId(), "⚠️ User @" + username + " is already in the whitelist.");
        }
    }

    private void handleWhitelistRemove(AbsSender bot, Message message, String username) {
        username = username.replaceFirst("^@", "");
        if (storage.removeFromWhitelist(username)) {
            sendText(bot, message.getChatId(), "✅ User @" + username + " has been removed from the whitelist.");
        } else {
            sendText(bot, message.getChatId(), "⚠️ User @" + username + " is not in the whitelist.");
        }
    }

    // ─── Admin panel callback actions ─────────────────────────────────────────────

    private void handleAdminAction(AbsSender bot, CallbackQuery callback, String action) {
        long chatId = callback.getMessage().getChatId();
        int messageId = callback.getMessage().getMessageId();

        switch (action) {
            case "back", "stats" -> {
                String text = buildStatsText();
                editMessageText(bot, chatId, messageId, text, buildPanelKeyboard(), "HTML");
            }
            case "users" -> {
                Set<String> users = storage.getWhitelistedUsers();
                String list = users.isEmpty() ? "No whitelisted users"
                        : users.stream().map(u -> "• @" + u).collect(Collectors.joining("\n"));
                editMessageText(bot, chatId, messageId, "📝 *Whitelisted Users:*\n\n" + list,
                        backKeyboard(), "Markdown");
            }
            case "add_user" ->
                    sendText(bot, chatId, "Please use: /whitelist <username>");
            case "remove_user" -> {
                Set<String> users = storage.getWhitelistedUsers();
                if (users.isEmpty()) {
                    sendText(bot, chatId, "The whitelist is empty.");
                    return;
                }
                List<List<InlineKeyboardButton>> rows = new ArrayList<>();
                for (String u : users) {
                    rows.add(List.of(InlineKeyboardButton.builder()
                            .text("❌ @" + u).callbackData("admin:remove:" + u).build()));
                }
                rows.add(List.of(InlineKeyboardButton.builder()
                        .text("🔙 Back").callbackData("admin:back").build()));
                editMessageText(bot, chatId, messageId, "Select user to remove:",
                        InlineKeyboardMarkup.builder().keyboard(rows).build(), null);
            }
            case "broadcast" -> {
                adminState.put(chatId, AdminState.BROADCAST_WAITING);
                sendText(bot, chatId,
                        "📨 Send the message you want to broadcast to all users.\n"
                                + "Send /cancel to abort.");
            }
            case "update_cookies" ->
                    sendText(bot, chatId, "Please send the cookies.txt file now.");
            case "update_ytdlp" ->
                    CompletableFuture.runAsync(() -> updateYtDlp(bot, chatId));
            case "get_logs" ->
                    sendLogFile(bot, chatId);
            case "close" -> {
                try {
                    bot.execute(new DeleteMessage(String.valueOf(chatId), messageId));
                } catch (TelegramApiException e) {
                    log.warn("Could not delete admin panel message: {}", e.getMessage());
                }
            }
            default -> {
                if (action.startsWith("remove:")) {
                    String username = action.substring(7);
                    if (storage.removeFromWhitelist(username)) {
                        editMessageText(bot, chatId, messageId,
                                "✅ User @" + username + " has been removed from the whitelist.", null, null);
                    }
                } else if (action.startsWith("history")) {
                    int page = 0;
                    if (action.contains(":")) {
                        try { page = Integer.parseInt(action.split(":")[1]); } catch (Exception ignored) {}
                    }
                    sendHistory(bot, chatId, messageId, page);
                }
            }
        }
    }

    // ─── Broadcast ────────────────────────────────────────────────────────────────

    private void processBroadcast(AbsSender bot, Message message) {
        long chatId = message.getChatId();
        adminState.put(chatId, AdminState.IDLE);

        List<Long> userIds = storage.getAllUserIds();
        if (userIds.isEmpty()) {
            sendText(bot, chatId, "❌ No users to broadcast to.");
            return;
        }

        InlineKeyboardMarkup confirmKeyboard = InlineKeyboardMarkup.builder()
                .keyboardRow(List.of(
                        InlineKeyboardButton.builder().text("✅ Confirm").callbackData("broadcast:confirm:" + message.getMessageId()).build(),
                        InlineKeyboardButton.builder().text("❌ Cancel").callbackData("broadcast:cancel").build()
                )).build();

        SendMessage preview = new SendMessage(String.valueOf(chatId),
                "📨 Broadcast to " + userIds.size() + " users. Confirm?");
        preview.setReplyMarkup(confirmKeyboard);
        try {
            bot.execute(preview);
        } catch (TelegramApiException e) {
            log.error("Error sending broadcast confirm: {}", e.getMessage());
        }
    }

    private void handleBroadcastConfirm(AbsSender bot, CallbackQuery callback, String action) {
        long chatId = callback.getMessage().getChatId();
        int messageId = callback.getMessage().getMessageId();

        if (action.equals("cancel")) {
            editMessageText(bot, chatId, messageId, "❌ Broadcast cancelled.", null, null);
            return;
        }

        if (action.startsWith("confirm:")) {
            int srcMsgId;
            try {
                srcMsgId = Integer.parseInt(action.substring(8));
            } catch (NumberFormatException e) {
                return;
            }

            List<Long> userIds = storage.getAllUserIds();
            editMessageText(bot, chatId, messageId,
                    "📤 Broadcasting to " + userIds.size() + " users...", null, null);

            CompletableFuture.runAsync(() -> {
                int success = 0, fail = 0;
                for (int i = 0; i < userIds.size(); i++) {
                    long uid = userIds.get(i);
                    try {
                        org.telegram.telegrambots.meta.api.methods.CopyMessage copy =
                                new org.telegram.telegrambots.meta.api.methods.CopyMessage(
                                        String.valueOf(uid),
                                        String.valueOf(chatId),
                                        srcMsgId);
                        bot.execute(copy);
                        success++;
                    } catch (TelegramApiException e) {
                        log.warn("Broadcast failed for user {}: {}", uid, e.getMessage());
                        fail++;
                    }

                    try { Thread.sleep(50); } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        break; // abort broadcast if thread is interrupted
                    }

                    if ((i + 1) % 10 == 0 || (i + 1) == userIds.size()) {
                        editMessageText(bot, chatId, messageId,
                                "📤 Broadcasting " + (i + 1) + "/" + userIds.size()
                                        + "\n✅ Sent: " + success + "\n❌ Failed: " + fail, null, null);
                    }
                }
                editMessageText(bot, chatId, messageId,
                        "✅ Broadcast complete!\n📊 Total: " + userIds.size()
                                + "\n✅ Sent: " + success + "\n❌ Failed: " + fail, null, null);
            });
        }
    }

    // ─── Cookie upload ────────────────────────────────────────────────────────────

    private void processCookieUpload(AbsSender bot, Message message, Document doc) {
        long chatId = message.getChatId();
        try {
            GetFile getFile = new GetFile(doc.getFileId());
            org.telegram.telegrambots.meta.api.objects.File tgFile = bot.execute(getFile);

            // Download to temp file
            Path tmpPath = config.getDataDir().resolve("cookies.txt.tmp");
            String fileUrl = "https://api.telegram.org/file/bot" + config.getBotToken() + "/" + tgFile.getFilePath();
            try (InputStream in = new URL(fileUrl).openStream();
                 OutputStream out = Files.newOutputStream(tmpPath)) {
                in.transferTo(out);
            }
            cookieTempPath.put(chatId, tmpPath.toString());

            InlineKeyboardMarkup keyboard = InlineKeyboardMarkup.builder()
                    .keyboardRow(List.of(
                            InlineKeyboardButton.builder().text("✅ Confirm").callbackData("cookie:confirm").build(),
                            InlineKeyboardButton.builder().text("❌ Cancel").callbackData("cookie:cancel").build()
                    )).build();

            SendMessage msg = new SendMessage(String.valueOf(chatId),
                    "⚠️ You are about to overwrite cookies.txt. Proceed?");
            msg.setReplyMarkup(keyboard);
            bot.execute(msg);
        } catch (Exception e) {
            log.error("Cookie upload failed: {}", e.getMessage());
            sendText(bot, chatId, "❌ Error uploading cookies: " + e.getMessage());
        }
    }

    private void handleCookieCallback(AbsSender bot, CallbackQuery callback, String action) {
        long chatId = callback.getMessage().getChatId();
        int messageId = callback.getMessage().getMessageId();
        String tmpPathStr = cookieTempPath.remove(chatId);

        if ("confirm".equals(action)) {
            if (tmpPathStr == null) {
                editMessageText(bot, chatId, messageId, "❌ Temporary file not found. Please upload again.", null, null);
                return;
            }
            try {
                Path tmpPath = Path.of(tmpPathStr);
                String content = Files.readString(tmpPath);

                // Save to DB
                cookieRepo.deleteAll();
                BotCookie cookie = new BotCookie();
                cookie.setContent(content);
                cookieRepo.save(cookie);

                // Replace on disk
                Path targetPath = config.getDataDir().resolve("cookies.txt");
                Files.move(tmpPath, targetPath, StandardCopyOption.REPLACE_EXISTING);
                editMessageText(bot, chatId, messageId, "✅ cookies.txt updated successfully!", null, null);
            } catch (Exception e) {
                log.error("Error applying cookies: {}", e.getMessage());
                editMessageText(bot, chatId, messageId, "❌ Error: " + e.getMessage(), null, null);
            }
        } else {
            if (tmpPathStr != null) {
                try { Files.deleteIfExists(Path.of(tmpPathStr)); } catch (IOException ignored) {}
            }
            editMessageText(bot, chatId, messageId, "❌ Cancelled. cookies.txt was not modified.", null, null);
        }
    }

    // ─── History ──────────────────────────────────────────────────────────────────

    private void sendHistory(AbsSender bot, long chatId, int messageId, int page) {
        try {
            Page<DownloadHistory> histPage = historyRepo.findAll(
                    PageRequest.of(page, HISTORY_PAGE_SIZE, Sort.by(Sort.Direction.DESC, "timestamp")));

            if (histPage.isEmpty()) {
                editMessageText(bot, chatId, messageId, "📜 *Download History*\n\nNo downloads recorded yet.",
                        backKeyboard(), "Markdown");
                return;
            }

            StringBuilder text = new StringBuilder("📜 *Download History (Page ")
                    .append(page + 1).append(")*\n\n");
            for (DownloadHistory h : histPage.getContent()) {
                String dateStr = h.getTimestamp() != null ? h.getTimestamp().format(HIST_FMT) : "??";
                String uname = formatHistoryUsername(h.getUsername());
                String platform = getPlatformLabel(h.getUrl());
                text.append("`").append(dateStr).append("` | ")
                        .append(uname).append(" | [").append(platform).append("](").append(h.getUrl()).append(")\n");
            }

            List<InlineKeyboardButton> nav = new ArrayList<>();
            if (page > 0) {
                nav.add(InlineKeyboardButton.builder().text("⬅️ Prev").callbackData("admin:history:" + (page - 1)).build());
            }
            if (histPage.hasNext()) {
                nav.add(InlineKeyboardButton.builder().text("Next ➡️").callbackData("admin:history:" + (page + 1)).build());
            }

            List<List<InlineKeyboardButton>> rows = new ArrayList<>();
            if (!nav.isEmpty()) rows.add(nav);
            rows.add(List.of(InlineKeyboardButton.builder().text("🔙 Back").callbackData("admin:back").build()));

            editMessageText(bot, chatId, messageId, text.toString(),
                    InlineKeyboardMarkup.builder().keyboard(rows).build(), "Markdown");
        } catch (Exception e) {
            log.error("Error fetching history: {}", e.getMessage());
            editMessageText(bot, chatId, messageId, "❌ Error: " + e.getMessage(), backKeyboard(), null);
        }
    }

    // ─── yt-dlp update ────────────────────────────────────────────────────────────

    private void updateYtDlp(AbsSender bot, long chatId) {
        sendText(bot, chatId, "🔄 Updating yt-dlp...");
        try {
            ProcessBuilder pb = new ProcessBuilder("pip", "install", "--upgrade", "yt-dlp");
            pb.redirectErrorStream(true);
            Process p = pb.start();
            String output = new String(p.getInputStream().readAllBytes());
            int exitCode = p.waitFor();
            if (exitCode == 0) {
                sendText(bot, chatId, "✅ yt-dlp updated successfully!\n```\n" + output.substring(0, Math.min(300, output.length())) + "\n```");
            } else {
                sendText(bot, chatId, "❌ Update failed:\n```\n" + output.substring(0, Math.min(300, output.length())) + "\n```");
            }
        } catch (Exception e) {
            log.error("yt-dlp update error: {}", e.getMessage());
            sendText(bot, chatId, "❌ Update error: " + e.getMessage());
        }
    }

    // ─── Logs ─────────────────────────────────────────────────────────────────────

    private void sendLogFile(AbsSender bot, long chatId) {
        List<Path> candidates = List.of(
                config.getLogDir().resolve("bot.log"),
                Path.of("bot.log"),
                Path.of("logs/bot.log")
        );
        for (Path logPath : candidates) {
            if (Files.exists(logPath)) {
                try {
                    SendDocument sd = new SendDocument(
                            String.valueOf(chatId),
                            new InputFile(logPath.toFile(), "bot.log.txt"));
                    sd.setCaption("📂 bot.log");
                    bot.execute(sd);
                    return;
                } catch (TelegramApiException e) {
                    log.error("sendLogFile failed: {}", e.getMessage());
                }
            }
        }
        sendText(bot, chatId, "❌ No log files found.");
    }

    // ─── Stats text builder ───────────────────────────────────────────────────────

    private String buildStatsText() {
        StorageService.WeeklyStats ws = storage.getWeeklyStats();
        Set<String> wl = storage.getWhitelistedUsers();
        String wlText = wl.isEmpty() ? "  No whitelisted users"
                : wl.stream().map(u -> "  @" + u).collect(Collectors.joining("\n"));

        return "📊 Weekly Statistics:\n\n"
                + "📥 Downloads:\n"
                + "   📹 Videos: " + ws.videoCount() + "\n"
                + "   🎵 Music: " + ws.audioCount() + "\n\n"
                + "👥 Active Users (last 7 days): " + ws.activeUsersCount() + "\n\n"
                + "📝 Whitelisted Users:\n"
                + wlText + "\n";
    }

    // ─── Keyboard builders ────────────────────────────────────────────────────────

    private InlineKeyboardMarkup buildPanelKeyboard() {
        return InlineKeyboardMarkup.builder()
                .keyboardRow(List.of(btn("👥 Users List", "admin:users")))
                .keyboardRow(List.of(btn("➕ Add User", "admin:add_user"), btn("➖ Remove User", "admin:remove_user")))
                .keyboardRow(List.of(btn("📊 Statistics", "admin:stats"), btn("📜 History", "admin:history")))
                .keyboardRow(List.of(btn("📨 Broadcast Message", "admin:broadcast")))
                .keyboardRow(List.of(btn("🍪 Update Cookies", "admin:update_cookies"), btn("🔄 Update yt-dlp", "admin:update_ytdlp")))
                .keyboardRow(List.of(btn("📂 Get Logs", "admin:get_logs"), btn("❌ Close", "admin:close")))
                .build();
    }

    private InlineKeyboardMarkup backKeyboard() {
        return InlineKeyboardMarkup.builder()
                .keyboardRow(List.of(btn("🔙 Back", "admin:back")))
                .build();
    }

    private InlineKeyboardButton btn(String text, String callback) {
        return InlineKeyboardButton.builder().text(text).callbackData(callback).build();
    }

    // ─── Utility helpers ──────────────────────────────────────────────────────────

    private String getPlatformLabel(String url) {
        if (url == null || url.isBlank()) return "Link";
        String u = url.toLowerCase();
        if (u.contains("youtube.com") || u.contains("youtu.be")) return "YouTube";
        if (u.contains("tiktok.com")) return "TikTok";
        if (u.contains("instagram.com")) return "Instagram";
        if (u.contains("twitter.com") || u.contains("x.com")) return "X";
        if (u.contains("facebook.com") || u.contains("fb.watch")) return "Facebook";
        if (u.contains("twitch.tv")) return "Twitch";
        if (u.contains("soundcloud.com")) return "SoundCloud";
        try {
            java.net.URI uri = new java.net.URI(url);
            String host = uri.getHost();
            if (host != null && host.startsWith("www.")) host = host.substring(4);
            return host != null ? host : "Link";
        } catch (Exception e) {
            return "Link";
        }
    }

    private String formatHistoryUsername(String username) {
        if (username == null || username.isBlank()) return "Unknown";
        String safe = username.replace("_", "\\_");
        if (username.matches("[A-Za-z0-9_]{5,}")) return "@" + safe;
        return safe;
    }

    private void sendText(AbsSender bot, long chatId, String text) {
        try {
            bot.execute(new SendMessage(String.valueOf(chatId), text));
        } catch (TelegramApiException e) {
            log.error("sendText failed: {}", e.getMessage());
        }
    }

    private void editMessageText(AbsSender bot, long chatId, int messageId, String text,
                                  InlineKeyboardMarkup keyboard, String parseMode) {
        EditMessageText edit = new EditMessageText();
        edit.setChatId(chatId);
        edit.setMessageId(messageId);
        edit.setText(text);
        if (keyboard != null) edit.setReplyMarkup(keyboard);
        if (parseMode != null) edit.setParseMode(parseMode);
        try {
            bot.execute(edit);
        } catch (TelegramApiException e) {
            log.warn("editMessageText failed: {}", e.getMessage());
        }
    }

    private void answerCallback(AbsSender bot, String callbackId) {
        try {
            bot.execute(new AnswerCallbackQuery(callbackId));
        } catch (TelegramApiException e) {
            log.warn("answerCallback failed: {}", e.getMessage());
        }
    }
}
