# Scrimverse Django Admin: The Ultimate Master Guide

This document is the absolute source of truth for managing the Scrimverse platform via the Django Admin. It covers every active module, technical workflows, and "End-to-End" testing scenarios for teammates.

---

## 1. Master Overview
**URL:** [http://localhost:8000/admin](http://localhost:8000/admin)
**Access Logic:** The Admin is the direct interface for the PostgreSQL database. It handles logic that isn't yet exposed in the Frontend UI (Port 3000) or is strictly for site owners.

---

## 2. PART 1: ACCOUNTS & IDENTITY (The Foundation)

### A. Users
*   **Identity Control:** Manage emails, passwords, and permissions.
*   **Permissions:** Use the `Groups` section (under Authentication) to assign "Moderator" or "Superuser" roles.
*   **Test Scenario:** Change a `User Type` from `Admin` to `Host` and verify they can no longer access this Admin panel but *can* log in as a Host on the Frontend.

### B. Host Profiles & Aadhar Verification
*   **The Trust Wall:** Hosts must be verified before their tournaments go public.
*   **Fields:** Look for `Verification notes` to explain *why* you rejected an Aadhar card (e.g., "Blurry image").
*   **Verified Badge:** Checking `Verified` = Green light for the Host's tournaments to appear on the site.

### C. Player Profiles
*   **Gamer Identity:** Links a User to their In-Game Name (IGN) and UID.
*   **Test Scenario:** Manually edit a player's `Total Wins` and verify it updates their rank on the Frontend Leaderboard.

### D. Teams & Joint Requests
*   **Team Statistics:** Tracks points per game (BGMI vs Valorant).
*   **Join Requests:** Manage invites from Captains to Players. 
*   **Technical Tip:** If a player says they "didn't get an invite," check the `Team Join Requests` table for an `Expired` status.

---

## 3. PART 2: TOURNAMENTS & ENGINE (The Heart)

### A. Tournaments Master List
*   **Global Toggle:** Use the "Actions" dropdown to `Clone Tournament` (copies all settings to a new one) or `Export to CSV`.
*   **Plan Status:** Track if the Host has paid for their "Featured" or "Premium" placement.

### B. Groups & Round Management
*   **Sub-Seeding:** Groups (`Groups` under TOURNAMENTS) allow you to divide 100 teams into 5 lobbies of 20 teams each.
*   **Round Status:** Track progress from Round 1 -> Semi-Finals -> Finals.

### C. Match & Room Management (NEWly Documented)
*   **Room ID/Pass:** Found in the `Matches` section.
*   **Automation Action:** Use the **"Generate Room IDs"** action to create randomIDs/Passwords for players to see on their dashboards.
*   **Test Scenario:** 
    1. Create a Match.
    2. Set a Room ID and Password.
    3. Save.
    *   *Verification:* Ensure the "Room Details" button appears for players on the Frontend registration page.

### D. Scoring & Leaderboards
*   **Match Scores:** Individual match performance (Kills + Placement).
*   **Round Results:** Summary of a team's performance across multiple matches in a round.
*   **Recalculation Action:** If scores look "stuck," use **"Recalculate from Match Scores"** in the `Round results` section to force a refresh.

---

## 4. PART 3: PAYMENTS & PLAN PRICING (The Revenue)

### A. The Ledger (Payments)
*   **Merchant Order ID:** Unique key for every transaction. Useful for debugging PhonePe logs.
*   **Metadata Preview:** Hover over this to see the raw JSON data sent back from PhonePe (UPI ID, Bank name, etc.).

### B. Refunds & Corrections
*   **Action:** `Initiate Refund`. Triggers the PhonePe API call.
*   **Test Scenario:** Manually add a Payment with status `payment_success` and attempt to trigger a refund action (check logs for API response).

### C. Plan Pricing
*   **Dynamic Costs:** Change the entry price of a "Tournament - Pro" plan here.
*   **Verification:** Verify the price update on the "Create Tournament" page for Hosts on the Frontend.

---

## 5. PART 4: HOST RATINGS & MODERATION

### A. Host Ratings
*   **Spam Control:** Players can rate hosts after a tournament.
*   **Moderation:** Admins can delete spam reviews or inappropriate content in the `Host ratings` section.
*   **Verification:** Deleting a rating here will instantly change the Host's "Average Rating" stars on their public profile.

---

## 6. Common Gotchas & Expert Tips
1.  **Server Restart:** If you change code in `admin.py`, the server restarts automatically. Wait for the terminal to show `Watching for file changes...` before refreshing the browser.
2.  **Null Values:** When adding a new Tournament, ensure `Max Participants` is not empty, or the "Progress Bar" calculation might throw an error (Fixed but good to remember).
3.  **Celery:** Always keep the Celery worker running (`celery -A scrimverse worker`). It handles the bulk creation of Groups and Matches in the background when you save a Tournament.

---

## 7. Comprehensive Verification Checklist
- [ ] Log in as Superuser.
- [ ] Create a Test Tournament -> Verify on Frontend.
- [ ] Verify a Test Host -> Verify they can host.
- [ ] Add a Manual Score -> Verify leaderboard updates.
- [ ] Generate Room Credentials -> Verify player visibility.
- [ ] Export a Team List to CSV -> Verify file contents.
