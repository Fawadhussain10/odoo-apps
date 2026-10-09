# LinkedIn Sales Automation – AI Agents with Claude (Odoo 18)

AI-driven LinkedIn prospecting for one or many LinkedIn accounts, run from Odoo
and written by Claude. Warm leads land in Odoo CRM. Works on Odoo 18 Community
and Enterprise.

* **Odoo runs everything.** Personas, daily limits, send windows in each
  persona's time zone, working days, delay gaps, manual takeover, pivot to CRM,
  posts and logging all live in Odoo and are enforced by Odoo.
* **Claude writes.** Claude connects to Odoo through one custom connector (a
  URL, no API key, no extra Python package). It writes connection notes,
  questionnaire messages, follow-ups, handoffs and posts, and analyses replies.
  For each person it first reads their LinkedIn profile kept in Odoo, then
  their last reply, and only then writes.
* **Four agents.** A Connection Agent and a Chat Agent per persona, one shared
  Follow-up Agent and one shared Activity Agent, each with Run / Pause / Stop.

Customers are responsible for using LinkedIn in line with LinkedIn's terms.

---

## 1. Two ways of running

Each LinkedIn profile in Odoo chooses how its LinkedIn work is done.

| | **Built-in engine** (own server) | **Claude in Chrome** (Odoo.sh or anywhere) |
|---|---|---|
| Who clicks on LinkedIn | Odoo, in the background, with a browser it installs and runs itself | Claude, in your own Chrome, with the Claude in Chrome extension |
| What Claude does | Writes texts and analyses replies (a few seconds per call) | Writes, and does the LinkedIn steps Odoo hands out, one by one |
| Runs | All day, by itself; Claude only needs to write 1–3 times a day | Only while that computer and Chrome are on and Claude runs |
| Where | Self-hosted Odoo 18 (Linux) | Any Odoo 18, including Odoo.sh |
| Setup | Prepare engine (one click) + Connect LinkedIn inside Odoo | Chrome extension, signed in to the LinkedIn account |
| Rules (limits, windows, gaps, takeover) | Enforced by Odoo | Enforced by Odoo: Claude confirms every send first |

On Odoo.sh the module detects the platform and offers Claude in Chrome only.

## 2. Requirements

* Odoo 18 Community or Enterprise. Dependencies: `crm`, `calendar`, `mail`,
  `sales_team` (all standard).
* A Claude plan with custom connectors (Claude Pro or higher).
* **Built-in engine only:**
  * Self-hosted Linux server (x86_64 or arm64) with outbound internet access.
  * Browser system libraries: one command run once by a server administrator.
    Settings shows it, for example on Ubuntu 24.04:
    `sudo apt-get install -y libasound2t64 libatk-bridge2.0-0t64 libatk1.0-0t64 libatspi2.0-0t64 libcairo2 libcups2t64 libdbus-1-3 libexpat1 libgbm1 libglib2.0-0t64 libnspr4 libnss3 libpango-1.0-0 libudev1 libx11-6 libxcb1 libxcomposite1 libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 xvfb`
    (`xvfb` is optional: it lets the LinkedIn sign-in run with a window, which
    LinkedIn trusts more).
  * About 1 GB of RAM per connected LinkedIn account while its engine runs
    (allow up to 1.5 GB at peaks such as people searches), and about 1.1 GB of
    disk for the engine, its Python and its browser (shared by all accounts).
  * LinkedIn's interface language set to **English** on every engine account
    (Odoo reads LinkedIn pages by their English labels and checks this at
    Connect and Test connection).
* **Claude in Chrome only:** Google Chrome with the Claude in Chrome extension
  on the computer that does the LinkedIn work.

## 3. Setup – Built-in engine (own server)

1. **Install** the module (Apps → LinkedIn Sales Automation → Activate).
2. **Prepare the engine**: LinkedIn Sales → Configuration → Settings → LinkedIn
   engine → **Prepare engine**. Odoo downloads the open-source LinkedIn engine
   and its browser into its data folder (a few minutes, about 300 MB). Press
   **Refresh status** until it says **Ready**. If an administrator command is
   listed, have it run once on the server.
