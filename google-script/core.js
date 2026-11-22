/**
 * Wuwa Tappo Auto Claim - Google Apps Script Core Engine
 * Author: github.com/Triet2804Dev
 * Repository: https://github.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim
 */

var globalScope = typeof globalThis !== "undefined" ? globalThis : (typeof this !== "undefined" ? this : {});

globalScope.WuwaCore = (function() {
  const APP_VERSION = "1.0.2";
  const SERVICE_BASE = "https://api-wutheringwaves-wuwatappo.kurogames-global.com";

  function getOrGenerateCID() {
    const props = PropertiesService.getScriptProperties();
    let cid = props.getProperty("DEVICE_CID");
    if (!cid) {
      cid = Utilities.getUuid().replace(/-/g, "").toLowerCase();
      props.setProperty("DEVICE_CID", cid);
    }
    return cid;
  }

  function getHeaders(config) {
    const token = (config.TOKEN || "").replace(/^Bearer\s+/i, "").trim();
    return {
      "Authorization": "Bearer " + token,
      "X-BLM-CID": getOrGenerateCID(),
      "X-BLM-FRID": Utilities.getUuid().replace(/-/g, ""),
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36 Edg/157.0.0.0",
      "Origin": "http://tauri.localhost",
      "Referer": "http://tauri.localhost/",
      "Accept": "application/json, text/plain, */*",
      "Content-Type": "application/json"
    };
  }

  function fetchWithRetry(url, options = {}, config = {}) {
    const maxRetries = Math.max(1, (config && config.MAX_RETRIES) || 3);
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const resp = UrlFetchApp.fetch(url, options);
        const code = resp.getResponseCode();

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

  function sendDiscordWebhook(config, nickname, place, assetName, rarity, balance, leftSec, rightSec) {
    const webhook = config.DISCORD_WEBHOOK ? config.DISCORD_WEBHOOK.trim() : "";
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
      }, config);
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

  function claimChest(config, place, totalClicks, totalConsume) {
    const targetClick = Math.max(totalClicks + 1000, totalConsume + 6000);
    try {
      const resp = fetchWithRetry(SERVICE_BASE + "/api/frontend/chests/open", {
        method: "post",
        headers: getHeaders(config),
        contentType: "application/json",
        payload: JSON.stringify({ place: place, click_num: targetClick }),
        muteHttpExceptions: true
      }, config);
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
    // Minimum 1 min on Google Apps Script (Cloud trigger precision)
    const delayMs = Math.max(60000, waitMs);
    const nextDate = new Date(Date.now() + delayMs);

    ScriptApp.newTrigger("runAutoClaim")
      .timeBased()
      .at(nextDate)
      .create();

    Logger.log(`[>>] Next run scheduled at: ${nextDate.toISOString()} (in ${formatDuration(delayMs / 1000)})`);
  }

  function runAutoClaim(config) {
    Logger.log(`=== CHECKING CHESTS (CLOUD 24/7 v${APP_VERSION}) ===`);
    const token = config.TOKEN ? config.TOKEN.trim() : "";
    if (!token || token === "YOUR_TOKEN_HERE") {
      Logger.log("[!] ERROR: Please paste your raw token into CONFIG.TOKEN in Code.gs!");
      return;
    }

    // 1. Sync server time
    let timeOffset = 0;
    try {
      const rTime = fetchWithRetry(SERVICE_BASE + "/api/common/activity-config", { muteHttpExceptions: true }, config);
      const jTime = JSON.parse(rTime.getContentText());
      if (jTime.code === 0 && jTime.data && jTime.data.server_time) {
        timeOffset = jTime.data.server_time - Date.now();
      }
    } catch (e) { }

    const now = Date.now() + timeOffset;

    // 2. Fetch player info with cache-buster timestamp
    let user;
    try {
      const rUser = fetchWithRetry(SERVICE_BASE + "/api/frontend/user/me?t=" + Date.now(), {
        headers: getHeaders(config),
        muteHttpExceptions: true
      }, config);
      const jUser = JSON.parse(rUser.getContentText());
      if (jUser.code === 10002 || jUser.code === 10003 || jUser.code === 90002) {
        Logger.log(`[!] SESSION TOKEN EXPIRED (Code ${jUser.code})! Please update your TOKEN.`);
        const webhook = config.DISCORD_WEBHOOK ? config.DISCORD_WEBHOOK.trim() : "";
        if (webhook) {
          fetchWithRetry(webhook, {
            method: "post",
            contentType: "application/json",
            payload: JSON.stringify({
              username: `Wuwa Tappo Auto Claim (GAS v${APP_VERSION})`,
              content: `⚠️ **Wuwa Tappo Auto Claim (GAS v${APP_VERSION})**: Session token expired! Please update your token in Google Apps Script.`
            }),
            muteHttpExceptions: true
          }, config);
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

    // Monotonic persistence check: prevent stale CDN reads from downgrading clicks/consume
    const props = PropertiesService.getScriptProperties();
    const savedClicks = parseInt(props.getProperty("LAST_TOTAL_CLICKS") || "0", 10);
    const savedConsume = parseInt(props.getProperty("LAST_TOTAL_CONSUME") || "0", 10);
    if (savedClicks > totalClicks) totalClicks = savedClicks;
    if (savedConsume > totalConsume) totalConsume = savedConsume;

    Logger.log(`[+] User: ${nickname} | Balance: ${(totalClicks - totalConsume).toLocaleString()} clicks`);

    // 3. Claim Left Chest if ready
    if (now >= leftTs) {
      Logger.log("[*] Left Chest ready! Claiming...");
      const res = claimChest(config, "left", totalClicks, totalConsume);
      if (res && res.code === 0) {
        const d = res.data || {};
        totalClicks = res.targetClick;
        totalConsume += (d.click_consume || 1000);
        leftTs = d.left_next_time || (now + 1800000);
        props.setProperty("LAST_TOTAL_CLICKS", String(totalClicks));
        props.setProperty("LAST_TOTAL_CONSUME", String(totalConsume));
        Logger.log(`[SUCCESS] Left Chest: ${d.asset_name} (${d.rarity_type}) | Balance: ${(totalClicks - totalConsume).toLocaleString()}`);
        sendDiscordWebhook(config, nickname, "left", d.asset_name, d.rarity_type, totalClicks - totalConsume,
          Math.max(0, Math.floor((leftTs - (Date.now() + timeOffset)) / 1000)),
          Math.max(0, Math.floor((rightTs - (Date.now() + timeOffset)) / 1000))
        );
      }
    }

    // 4. Claim Right Chest if ready
    if (now >= rightTs) {
      Logger.log("[*] Right Chest ready! Claiming...");
      const res = claimChest(config, "right", totalClicks, totalConsume);
      if (res && res.code === 0) {
        const d = res.data || {};
        totalClicks = res.targetClick;
        totalConsume += (d.click_consume || 1000);
        rightTs = d.right_next_time || (now + 1800000);
        props.setProperty("LAST_TOTAL_CLICKS", String(totalClicks));
        props.setProperty("LAST_TOTAL_CONSUME", String(totalConsume));
        Logger.log(`[SUCCESS] Right Chest: ${d.asset_name} (${d.rarity_type}) | Balance: ${(totalClicks - totalConsume).toLocaleString()}`);
        sendDiscordWebhook(config, nickname, "right", d.asset_name, d.rarity_type, totalClicks - totalConsume,
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

  function setup(config) {
    Logger.log(`=== STARTING CLOUD AUTO CLAIM (v${APP_VERSION}) ===`);
    deleteTriggers();

    ScriptApp.newTrigger("safetyTrigger")
      .timeBased()
      .everyHours(2)
      .create();

    runAutoClaim(config);
  }

  function safetyTrigger(config) {
    Logger.log("[*] Safety trigger check running...");
    runAutoClaim(config);
  }

  function stopAutomation() {
    deleteTriggers();
    Logger.log("[+] All cloud triggers stopped.");
  }

  function testToken(config) {
    Logger.log(`=== TESTING TOKEN (v${APP_VERSION}) ===`);
    try {
      const res = JSON.parse(fetchWithRetry(SERVICE_BASE + "/api/frontend/user/me?t=" + Date.now(), {
        headers: getHeaders(config),
        muteHttpExceptions: true
      }, config).getContentText());

      if (res.code === 0 && res.data) {
        Logger.log("✅ SUCCESS!");
        Logger.log("👤 Player: " + res.data.nickname);
        Logger.log("📱 Device CID: " + getOrGenerateCID());
        Logger.log("🔘 Balance: " + (res.data.total_click_count - res.data.total_click_consume).toLocaleString() + " clicks");
        Logger.log("📦 Left: " + new Date(res.data.left_treasure_chest).toISOString());
        Logger.log("📦 Right: " + new Date(res.data.right_treasure_chest).toISOString());
        Logger.log(`✨ Version: v${APP_VERSION} (Managed via GitHub Loader)`);
      } else {
        Logger.log("❌ FAILED: " + JSON.stringify(res));
      }
    } catch (e) {
      Logger.log("❌ ERROR: " + e.message);
    }
  }

  return {
    setup: setup,
    runAutoClaim: runAutoClaim,
    safetyTrigger: safetyTrigger,
    stopAutomation: stopAutomation,
    testToken: testToken
  };
})();

var WuwaCore = globalScope.WuwaCore;
