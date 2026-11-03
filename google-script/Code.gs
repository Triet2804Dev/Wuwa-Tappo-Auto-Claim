/**
 * Wuwa Tappo Auto Claim - Google Apps Script (24/7 Cloud)
 * Author: github.com/Triet2804Dev
 */

// ==========================================
// CONFIGURATION
// ==========================================
const CONFIG = {
  // Enter your raw 64-character token here (e.g. from config.json or tool/copy_token.bat)
  TOKEN: "YOUR_TOKEN_HERE",

  // Maximum retry attempts for API and Discord calls (against rate limits and network drops)
  MAX_RETRIES: 3,

  // Discord Webhook URL for reward notifications (optional, leave empty "" if not used)
  DISCORD_WEBHOOK: "",
};

const APP_VERSION = "1.0.1";
const VERSION_CHECK_URL = "https://raw.githubusercontent.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim/refs/heads/main/google-script/version.json";
const SERVICE_BASE = "https://api-wutheringwaves-wuwatappo.kurogames-global.com";
const UPDATE_NOTIFY_INTERVAL_MS = 24 * 60 * 60 * 1000; // 24 hours cooldown

// ==========================================
// CORE FUNCTIONS
// ==========================================

function parseVersion(v) {
  const parts = String(v || "").match(/\d+/g);
  return parts ? parts.map(Number) : [0];
}

function isNewerVersion(remote, local) {
  const r = parseVersion(remote);
  const l = parseVersion(local);
  for (let i = 0; i < Math.max(r.length, l.length); i++) {
    const rv = r[i] || 0;
    const lv = l[i] || 0;
    if (rv > lv) return true;
    if (rv < lv) return false;
  }
  return false;
}

function checkForUpdates() {
  try {
    const resp = UrlFetchApp.fetch(VERSION_CHECK_URL, { muteHttpExceptions: true });
    if (resp.getResponseCode() === 200) {
      const data = JSON.parse(resp.getContentText());
      if (data.version && isNewerVersion(data.version, APP_VERSION)) {
        Logger.log(`[!] UPDATE AVAILABLE: Google Script v${data.version} is released! (Current: v${APP_VERSION})`);
        Logger.log(`[!] Source URL: ${data.source_url || ""}`);
        return data;
      }
    }
  } catch (e) {
    Logger.log("[-] Update check skipped: " + e.message);
  }
  return null;
}

/**
 * Checks for Google Script updates and notifies Discord.
 * Enforces a strict 24-hour cooldown between update notifications to prevent spam.
 */
function checkAndNotifyUpdate(forceNotify = false) {
  const update = checkForUpdates();
  if (!update) return;

  const webhook = CONFIG.DISCORD_WEBHOOK ? CONFIG.DISCORD_WEBHOOK.trim() : "";
  if (!webhook.startsWith("https://discord.com/api/webhooks/")) return;

  const props = PropertiesService.getScriptProperties();
  const lastNotify = parseInt(props.getProperty("LAST_UPDATE_NOTIFY_TS") || "0", 10);
  const notifiedVer = props.getProperty("NOTIFIED_UPDATE_VERSION") || "";
  const now = Date.now();

  // Only notify if new version is detected OR if 24 hours have elapsed since the last notification
  if (forceNotify || notifiedVer !== update.version || (now - lastNotify >= UPDATE_NOTIFY_INTERVAL_MS)) {
    Logger.log(`[>>] Sending update notification to Discord (v${update.version})...`);

    const embed = {
      title: `📢 Wuwa Tappo Auto Claim (GAS v${APP_VERSION}): New Update Available!`,
      color: 0x5865F2,
      description: `A newer version of **Google Apps Script** (**v${update.version}**) is now available!\nYour current version is **v${APP_VERSION}**.`,
      fields: [
        { name: "✨ Latest Version", value: `\`v${update.version}\``, inline: true },
        { name: "📦 Current Version", value: `\`v${APP_VERSION}\``, inline: true },
        { name: "🔗 Update Link", value: `[Click here to copy Code.gs](${update.source_url || ""})`, inline: false }
      ],
      footer: { text: "Wuwa Tappo Auto Claim • github.com/Triet2804Dev" },
      timestamp: new Date().toISOString()
    };

    try {
      fetchWithRetry(webhook, {
        method: "post",
        contentType: "application/json",
        payload: JSON.stringify({
          username: `Wuwa Tappo Auto Claim (GAS v${APP_VERSION})`,
          avatar_url: "https://aki-gm-resources-back.aki-game.net/head_photo/82001501.png",
          embeds: [embed]
        }),
        muteHttpExceptions: true
      });

      // Save notification timestamp and version to enforce 24-hour cooldown
      props.setProperty("LAST_UPDATE_NOTIFY_TS", String(now));
      props.setProperty("NOTIFIED_UPDATE_VERSION", update.version);
    } catch (e) {
      Logger.log("[-] Failed to send Discord update notification: " + e.message);
    }
  }
}