3. **Connector URL for Claude**: in the same Settings press **New connector
   URL** → Generate, and copy the URL (shown once; treat it like a password).
   In Claude: Settings → Connectors → **Add custom connector** → paste the URL →
   Authentication **No sign-in** → Add.
4. **LinkedIn profile**: LinkedIn Sales → LinkedIn Profiles → New. Name, the
   account's LinkedIn URL, owner, execution mode **Built-in engine** → Save.
5. **Connect LinkedIn**: press **Connect LinkedIn** → **Log in here** → **Open
   LinkedIn sign-in**. The real LinkedIn sign-in page appears inside Odoo: sign
   in, including any 2-step code. Odoo starts the engine, reads your own profile
   (display name, interface language) and shows **Connected**. Alternatives in
   the same dialog: **Import session** (sign in on your own computer with the
   engine's command and upload the session zip) and **Paste cookie**.
6. **Test connection** on the profile: "Connected as …", language English.
7. **Service, persona, agents**: Configuration → Services (what you sell),
   Personas → New (audience, job titles, locations, keywords, target time zone
   and working days, ideal customer, pain points), then the **Connection Agent**
   tab (daily limit, send window, delays, note with invite, follow when no
   Connect) and the **Chat Agent** tab (questionnaire steps, pivot criteria,
   handoff message, meeting link). Press **Run** on the agents.
8. **Follow-up and Activity Agents** (Configuration): follow-up steps for silent
   prospects; reply activities with a deadline for prospects you took over.

From now on Odoo searches LinkedIn, sends invites without notes, checks
acceptances, reads the inbox and replies, and sends approved texts — inside
each persona's send window and limits. Claude writes what needs writing.

## 4. Setup – Claude in Chrome (Odoo.sh or any Odoo)

1. Install the module; create the connector URL and add it to Claude (steps 1
   and 3 above).
2. LinkedIn profile with execution mode **Claude in Chrome** (the only mode on
   Odoo.sh).
3. On the computer that does the LinkedIn work: Chrome with the **Claude in
   Chrome** extension, signed in to that LinkedIn account (one Chrome profile
   per LinkedIn account). In Claude in Chrome, enable the Odoo connector.
4. Service, persona and agents as above.
5. Run the **Claude in Chrome** prompt from Settings. The first item makes
   Claude open your own LinkedIn profile to check it is the right account. Then
   Claude does each item — search, invite, check acceptance, inbox, message,
   publish post — and calls `li_confirm_send` before every click that sends or
   posts; it clicks only when Odoo answers **go**.

## 5. A day with each mode

**Built-in engine.** At 09:30 a scheduled Claude task writes the notes and
messages Odoo prepared (2–3 minutes). From 10:00 in each persona's time zone
Odoo sends them one at a time, keeping the random delay gap, re-reading each
conversation right before a message. It checks the inbox every hour (or as set)
and reads your newest connections every 15 minutes while invites are pending,
so an accepted invite shows as Accepted within about 15 minutes. When someone
is invited or accepts, Odoo keeps their LinkedIn profile on the prospect
(**LinkedIn profile** tab) and Claude reads it before writing to them. New
replies wait for Claude's next run (13:30, 16:30), which analyses them and
writes the next step. A reply
from someone you took over becomes an Odoo activity for the salesperson. At the
pivot Odoo creates the CRM lead and sends the handoff.

**Claude in Chrome.** With the computer on, a scheduled Claude task (or you)
runs the Chrome prompt 1–3 times a day inside the working hours. Claude checks
the account, then does the items Odoo hands out in order, reporting each. Odoo
keeps every limit; nothing is sent outside the windows.

## 6. Prompts (Settings → Prompts for Claude, with Copy buttons)

* **Run now – built-in engine**: "Run my LinkedIn agents now (Odoo connector).
  Call li_overview, then for every LinkedIn profile in Built-in engine mode call
  li_get_work and answer every writing item (li_submit_text, li_record_analysis,
  li_submit_post_draft) until li_get_work returns no items. Do not open
  LinkedIn: Odoo sends and reads by itself. Then call li_finish_run and give me
  a short summary per profile."
* **Send connections now – built-in engine**: Claude calls `li_send_now`
  (writing missing notes first) and reports with `li_sending_status`.
* **Answer replies now – built-in engine**: Claude calls `li_check_inbox_now`,
  analyses and answers, then `li_send_now` for messages.
* **Scheduled – built-in engine**: the run-now prompt for a Claude scheduled
  task, 1–3 times a day.
* **Run now / Scheduled – Claude in Chrome**: per profile, with the account
  check first and `li_confirm_send` before every click.

Plain requests work too, for example "send my connections now", "invite
https://www.linkedin.com/in/… from harvey", "answer my replies", "did they go
out?".

## 7. What Odoo enforces

* Daily limits per agent (and an optional weekly limit and total target), send
  windows and working days in each persona's **target time zone**, a random
  delay gap between sends per LinkedIn account.
* LinkedIn's weekly invitation limit: Odoo reads LinkedIn's own notice and
  pauses that account's Connection Agents until next week. If LinkedIn stops
  recording invitations without saying why (two different people in a row),
  invites pause for a day and try again by themselves. A restriction pauses the
  account and tells the owner.
* A person LinkedIn only lets you invite with their email address is followed
  instead (or flagged), without retries.
* Before writing, Claude gets each person's LinkedIn profile from Odoo and is
  told to work in a fixed order: read the profile, read the last reply and
  judge its nature, and only then write so the text fits the person's real role
  and what they said. The same order is in the tool descriptions, in every
  item and in the prompts.
* Every message is sent only after a fresh read of its conversation: a new
  reply drops the queued text (stale), and a message you write by hand on
  LinkedIn takes the prospect over. LinkedIn's own interface text (banners,
  quick-reply suggestions) is never read as a message.
