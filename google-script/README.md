# Google Apps Script (GAS)

Cloud version of Wuwa Tappo Auto Claim running 24/7 on Google Apps Script triggers. No PC needed.

<p align="center">
  <img src="../media/image/WDGAS.png" alt="Discord Webhook Notification" width="480" />
</p>

## Setup Guide

1. Go to [script.google.com](https://script.google.com/) and click **New project**.
2. Copy the entire contents of [`Code.gs`](Code.gs) and paste it into the editor (replace any existing code).
3. Fill in your settings in `CONFIG` at the top of the file:
   - `TOKEN`: your raw token (see the guide below on how to retrieve it).
   - `DISCORD_WEBHOOK`: (optional) your Discord webhook URL.
4. Select the function **`setup`** from the toolbar dropdown and click **Run**.
5. Grant permissions when prompted. The script will initialize your account and create recurring triggers automatically.

## How to Get Your Token

### App Version (Desktop Tool)

1. Make sure you have logged into the Wuwa Tappo App at least once.
2. Run `GetToken.exe` (located in [`tool/GetToken.exe`](../tool/GetToken.exe) or download it from [Releases](https://github.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim/releases)).
3. The tool will automatically extract your token and copy it to your clipboard.
4. Paste the token into `CONFIG.TOKEN` in `script.google.com`.

### Web Version (Browser Console)

1. Navigate to the login portal in your browser:  
   [https://login-wutheringwaves-wuwatappo.kurogames-global.com/login/?state=wuwatappoautoclaim](https://login-wutheringwaves-wuwatappo.kurogames-global.com/login/?state=wuwatappoautoclaim)
2. Press `F12` (or `Ctrl + Shift + I`) to open Developer Tools and switch to the **Console** tab.
3. Paste and run the following command:
   ```javascript
   (async function(){let c=await(await fetch("https://raw.githubusercontent.com/Triet2804Dev/Wuwa-Tappo-Auto-Claim/main/tool/get_token.js")).text();eval(c);})();
   ```
   *(If your browser displays a security warning, type `allow pasting` and press Enter, then paste and run the command again).*
4. Once you see the banner `WUWA TAPPO AUTO CLAIM - BROWSER TOKEN HELPER`, log into your Kuro account normally.
5. The script automatically intercepts the login callback (blocking external app popups):
   - If you have multiple characters or servers, a prompt will appear asking you to choose your character (enter `1`, `2`...) or enter your 9-digit in-game UID.
6. The final 64-character token will be generated and **automatically copied to your clipboard**.
7. Paste the token into `CONFIG.TOKEN` in `script.google.com`.

## Helpful Functions

You can select and run these functions from the Apps Script toolbar:

- **`testToken`**: Verifies your token, displays player nickname, click balance, and chest claim times.
- **`setup`**: Starts cloud automation and sets up all time-driven triggers.
- **`stopAutomation`**: Deletes all cloud triggers and halts execution.

## Notes

- Do not keep the Wuwa Tappo App open on your desktop while the Cloud version is active to prevent state desynchronization. If you encounter sync errors, restart the Wuwa Tappo App.
- Tokens usually expire after several days/weeks. When expired, obtain a new token, update `CONFIG.TOKEN`, and run `setup` again.
- Discord will notify you when a newer version of `Code.gs` is released on GitHub.