function getOrGenerateCID() {
  const props = PropertiesService.getScriptProperties();
  let cid = props.getProperty("DEVICE_CID");
  if (!cid) {
    cid = Utilities.getUuid().replace(/-/g, "").toLowerCase();
    props.setProperty("DEVICE_CID", cid);
  }
  return cid;
}

function getHeaders() {
  const token = CONFIG.TOKEN.replace(/^Bearer\s+/i, "").trim();
  return {
    "Authorization": "Bearer " + token,
    "X-BLM-CID": getOrGenerateCID(),
    "X-BLM-FRID": Utilities.getUuid().replace(/-/g, ""),
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
    "Origin": "http://tauri.localhost",
    "Referer": "http://tauri.localhost/",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json"
  };
}

/**
 * Executes HTTP requests with exponential backoff retry mechanism.
 * Handles rate limits (HTTP 429), server hiccups (HTTP 5xx), and network timeouts.
 */
function fetchWithRetry(url, options = {}) {
  const maxRetries = Math.max(1, CONFIG.MAX_RETRIES || 3);
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      const resp = UrlFetchApp.fetch(url, options);
      const code = resp.getResponseCode();

      // Retry on Rate limit (429) or Server error (5xx)
      if ((code === 429 || code >= 500) && attempt < maxRetries) {
        const backoff = attempt * 2000;
        Logger.log(`[!] HTTP ${code} on ${url}. Retrying (${attempt}/${maxRetries}) in ${backoff / 1000}s...`);
        Utilities.sleep(backoff);
        continue;
      }
      return resp;
    } catch (e) {
      if (attempt < maxRetries) {
        const backoff = attempt * 2000;
        Logger.log(`[!] Request error: ${e.message}. Retrying (${attempt}/${maxRetries}) in ${backoff / 1000}s...`);
        Utilities.sleep(backoff);
      } else {
        throw e;
      }
    }
  }
  return null;
}

function formatDuration(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return m > 0 ? `${m}m ${rem}s` : `${rem}s`;
}

function getAssetUrl(assetName) {
  if (!assetName) return "";
  const base = "https://wutheringwaves-wuwatappo.kurogames-global.com";
  const lower = assetName.toLowerCase();
  if (lower.startsWith("accessory")) return `${base}/accessory/${assetName}`;
  if (lower.startsWith("role")) return `${base}/character/${assetName}`;
  if (lower.startsWith("emote")) return `${base}/emote/${assetName}`;
  return `${base}/${assetName}`;
}

function sendDiscordWebhook(nickname, place, assetName, rarity, balance, leftSec, rightSec) {
  const webhook = CONFIG.DISCORD_WEBHOOK ? CONFIG.DISCORD_WEBHOOK.trim() : "";
  if (!webhook.startsWith("https://discord.com/api/webhooks/")) return;

  const colorMap = { epic: 0x9B59B6, rare: 0x3498DB, uncommon: 0x2ECC71, common: 0xF1C40F };
  const embedColor = colorMap[(rarity || "common").toLowerCase()] || 0x5865F2;
  const label = place === "left" ? "Left Chest" : "Right Chest";
  const imageUrl = getAssetUrl(assetName);

  const embed = {
    title: `🎁 ${label} Claimed Successfully!`,
    color: embedColor,
    fields: [
      { name: "👤 Player", value: nickname || "Player", inline: true },
      { name: "📦 Chest", value: label, inline: true },
      { name: "💎 Rarity", value: (rarity || "COMMON").toUpperCase(), inline: true },
      { name: "✨ Reward Item", value: `\`${assetName}\``, inline: true },
      { name: "🔘 Balance", value: `${balance.toLocaleString()} clicks`, inline: true },
      { name: "⏳ Next Cooldowns", value: `Left: \`${formatDuration(leftSec)}\` | Right: \`${formatDuration(rightSec)}\``, inline: false }
    ],
    footer: { text: "Wuwa Tappo Auto Claim • github.com/Triet2804Dev" },
    timestamp: new Date().toISOString()
  };

  if (imageUrl) embed.thumbnail = { url: imageUrl };

  try {
    fetchWithRetry(webhook, {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({
        username: `Wuwa Tappo Auto Claim (GAS v${APP_VERSION})`,
        avatar_url: "https://aki-gm-resources-back.aki-game.net/head_photo/82001501.png",
        embeds: [embed]
      }),
      muteHttpExceptions: true
    });
  } catch (e) {
    Logger.log("[-] Discord webhook failed: " + e.message);
  }
}