* Manual takeover (button, message written by hand, or pivot) stops every agent
  for that prospect only.
* Do-not-contact list across all personas; "not interested" stops the sequence.
* A send whose outcome is unknown is never repeated; the prospect is flagged for
  a person to check.
* Engine accounts: a daily read budget (default 150 pages) shared by searches,
  inbox, conversations and acceptance checks; one action at a time per account.
* Follow-only profiles (no Connect): followed instead, if the agent allows it.

## 8. Posts and dashboard

* **Posts**: add a **Post idea** (title, idea, optional image, publish time).
  Claude drafts it at its next run; the profile owner or a manager approves;
  Odoo publishes it at the chosen time (engine) or hands Claude a
  `publish_post` item (Chrome). The post URL is saved and reactions, comments
  and reposts are re-read weekly.
* **Prospect profile**: each prospect has a **LinkedIn profile** tab with the
  text of their profile page, saved when they are invited (or read once when
  they reach the Chat Agent). Claude reads it from there, not from LinkedIn.
* **Dashboard** (refreshes every minute): account health per profile, work queue (waiting for Claude,
  approved texts with the next window, sent today, discarded as stale), last
  Claude run, KPIs (invites, acceptance, replies, warm leads, meetings,
  follow-ups, posts; people who were already your connections are shown beside
  the acceptance rate, not in it), invites per day, funnel, a per-persona table, a world
  map of where your prospects are, and filters by date, profile, persona,
  service, agent and execution mode.

## 9. FAQ

* **The sign-in inside Odoo does not work / LinkedIn asks for a security
  check.** Use **Import session**: on your own computer install `uv`, run
  `uvx mcp-server-linkedin@4.26.2 --login`, sign in, zip `cookies.json` and
  `source-state.json` from `~/.linkedin-mcp`, upload the zip. Delete the zip
  afterwards.
