# Anchorpoint: the three-minute demo

For whoever presents. One person talks, one person drives the browser. No slides: the app is the pitch.

Site: <https://172-232-25-241.sslip.io>

## The one idea to land

**Rules decide. The agent reads and explains. Every record traces to its source.**

If the judges remember one sentence, it should be that. Everything below is there to show it three times: in the ledger, in the blocked attack email, and in the contract verdict.

## Before you go up

Do these in order. Allow 20 minutes.

| When | Do | Why |
| --- | --- | --- |
| T-20 min | Ask P4 to confirm the server is on the final version and the smoke test is green | No deploys after this |
| T-20 min | Press **Reset demo** once (sidebar), then leave the site alone for 10 minutes | The first reset after a deploy re-reads the inbox through the model and takes several minutes |
| T-10 min | Open **Overview**. Check: score in the 50s, "needs attention", 2 of 3 factors, a gap in the chart at June | This is your opening screen |
| T-10 min | Open **Connections**. Check Gmail and Bank both say connected | The bank drops on every restart. If it is not connected, click Connect on the Bank card and wait 30 seconds |
| T-5 min | Open **Contract check**, click **Use sample offer**, do not submit. Leave this tab open | The offer is ready to run |
| T-5 min | Open a second tab on **Overview** | You start here |
| T-2 min | Browser at 100% zoom, full screen, notifications off, laptop charging | |

**Do not press Reset demo during the demo.** It empties the screen.

**Do not click "Send a live email" more than once.** Each click puts a real email in the inbox.

## The script

Times are targets. The contract check is the only step with a wait, so keep talking through it.

### 0:00 to 0:25. The problem, on the Overview page

**Say:**
"Meet Maya, a travel ICU nurse. Half her pay is tax-free stipends, but only if she can prove she keeps a real home in Kansas City. If she can't, all of it becomes taxable. The IRS judges that on three factors, and on evidence."

**Show:** the score, the three factor bars, then point at the chart.

**Say:**
"Anchorpoint says she needs attention. Look at June: she paid for housing in Denver, and there's no proof she paid rent at home."

**Hit:** the gap in the chart. It is the most visual thing in the product.

### 0:25 to 0:55. She connected once; the agent did the rest

**Do:** click **Connections**.

**Say:**
"She connected her Gmail and her bank once, read-only. She never typed any of this in."

**Do:** click **Agent activity**.

**Say:**
"This is the agent working: what it found, what it filed, what it skipped as junk."

**Do:** point at the entry marked **Blocked**.

**Say:**
"And this one. Someone emailed her inbox with instructions telling the AI to confirm every record and send her ledger out. It was blocked and logged. We treat every email as hostile input."

**Hit:** the Blocked entry. Security is a third of what makes this believable.

### 0:55 to 1:35. Every record traces to its source

**Do:** click **Records**.

**Say:**
"Every piece of evidence, each with where it came from. Notice the two icons: this rent payment was found in her email and in her bank. Two independent sources for one payment."

**Do:** click a rent payment row. The drawer opens.

**Say:**
"The source text, a link back to the original email, how confident the agent was, and the audit trail."

**Do:** close it. Click **Needs review**. A handful of rows appear. Open the **rent payment** dated April.

**Say:**
"The agent flagged this one itself. It's a rent receipt, but look at the address: Unit 5, not Maya's Unit 3. It's her old roommate's. The agent wasn't sure, so it asked."

**Do:** click **Reject**.

**Say:**
"She rejects it, and it no longer counts."

**Hit:** the agent admitting doubt. It is more convincing than the agent being right.

### 1:35 to 1:55. It keeps working

**Do:** in the sidebar, click **Send a live email** once. Then click **Sync now** in the header.

**Say:**
"A new electricity bill just arrived in her real inbox. The agent is reading it now, with a live model call."

**Do:** open **Agent activity** and wait for the new entry. It takes 5 to 15 seconds.

**Say, while it loads:**
"This runs on AWS Strands Agents, with the model hosted on Akamai Cloud."