function deleteTriggers(handlerName = null) {
  const triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(t => {
    if (!handlerName || t.getHandlerFunction() === handlerName) {
      ScriptApp.deleteTrigger(t);
    }
  });
}

function claimChest(place, totalClicks, totalConsume) {
  // Maintain safe balance: click_num >= consumed + 1000 + 5000
  const targetClick = Math.max(totalClicks + 1000, totalConsume + 6000);
  try {
    const resp = fetchWithRetry(SERVICE_BASE + "/api/frontend/chests/open", {
      method: "post",
      headers: getHeaders(),
      contentType: "application/json",
      payload: JSON.stringify({ place: place, click_num: targetClick }),
      muteHttpExceptions: true
    });
    const res = JSON.parse(resp.getContentText());
    res.targetClick = targetClick;
    return res;
  } catch (e) {
    Logger.log(`[-] Error claiming ${place} chest: ${e.message}`);
    return null;
  }
}

function scheduleNext(waitMs) {
  deleteTriggers("runAutoClaim");
  // Minimum 1 min on Google Apps Script, +5s buffer for server synchronization
  const delayMs = Math.max(60000, waitMs + 5000);
  const nextDate = new Date(Date.now() + delayMs);

  ScriptApp.newTrigger("runAutoClaim")
    .timeBased()
    .at(nextDate)
    .create();

  Logger.log(`[>>] Next run scheduled at: ${nextDate.toISOString()} (in ${formatDuration(delayMs / 1000)})`);
}

// ==========================================
// MAIN LOOP & USER CONTROLS
// ==========================================

function runAutoClaim() {
  Logger.log("=== CHECKING CHESTS (CLOUD 24/7) ===");
  const token = CONFIG.TOKEN ? CONFIG.TOKEN.trim() : "";
  if (!token || token === "YOUR_TOKEN_HERE") {
    Logger.log("[!] ERROR: Please paste your raw token into CONFIG.TOKEN in Code.gs!");
    return;
  }

  // Check for updates and notify Discord (with 24-hour rate limit)
  checkAndNotifyUpdate();

  // 1. Sync server time
  let timeOffset = 0;
  try {
    const rTime = fetchWithRetry(SERVICE_BASE + "/api/common/activity-config", { muteHttpExceptions: true });
    const jTime = JSON.parse(rTime.getContentText());
    if (jTime.code === 0 && jTime.data && jTime.data.server_time) {
      timeOffset = jTime.data.server_time - Date.now();
    }
  } catch (e) { }

  const now = Date.now() + timeOffset;

  // 2. Fetch player info
  let user;
  try {
    const rUser = fetchWithRetry(SERVICE_BASE + "/api/frontend/user/me", {
      headers: getHeaders(),
      muteHttpExceptions: true
    });
    const jUser = JSON.parse(rUser.getContentText());
    if (jUser.code === 10002 || jUser.code === 10003 || jUser.code === 90002) {
      Logger.log(`[!] SESSION TOKEN EXPIRED (Code ${jUser.code})! Please update your TOKEN.`);
      const webhook = CONFIG.DISCORD_WEBHOOK ? CONFIG.DISCORD_WEBHOOK.trim() : "";
      if (webhook) {
        fetchWithRetry(webhook, {
          method: "post",
          contentType: "application/json",
          payload: JSON.stringify({
            username: `Wuwa Tappo Auto Claim (GAS v${APP_VERSION})`,
            content: `⚠️ **Wuwa Tappo Auto Claim (GAS v${APP_VERSION})**: Session token expired! Please update your token in Google Apps Script.`
          }),
          muteHttpExceptions: true
        });
      }
      return;
    }
    if (jUser.code !== 0 || !jUser.data) {
      Logger.log("[-] Query user error: " + (jUser.message || JSON.stringify(jUser)));
      scheduleNext(300000); // Retry in 5 minutes
      return;
    }
    user = jUser.data;
  } catch (e) {
    Logger.log("[-] Network error: " + e.message);
    scheduleNext(180000); // Retry in 3 minutes
    return;
  }

  const nickname = user.nickname || "User";
  let totalClicks = user.total_click_count || 0;
  let totalConsume = user.total_click_consume || 0;
  let leftTs = user.left_treasure_chest || 0;
  let rightTs = user.right_treasure_chest || 0;

  Logger.log(`[+] User: ${nickname} | Balance: ${(totalClicks - totalConsume).toLocaleString()} clicks`);

  // 3. Claim Left Chest if ready
  if (now >= leftTs) {
    Logger.log("[*] Left Chest ready! Claiming...");
    const res = claimChest("left", totalClicks, totalConsume);
    if (res && res.code === 0) {
      const d = res.data || {};
      totalClicks = res.targetClick;
      totalConsume += (d.click_consume || 1000);
      leftTs = d.left_next_time || (now + 1800000);
      Logger.log(`[SUCCESS] Left Chest: ${d.asset_name} (${d.rarity_type}) | Balance: ${(totalClicks - totalConsume).toLocaleString()}`);
      sendDiscordWebhook(nickname, "left", d.asset_name, d.rarity_type, totalClicks - totalConsume,
        Math.max(0, Math.floor((leftTs - (Date.now() + timeOffset)) / 1000)),
        Math.max(0, Math.floor((rightTs - (Date.now() + timeOffset)) / 1000))
      );
    }
  }

  // 4. Claim Right Chest if ready
  if (now >= rightTs) {
    Logger.log("[*] Right Chest ready! Claiming...");
    const res = claimChest("right", totalClicks, totalConsume);
    if (res && res.code === 0) {
      const d = res.data || {};
      totalClicks = res.targetClick;
      totalConsume += (d.click_consume || 1000);
      rightTs = d.right_next_time || (now + 1800000);
      Logger.log(`[SUCCESS] Right Chest: ${d.asset_name} (${d.rarity_type}) | Balance: ${(totalClicks - totalConsume).toLocaleString()}`);
      sendDiscordWebhook(nickname, "right", d.asset_name, d.rarity_type, totalClicks - totalConsume,
        Math.max(0, Math.floor((leftTs - (Date.now() + timeOffset)) / 1000)),
        Math.max(0, Math.floor((rightTs - (Date.now() + timeOffset)) / 1000))
      );
    }
  }

  // 5. Schedule next run dynamically
  const currentTs = Date.now() + timeOffset;
  const leftWait = Math.max(0, leftTs - currentTs);
  const rightWait = Math.max(0, rightTs - currentTs);
  const minWait = Math.min(leftWait, rightWait);

  Logger.log(`[i] Wait times: Left = ${formatDuration(leftWait / 1000)} | Right = ${formatDuration(rightWait / 1000)}`);
  scheduleNext(minWait);
}