* **Reconnect needed.** LinkedIn ended the session. Its agents pause and the
  owner gets an activity. Press **Reconnect LinkedIn** (engine) or sign in to
  LinkedIn in Chrome (Chrome mode); then run the agents again.
* **"Weekly invitation limit".** LinkedIn's own weekly cap, lower on new
  accounts. Odoo reads LinkedIn's notice, pauses that account's Connection
  Agents until next Monday and resumes them by itself. Messages to people who
  accepted keep going out.
* **Invites are paused for a day.** LinkedIn did not record invitations to two
  different people in a row and gave no reason. Odoo pauses that account's
  invites for 24 hours and tries again by itself; leave it paused.
* **A prospect shows Taken over although I did not press the button.** Someone
  wrote to that person by hand on LinkedIn from the account. Odoo stops the
  agents for that person only. A manager can press **Return to agents**.
* **Replies are picked up slowly.** The inbox is read every 60 minutes by
  default. Set **Check inbox every** to 20 or 30 minutes in Settings and raise
  the daily read budget (for example 250), or ask Claude to answer replies now.
* **The acceptance rate does not count someone who is connected.** It counts
  invitations Odoo sent. People who were already your connections are shown
  beside it as "already connected" and are still handled by the Chat Agent.
* **Scheduled actions stop on a server with many databases.** Without workers,
  Odoo only runs scheduled actions for databases opened since its last restart.
  Run Odoo with workers (`workers` and `max_cron_threads` in the configuration
  file, plus the `/websocket` route in the proxy): its cron workers then go
  through every database.
* **Claude in Chrome keeps asking for permission.** Choose **Always allow** for
  linkedin.com (and your Odoo address) in the extension.
* **Claude says there is nothing to do.** Normal for engine profiles when nobody
  accepted or replied since the last run and no notes are needed: Odoo keeps
  working in the background. Ask "did my invites go out?" for a status.
* **The engine is stopped.** The watchdog restarts engines every 5 minutes; you
  can press **Start engine**. Engines also stop on purpose when a session
  expires or LinkedIn restricts the account.
* **"Set LinkedIn's language to English".** Engine accounts must use LinkedIn in
  English; change it in LinkedIn's settings, then press Test connection.
* **Sending looks slower than planned.** One send at a time with the random
  delay gap: five invites take several minutes.
* **Claude does not see a new tool after an update.** Restart Odoo and upgrade
  the module, then in Claude open Settings → Connectors → the Odoo connector and
  make sure every tool is enabled (tools added later can stay switched off), or
  remove and add the connector again with the same URL.
* **Claude used another LinkedIn tool.** Odoo's instructions tell Claude to use
  only this connector; in a chat, keep other LinkedIn connectors off.
* **Can a message have line breaks?** Messages are sent as one paragraph
  (LinkedIn would send on Enter); posts keep their line breaks.

## 10. Security and privacy

* The connector URL holds a random token (stored hashed, shown once, revocable;
  blanked out of Odoo's request log). Tools run as a technical user with its
  own group.
* LinkedIn passwords and codes typed in the sign-in dialog are never logged or
  stored; the session stays in the engine's own folder on your server
  (permissions 700). Each engine listens on 127.0.0.1 only, on a random secret
  path, one per account.
* The prospects map works offline: no map or geocoding service is called.

## 11. Credits

* LinkedIn engine: [linkedin-mcp-server](https://github.com/stickerdaniel/linkedin-mcp-server)
  (`mcp-server-linkedin` 4.26.2), Apache License 2.0. Downloaded unmodified by
  **Prepare engine**; its LICENSE and NOTICE are kept next to the install.
* Map: Natural Earth 1:110m (public domain) via world-atlas 2.0.2 (ISC);
  places: GeoNames (CC BY 4.0). See `data/geo/NOTICE`.

## 12. Support

PackBytes — <https://packbytes.com> — sales@packbytes.com — WhatsApp +92 301 0400131
