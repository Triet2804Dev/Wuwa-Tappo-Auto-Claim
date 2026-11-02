// ========================================================================
// Wuwa Tappo Auto Claim - Browser Token Helper (F12 Console Snippet)
// Author: github.com/Triet2804Dev
// Repository: https://github.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim
// ========================================================================

(function () {
    "use strict";

    let isProcessing = false;
    let isCompleted = false;

    // Stylish console styling helpers
    const STYLES = {
        banner: "color: #00e5ff; font-weight: bold; font-family: monospace; font-size: 11px;",
        title: "color: #00ff88; font-weight: bold; font-size: 13px;",
        info: "color: #00e5ff; font-weight: bold;",
        step: "color: #ffb700; font-weight: bold;",
        success: "color: #00ff88; font-weight: bold;",
        blocked: "color: #ff5252; font-weight: bold;",
        tokenBox: "color: #fff; font-size: 15px; font-weight: bold; background: #1a1a2e; border: 1px solid #00ff88; padding: 6px 10px; border-radius: 6px; font-family: monospace;"
    };

    console.log(
        `%c` +
        `========================================================================\n` +
        `             WUWA TAPPO AUTO CLAIM - BROWSER TOKEN HELPER               \n` +
        `                      github.com/Triet2804Dev                           \n` +
        `========================================================================`,
        STYLES.banner
    );
    console.log("%c[*] Waiting for login or SDK callback...", STYLES.info);
    console.log("%c[*] Protocol interception active: 'wuwa-buddy://' calls will be captured and blocked.", "color: #aaa; font-style: italic;");

    /**
     * Parse credentials from wuwa-buddy:// URL.
     */
    function parseCallbackUrl(urlStr) {
        try {
            const normalized = urlStr.replace(/^wuwa-buddy:\/\/[^?]*\?/i, "https://dummy.local/?");
            const parsed = new URL(normalized);
            const params = parsed.searchParams;
            const accessToken = params.get("access_token");
            const cuid = params.get("cuid");
            const userId = params.get("userId") || (cuid ? `U${cuid}A` : null);
            const userName = params.get("userName") || userId;

            if (accessToken && cuid) {
                return { accessToken, cuid, userId, userName };
            }
        } catch (e) {
            // Fallback manual regex parser
            const matchAt = urlStr.match(/access_token=([^&]+)/i);
            const matchCuid = urlStr.match(/cuid=([^&]+)/i);
            const matchUid = urlStr.match(/userId=([^&]+)/i);
            const matchUname = urlStr.match(/userName=([^&]+)/i);

            if (matchAt && matchCuid) {
                const cuid = decodeURIComponent(matchCuid[1]);
                return {
                    accessToken: decodeURIComponent(matchAt[1]),
                    cuid: cuid,
                    userId: matchUid ? decodeURIComponent(matchUid[1]) : `U${cuid}A`,
                    userName: matchUname ? decodeURIComponent(matchUname[1]) : `U${cuid}A`
                };
            }
        }
        return null;
    }

    /**
     * Intercept callback URL, suppress external protocol popups, and extract tokens.
     */
    function handleCallbackUrl(url) {
        if (typeof url !== "string") return false;
        if (!url.toLowerCase().startsWith("wuwa-buddy://") && !url.includes("access_token=")) return false;

        console.log("%c[!] Intercepted and blocked external protocol call:%c " + url.split("?")[0], STYLES.blocked, "color: #ffb700;");

        const creds = parseCallbackUrl(url);
        if (creds && !isProcessing && !isCompleted) {
            exchangeToken(creds.accessToken, creds.cuid, creds.userId, creds.userName);
        }
        return true;
    }

    /**
     * Exchange short-lived SDK credentials for the permanent 64-character session token.
     */
    async function exchangeToken(accessToken, cuid, userId, userName) {
        if (isProcessing || isCompleted) return;
        isProcessing = true;

        const API = "https://api-wutheringwaves-wuwatappo.kurogames-global.com";

        try {
            console.log(`%c[1/2] Fetching character info for CUID: ${cuid}...`, STYLES.step);

            // 1. Query player character data from Kuro API
            const resPlayer = await fetch(API + "/api/auth/player/query", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cuid: String(cuid), is_domestic: 0 })
            });
            const playerData = await resPlayer.json();
            if (playerData.code !== 0 || !playerData.data?.items?.length) {
                throw new Error("No character found for this account! (" + JSON.stringify(playerData) + ")");
            }

            const char = playerData.data.items[0];
            const channelId = playerData.data.channelId || 18;
            console.log(`%c[+] Found Character: ${char.playerName} (ID: ${char.playerId})`, STYLES.success);

            // 2. Exchange credentials for final 64-character token
            console.log("%c[2/2] Generating final 64-char Token...", STYLES.step);
            const resLogin = await fetch(API + "/api/auth/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    cuid: String(cuid),
                    puid: String(cuid),
                    channelId: channelId,
                    userid: String(userId || cuid),
                    cname: String(char.playerName || userName || cuid),
                    accessToken: String(accessToken),
                    source: "sdk",
                    playerId: char.playerId,
                    serverId: String(char.serverId),
                    is_domestic: 0
                })
            });
            const loginData = await resLogin.json();
            if (loginData.code !== 0 || !loginData.data?.token) {
                throw new Error("Token generation failed: " + JSON.stringify(loginData));
            }

            const finalToken = loginData.data.token;
            isCompleted = true;

            // Output formatted results to console
            console.log(
                `%c` +
                `========================================================================\n` +
                `                      LOGIN SUCCESSFUL! FINAL TOKEN                     \n` +
                `========================================================================`,
                STYLES.success
            );
            console.log(`%c${finalToken}`, STYLES.tokenBox);
            console.log(
                `%c` +
                `========================================================================`,
                STYLES.success
            );

            console.log("%c[!] Please copy your 64-character token above manually (Ctrl+C).", STYLES.step);

            // Display browser prompt dialog pre-filled with the token for manual copy
            prompt(
                `WUWA TAPPO AUTO CLAIM - LOGIN SUCCESSFUL!\n\n` +
                `Player: ${char.playerName} (ID: ${char.playerId})\n\n` +
                `Please copy your 64-character token below (Ctrl+C):`,
                finalToken
            );

        } catch (err) {
            console.error("%c[-] Token exchange error:", STYLES.blocked, err);
            alert("Token generation error: " + (err.message || err));
        } finally {
            isProcessing = false;
        }
    }

    // ========================================================================
    // EXTERNAL PROTOCOL BLOCKER & INTERCEPTORS
    // ========================================================================

    // 1. Intercept window.open
    const _origOpen = window.open;
    window.open = function (url, ...args) {
        if (typeof url === "string" && handleCallbackUrl(url)) {
            return null;
        }
        return _origOpen.apply(this, [url, ...args]);
    };

    // 2. Intercept window.location.assign and window.location.replace
    try {
        const _origAssign = window.location.assign;
        window.location.assign = function (url) {
            if (typeof url === "string" && handleCallbackUrl(url)) return;
            return _origAssign.call(window.location, url);
        };
    } catch (e) {}

    try {
        const _origReplace = window.location.replace;
        window.location.replace = function (url) {
            if (typeof url === "string" && handleCallbackUrl(url)) return;
            return _origReplace.call(window.location, url);
        };
    } catch (e) {}

    // 3. Intercept Location.prototype.href if configurable
    try {
        const _locHrefDesc = Object.getOwnPropertyDescriptor(Location.prototype, "href");
        if (_locHrefDesc && _locHrefDesc.set) {
            Object.defineProperty(Location.prototype, "href", {
                set: function (val) {
                    if (typeof val === "string" && handleCallbackUrl(val)) return;
                    return _locHrefDesc.set.call(this, val);
                },
                get: function () {
                    return _locHrefDesc.get.call(this);
                }
            });
        }
    } catch (e) {}

    // 4. Intercept <a> anchor clicks (DOM event capturing)
    window.addEventListener(
        "click",
        function (e) {
            const target = e.target && e.target.closest ? e.target.closest("a") : null;
            if (target && target.href && handleCallbackUrl(target.href)) {
                e.preventDefault();
                e.stopPropagation();
                e.stopImmediatePropagation();
            }
        },
        true
    );

    // 5. Intercept HTMLAnchorElement.prototype.click
    try {
        const _origClick = HTMLAnchorElement.prototype.click;
        HTMLAnchorElement.prototype.click = function () {
            if (this.href && handleCallbackUrl(this.href)) {
                return;
            }
            return _origClick.apply(this, arguments);
        };
    } catch (e) {}

    // 6. Intercept <iframe> src changes (used by some SDK redirectors)
    try {
        const _iframeSrcDesc = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, "src");
        if (_iframeSrcDesc && _iframeSrcDesc.set) {
            Object.defineProperty(HTMLIFrameElement.prototype, "src", {
                set: function (val) {
                    if (typeof val === "string" && handleCallbackUrl(val)) return;
                    return _iframeSrcDesc.set.call(this, val);
                },
                get: function () {
                    return _iframeSrcDesc.get.call(this);
                }
            });
        }
    } catch (e) {}

    // 7. Intercept Chromium Navigation API if supported
    if (window.navigation && typeof window.navigation.addEventListener === "function") {
        try {
            window.navigation.addEventListener("navigate", function (e) {
                const dest = e.destination ? e.destination.url : "";
                if (dest && handleCallbackUrl(dest)) {
                    e.preventDefault();
                }
            });
        } catch (e) {}
    }

    // 8. Listen for SDK postMessage events
    window.addEventListener("message", async function (e) {
        if (e.data && e.data.data && e.data.data.access_token) {
            const d = e.data.data;
            await exchangeToken(d.access_token, d.cuid, d.userId, d.userName);
        }
    });

})();
