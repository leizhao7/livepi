# Fastmail Email Setup for LivePI Experiments

This guide sets up a Fastmail mailbox for the email experiments and configures LivePI so it can send, receive, and inject benchmark emails reliably.

The experiments previously hit Fastmail's daily SMTP sending limit. For benchmark runs, the recommended setup is to receive mail through IMAP and inject test emails with IMAP `APPEND`, which avoids consuming SMTP send quota for every test case.

## 1. Create or Choose a Fastmail Mailbox

1. Sign in to Fastmail or create a Fastmail account at `https://www.fastmail.com`.
2. Choose the mailbox that LivePI will use for the experiment recipient.
3. Keep the mailbox inbox mostly empty before running a sweep so the agent reads only experiment mail.

Use a dedicated test mailbox if possible. Do not use a personal mailbox.

## 2. Create a Fastmail App Password

Fastmail requires an app password for IMAP and SMTP access. Do not use your Fastmail web login password in `.env`.

1. Open Fastmail settings.
2. Go to `Privacy & Security`.
3. Open `Connected apps & API tokens`.
4. Create a new app password.
5. Give it access to mail, including IMAP and SMTP.
6. Copy the generated app password and store it in `prompt_injection_lab/.env`.

Official Fastmail reference: `https://www.fastmail.help/hc/en-us/articles/360058752854-App-passwords`

## 3. Configure Receiving with IMAP

Fastmail IMAP settings:

```env
IMAP_HOST=imap.fastmail.com
IMAP_PORT=993
IMAP_SECURE=true
IMAP_USER=your_fastmail_address@fastmail.com
IMAP_PASS=your_fastmail_app_password
IMAP_MAILBOX=INBOX
```

Official Fastmail server reference: `https://www.fastmail.help/hc/en-us/articles/1500000278342-Server-names-and-ports`

## 4. Configure Sending with SMTP

Fastmail SMTP settings:

```env
SMTP_HOST=smtp.fastmail.com
SMTP_PORT=465
SMTP_SECURE=true
SMTP_STARTTLS=false
SMTP_USER=your_fastmail_address@fastmail.com
SMTP_PASS=your_fastmail_app_password
SMTP_FROM=your_fastmail_address@fastmail.com
```

Port `465` uses implicit TLS. Fastmail also supports port `587` with STARTTLS, but the experiments are configured around port `465`.

Official Fastmail IMAP/SMTP reference: `https://www.fastmail.help/hc/en-us/articles/1500000279921-IMAP-POP-and-SMTP`

## 5. Enable IMAP Append Injection for Sweeps

For these experiments, use IMAP append for benchmark injection emails:

```env
LIVEPI_EMAIL_INJECT_METHOD=imap_append
BENCHMARK_ATTACKER_EMAIL=attacker@example.test
```

With this setting, LivePI appends synthetic attack emails directly into the recipient mailbox over IMAP instead of sending every benchmark injection through SMTP. This avoids Fastmail's outbound daily send quota during sweeps.

`BENCHMARK_ATTACKER_EMAIL` controls the apparent sender address in injected test emails. It does not need to be a real mailbox when using `imap_append`.

## 6. Optional: Configure a Separate Attacker SMTP Account

If you want attack emails to be sent over SMTP instead of appended through IMAP, configure a separate sender account:

```env
LIVEPI_EMAIL_INJECT_METHOD=smtp

ATTACKER_SMTP_HOST=smtp.fastmail.com
ATTACKER_SMTP_PORT=465
ATTACKER_SMTP_SECURE=true
ATTACKER_SMTP_STARTTLS=false
ATTACKER_SMTP_USER=attacker_fastmail_address@fastmail.com
ATTACKER_SMTP_PASS=attacker_fastmail_app_password
ATTACKER_SMTP_FROM=attacker_fastmail_address@fastmail.com
```

This still counts against the sender account's Fastmail SMTP quota. Use `imap_append` for long benchmark sweeps.

## 7. Test the Mailbox Configuration

From the repo root:

```powershell
.venv\Scripts\python.exe prompt_injection_lab\scripts\check_imap_login.py --env-file prompt_injection_lab\.env --verify
```

This verifies that the app can connect to the configured Fastmail mailbox through IMAP.

## 8. Run or Resume the Email Sweep

Start the local gateway, then resume the sweep:

```powershell
.openclaw-livepi\start-gateway.ps1

.venv\Scripts\python.exe prompt_injection_lab\scripts\sweep_email_gmail_local.py `
  --resume C:\Git\livePI\prompt_injection_lab\results\sweep_email_gmail_local_20260602_212852 `
  --agent openclaw `
  --gateway-ws-url ws://127.0.0.1:18789/ws `
  --chat-timeout-s 420 `
  --case-timeout-s 900 `
  --env-file prompt_injection_lab\.env
```

After the run completes, stop the gateway if it is no longer needed.

## 9. Expected Result

With `LIVEPI_EMAIL_INJECT_METHOD=imap_append`, the prior sweep completed successfully:

```text
total_runs=50
completed_rows=50
ok_count=50
error_count=0
attack_success=0
ASR=0%
```

The important behavioral change is that benchmark email injection no longer depends on Fastmail SMTP quota.

