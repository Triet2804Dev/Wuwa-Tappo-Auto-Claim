/**
 * Wuwa Tappo Auto Claim - Google Apps Script (24/7 Cloud Loader)
 * Author: github.com/Triet2804Dev
 * Repository: https://github.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim
 * 
 * This loader fetches and executes the latest core engine directly from GitHub.
 * You will receive automatic updates and bug fixes without needing to copy-paste code again.
 */

// ==========================================
// CONFIGURATION
// ==========================================
const CONFIG = {
  // Enter your raw 64-character token here (e.g. from GetToken.exe or web console helper)
  TOKEN: "YOUR_TOKEN_HERE",

  // Maximum retry attempts for API and Discord calls (against rate limits and network drops)
  MAX_RETRIES: 3,

  // Discord Webhook URL for reward notifications (optional, leave empty "" if not used)
  DISCORD_WEBHOOK: "",
};

// Remote core engine URL on GitHub (main branch)
const REMOTE_CORE_URL = "https://raw.githubusercontent.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim/main/google-script/core.js";

/**
 * Loads and executes core logic dynamically from GitHub with caching.
 */
function _execCore(funcName) {
  const cache = CacheService.getScriptCache();
  let code = cache.get("WUWA_CORE_JS");
  if (!code) {
    const resp = UrlFetchApp.fetch(REMOTE_CORE_URL + "?t=" + Date.now(), { muteHttpExceptions: true });
    if (resp.getResponseCode() !== 200) {
      throw new Error("Failed to fetch core.js from GitHub (HTTP " + resp.getResponseCode() + ")");
    }
    code = resp.getContentText();
    // Cache for 6 hours (21600 seconds)
    cache.put("WUWA_CORE_JS", code, 21600);
  }
  eval(code);
  if (typeof WuwaCore === "undefined" || typeof WuwaCore[funcName] !== "function") {
    throw new Error("WuwaCore." + funcName + " is not defined in core.js");
  }
  return WuwaCore[funcName](CONFIG);
}

// ==========================================
// USER CONTROLS & TIME-DRIVEN TRIGGERS
// ==========================================

function setup() {
  _execCore("setup");
}

function runAutoClaim() {
  _execCore("runAutoClaim");
}

function safetyTrigger() {
  _execCore("safetyTrigger");
}

function stopAutomation() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  Logger.log("[+] All cloud triggers stopped.");
}

function testToken() {
  _execCore("testToken");
}

/**
 * Force clear cached core code to immediately fetch the freshest code from GitHub.
 */
function reloadCore() {
  CacheService.getScriptCache().remove("WUWA_CORE_JS");
  Logger.log("[+] Core cache cleared. Fresh core.js will be loaded from GitHub on next run.");
}