**If it has not appeared after 15 seconds:** say "it will be there in a moment" and move on. Do not wait.

### 1:55 to 2:40. The warning before she signs

**Do:** switch to the tab with the sample offer ready. Click **Check this contract**.

**Say, while it runs (10 to 30 seconds):**
"Her recruiter offers four more months in Denver, at a higher stipend. Before she signs, she pastes it in. The verdict comes from tax rules written as tested code, not from the AI. The AI's only job is to explain the result in plain English."

**When it returns, say:**
"High risk. She's been in Denver 45 weeks. This offer takes her past a year, and past a year the IRS no longer calls it temporary. The stipend is also above the federal ceiling. And here are the questions to take to her CPA."

**Hit:** the words "the verdict comes from rules, not from the AI". Say them even if you cut everything else.

**Optional, only if you have 20 seconds spare:** change the End date in the offer to `2026-11-30` and run it again. The verdict drops to "review with CPA". This proves it reads the offer.

### 2:40 to 3:00. Close

**Do:** go back to **Overview**.

**Say:**
"Maya went from a shoebox of emails to knowing exactly which month to go find, and to not signing a contract that would have cost her thousands. The same test applies to contract engineers and construction crews, and the staffing agencies that pay them carry the same exposure. Real Gmail, real Plaid, real rules. The data is synthetic; everything else is live."

## If something goes wrong

| Problem | Do this |
| --- | --- |
| A page is empty or shows no score | Someone reset it. Say "we just reset the demo, it refills from her inbox", go to **Agent activity** and show it filling. Then skip to the contract check |
| The contract check spins past 40 seconds | Keep talking. If it fails, go to the **Offered assignment** tab on the same page and run that instead |
| "Send a live email" shows an error | Skip the step. Say "a new email would appear here within a minute" |
| The site will not load | Switch to the laptop fallback: `docker compose up -d` on the presenter's machine, then <http://localhost>. It shows sample records, so say so |
| A judge asks to see Google sign-in | On **Connections**, show the read-only scopes listed. Do not disconnect and reconnect live: Google shows an "unverified app" warning for test-mode apps |

## What not to click

- **Reset demo:** wipes the ledger.
- **Revoke** on a connection: disconnects Gmail or the bank.
- **Connect** or **Revoke** on any card, Calendar included. All three are connected; leave them.
- Typing an offer by hand: the check reads a labelled format. Use the sample and edit it.

## Questions you will get

| Question | Answer |
| --- | --- |
| Why not let the AI decide? | Tax logic has to be testable and versioned. The rules are code with tests; the rates are data. The AI extracts and explains |
| What is mocked? | The data: Maya, her emails, her bank. The Gmail connection, the Plaid connection, the model calls and the rules are real. Her assignment dates come from a fixed list for now |
| Is this tax advice? | No. It organizes evidence and flags risk for a CPA |
| What about privacy? | Read-only scopes. Tokens encrypted at rest. We store a snippet and a link, not the email. One click revokes and deletes |
| Why the "unverified app" warning from Google? | The app is in Google's test mode. Verification and a security assessment are required before real users; that is on the roadmap |
| What happens if the AI reads something wrong? | It reports its confidence, and low-confidence records are flagged for review, as you saw. The user confirms or rejects. Rejected records never count |
| What is not built? | The CPA packet export, receipt uploads, and reading free-form offers. Five of ten planned rules are in |
| Who pays? | Workers by subscription; staffing agencies per seat, to check tax homes before they pay per diems |
| What did you build on? | AWS Strands Agents, Akamai Cloud inference and a Linode VM, Plaid sandbox, FastAPI and React |

## Numbers you can quote

Check these on the site before you go up, since they change after a reset.

- About 120 records filed automatically; about 70 distinct pieces of evidence, most confirmed by two sources.
- About 100 emails read; about 30 skipped as noise.
- One attack email, blocked.
- Score 56 of 100, 2 of 3 factors met, 3 findings.
- 45 weeks in Denver; the offer makes it 62.