/**
 * Run this function once to start 24/7 cloud automation.
 */
function setup() {
  Logger.log("=== STARTING CLOUD AUTO CLAIM ===");
  checkAndNotifyUpdate();
  deleteTriggers(); // Clear all existing triggers to prevent conflicts

  // Create 2-hour recurring safety trigger to guarantee the trigger chain never breaks
  ScriptApp.newTrigger("safetyTrigger")
    .timeBased()
    .everyHours(2)
    .create();

  runAutoClaim();
}

/**
 * Periodic fallback trigger running every 2 hours to ensure continuous execution.
 */
function safetyTrigger() {
  Logger.log("[*] Safety trigger check running...");
  runAutoClaim();
}

/**
 * Run this function to stop all cloud triggers.
 */
function stopAutomation() {
  deleteTriggers();
  Logger.log("[+] All cloud triggers stopped.");
}

/**
 * Quick test to verify your token.
 */
function testToken() {
  Logger.log("=== TESTING TOKEN ===");
  try {
    const res = JSON.parse(fetchWithRetry(SERVICE_BASE + "/api/frontend/user/me", {
      headers: getHeaders(),
      muteHttpExceptions: true
    }).getContentText());

    if (res.code === 0 && res.data) {
      Logger.log("✅ SUCCESS!");
      Logger.log("👤 Player: " + res.data.nickname);
      Logger.log("📱 Device CID: " + getOrGenerateCID());
      Logger.log("🔘 Balance: " + (res.data.total_click_count - res.data.total_click_consume).toLocaleString() + " clicks");
      Logger.log("📦 Left: " + new Date(res.data.left_treasure_chest).toISOString());
      Logger.log("📦 Right: " + new Date(res.data.right_treasure_chest).toISOString());

      const update = checkForUpdates();
      if (update) {
        Logger.log(`📢 UPDATE AVAILABLE: Google Script v${update.version} (Current: v${APP_VERSION})`);
        Logger.log(`🔗 Source: ${update.source_url || ""}`);
      } else {
        Logger.log(`✨ Version: v${APP_VERSION} (Up to date)`);
      }
    } else {
      Logger.log("❌ FAILED: " + JSON.stringify(res));
    }
  } catch (e) {
    Logger.log("❌ ERROR: " + e.message);
  }
}
