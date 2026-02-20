# Tournament Registration Flow - Detailed Breakdown

## Current Registration Flow

### Step 1: User Registers (Frontend)
- User enters: Team Name + All Teammate Emails (mandatory)
- Click "Register" → API call to `registerInitiate()`

### Step 2: Registration Created (Backend)
- TournamentRegistration created with:
  - status: `"pending"`
  - temp_teammate_emails: [email1, email2, email3, email4]
  - payment_status: false
  - invited_members_status: {} (empty at this point)

### Step 3: Payment Processing
- If tournament entry_fee > 0:
  - Payment gateway initiated
  - User pays
  - Payment callback triggers `process_successful_registration()`
- If tournament FREE:
  - Registration auto-confirmed immediately

### Step 4: Post-Payment (process_successful_registration())
- Registration status: `"pending"` → `"confirmed"`
- Team created with `is_temporary=False`
- TeamJoinRequest records created for each teammate email
- invited_members_status populated: 
  ```json
  {
    "email1@test.com": {"status": "pending", "username": null},
    "email2@test.com": {"status": "pending", "username": null},
    ...
  }
  ```
- Invite emails sent (async task)

### Step 5: Teammate Response
- Teammate receives email with invite link
- Accepts: TeamJoinRequest.status → `"accepted"`, invited_members_status updated
- Declines: TeamJoinRequest.status → `"rejected"`, invited_members_status updated

---

## Three Key Questions

### ❓ Question 1: When Should Registration Be "Confirmed"?

**Current Behavior:**
- Registration confirmed AFTER payment (Step 4)
- Teams are confirmed even if teammates haven't accepted yet

**Option A: Confirm After Payment (Current)**
- ✅ Simpler logic
- ❌ Team might not be complete if teammates decline

**Option B: Confirm Only After All Teammates Accept**
- ✅ Guarantees full team is available
- ❌ More complex, requires "hold" state
- ❌ What if teammate never responds? (Timeout)

**Recommendation:** Keep Option A (current) BUT track member acceptance separately for display/participation.

---

### ❓ Question 2: "Registered Team Members Card" - Don't Show Tournament Teams?

**Question:** Do you want tournament-created teams:
1. **Hidden from main team list** (player's dashboard teams)?
2. **Shown separately** in "Tournament Teams" section?
3. **Not shown at all** until all teammates accept?

**Current Behavior:**
- Teams created with `is_temporary=False` (shows everywhere)

**Proposed Solution:**
- Change to `is_temporary=True` for tournament-registration teams
- Only show in "Your Tournament Registrations" section
- Keep as temporary until tournament ends

---

### ❓ Question 3: Resend Invite Logic - Structure?

**Need to handle:**
1. Captain views their tournament registrations
2. Sees teammate status (pending/accepted/declined)
3. Can resend to declined teammates
4. System generates new invite token + sends email

**Two Implementation Options:**

**Option A: Single Endpoint (Simpler)**
```
POST /api/accounts/invites/<old_token>/resend/
- Finds old TeamJoinRequest
- Generates new token
- Resets status to "pending"
- Sends new email
```

**Option B: Captain Dashboard Endpoint (Better UX)**
```
POST /api/tournaments/<id>/registrations/<reg_id>/resend-invite/
Body: { "email": "teammate@test.com" }
- Finds all declining invites for that email
- If exists: Generate new token, reset to pending
- If not: Create new invite
- Send email
```

**Recommendation:** Option B (better user experience, captain-focused)

---

## Summary of Changes Needed

1. **Team Creation Flag**: Mark tournament teams with `is_temporary=True`
2. **Resend Backend**: New endpoint for captain to resend declined invites
3. **Frontend UI**: Captain dashboard showing:
   - Registration status
   - Each teammate status (pending/accepted/declined)
   - Resend button for declined invites
4. **Email Logic**: Support resending invites (new token generation)

