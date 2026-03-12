# Scripts Inventory

Utility scripts organized from root directory. **Total: 83 scripts** across 4 categories.

Run scripts with:
```bash
python manage.py shell < scripts/<folder>/<script>.py
# or
python scripts/<folder>/<script>.py
```

---

## checks/ (12 scripts)
Debug and inspection scripts for verifying state, API responses, DB data.

| Script | Purpose |
|--------|---------|
| `_check_registrations.py` | Check tournament registrations |
| `check_api_response.py` | Inspect API responses |
| `check_db.py` | Verify database state |
| `check_player.py` | Check player data |
| `check_t78.py` | Inspect tournament 78 state |
| `check_tournament_84_regs.py` | Check tournament 84 registrations |
| `check_tournament_config.py` | Verify tournament configuration |
| `check_tournament_state.py` | Check tournament state |
| `final_test.py` | Final validation test |
| `inspect_t21.py` | Inspect tournament 21 |
| `show_api_data.py` | Display API data |
| `verify_fix.py` | Verify a fix was applied correctly |

---

## testing/ (26 scripts)
Scripts for creating test data, test tournaments, and running test flows.

| Script | Purpose |
|--------|---------|
| `create_5v5_test_tournament.py` | Create a 5v5 test tournament |
| `create_bgmi_test_tournament.py` | Create a BGMI test tournament |
| `create_cod_test_tournament.py` | Create a COD test tournament |
| `create_e2e_testing_setup.py` | Setup E2E testing environment |
| `create_live_test_tournaments.py` | Create live test tournaments |
| `create_test_free_tournaments.py` | Create free test tournaments |
| `create_test_tournament.py` | Generic test tournament creation |
| `create_test_tournaments.py` | Create comprehensive test tournaments (54 events) |
| `create_upcoming_bulk_test_tournament.py` | Bulk upcoming tournament setup |
| `creation_automation.py` | Automate tournament creation |
| `generate_comprehensive_data.py` | Generate comprehensive test data |
| `insert_bulk_schedule_test.py` | Insert bulk schedule test data |
| `insert_bulk_test_data.py` | Insert bulk test data |
| `insert_test_tournaments.py` | Insert test tournaments |
| `insert_test_tournaments_bgmi_5v5.py` | Insert BGMI 5v5 test tournaments |
| `large_tournament_automation.py` | Automate large tournament scenarios |
| `scrim_automation.py` | Automate scrim creation |
| `setup_bulk_schedule_test.py` | Setup bulk schedule test |
| `small_tournament_automation.py` | Automate small tournament scenarios |
| `test_api_endpoint.py` | Test API endpoint |
| `test_bulk_schedule.py` | Test bulk schedule functionality |
| `test_csv_export.py` | Test CSV export functionality |
| `test_fix.py` | Test a specific fix |
| `test_free_registration.py` | Test free registration flow |
| `test_registration_flow.py` | Test full registration flow |
| `test_step1.py` | Test step 1 of a flow |

---

## fixes/ (7 scripts)
One-time fix scripts for correcting data inconsistencies.

| Script | Purpose |
|--------|---------|
| `cleanup_test_accounts.py` | Clean up test user accounts |
| `fix_current_participants.py` | Fix current participant counts |
| `fix_registrations.py` | Fix registration records |
| `fix_t30_bye_team.py` | Fix bye team in tournament 30 |
| `fix_team_mismatch.py` | Fix team mismatch issues |
| `fix_tournament_75_registration.py` | Fix tournament 75 registration |
| `fix_tournament_capacity.py` | Fix tournament capacity values |

---

## one-off/ (38 scripts)
One-time operational scripts for seeding data, configuring tournaments, etc.

| Script | Purpose |
|--------|---------|
| `add_10_teams.py` | Add 10 teams to a tournament |
| `add_bgmi_registrations.py` | Add BGMI registrations |
| `add_bgmi_teams.py` | Add BGMI teams |
| `add_cod_registrations.py` | Add COD registrations |
| `add_more_teams_to_tournament.py` | Add additional teams |
| `add_test_teams_to_tournament21.py` | Add test teams to tournament 21 |
| `advance_round.py` | Advance tournament to next round |
| `cleanup_and_add_teams_for_22.py` | Cleanup and add teams for tournament 22 |
| `complete_t78_round1.py` | Complete round 1 of tournament 78 |
| `configure_round1_bo3.py` | Configure round 1 as BO3 |
| `confirm_free_registration.py` | Confirm free registration |
| `create_and_simulate_cod_round1.py` | Create and simulate COD round 1 |
| `create_bgmi_tournament_73.py` | Create BGMI tournament 73 |
| `create_completed_pts_tournaments.py` | Create completed PTS tournaments |
| `create_rounds_t30.py` | Create rounds for tournament 30 |
| `create_t30_regs.py` | Create registrations for tournament 30 |
| `create_test_stats.py` | Create test statistics |
| `create_valorant_5v5_complete.py` | Create complete Valorant 5v5 tournament |
| `init_round_t88.py` | Initialize round for tournament 88 |
| `insert_additional_tournaments.py` | Insert additional tournaments |
| `insert_diverse_tournaments.py` | Insert diverse tournament types |
| `insert_live_tournament.py` | Insert a live tournament |
| `insert_more_tournaments.py` | Insert more tournaments |
| `insert_multiple_tournaments.py` | Insert multiple tournaments |
| `insert_tournament_registrations.py` | Insert tournament registrations |
| `make_tournaments_free.py` | Set tournaments as free |
| `make_tournaments_live.py` | Set tournaments to live state |
| `make_tournaments_live_5hrs.py` | Set tournaments live with 5hr window |
| `open_registrations_now.py` | Open registrations immediately |
| `populate_qualifiers_round1.py` | Populate qualifiers round 1 |
| `setup_live_tournament.py` | Setup a live tournament |
| `simulate_cod_full_tournament.py` | Simulate a full COD tournament |
| `submit_tournament_85_scores.py` | Submit scores for tournament 85 |
| `update_bulk_test_tournament_count.py` | Update bulk tournament counts |
| `update_tournament_counts.py` | Update tournament participant counts |
| `update_tournament_start.py` | Update tournament start time |
| `update_tournament_stats.py` | Update tournament statistics |
| `update_tournaments_live.py` | Update tournaments to live status |
