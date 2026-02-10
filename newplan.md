I'll research the codebase to understand the current tournament system architecture and then create a detailed implementation plan for adding Valorant and Call of Duty support. 


## Plan: 5v5 Match System for Valorant & Call of Duty

Currently, SCRIMVERSE treats all games identically with multi-team lobbies (up to 25 teams per group). The requirement is to add support for **Valorant and Call of Duty as strict 5v5 head-to-head matches** where each group contains exactly 2 teams fighting against each other. Additionally, stats must be **game-specific** rather than merged, and leaderboards need filtering by game. This is a structural change affecting models, services, scoring logic, qualification rules, and stats tracking.

**Key Architectural Decision:** Instead of adding a separate `lobby_type` field, we'll use the existing `game_name` field to infer lobby behavior—games like BGMI/Scarfall/Free Fire continue as multi-team, while Valorant/COD use head-to-head logic. This keeps the data model simpler while enabling distinct behavior.

**Steps**

1. **Add Valorant to Game Choices & Helper Methods** 
   - Update models.py `GAME_CHOICES` to include `("Valorant", "Valorant")`
   - Add `is_head_to_head_game()` method to `Tournament` model that returns `True` if `game_name` in `["COD", "Valorant"]`
   - Add `requires_password()` method that returns `False` for Valorant (ID only), `True` for others

2. **Modify Match Model for Winner Tracking**
   - Add `winner` field to models.py model: `ForeignKey(TournamentRegistration, null=True, blank=True, related_name='won_matches')`
   - Add `match_type` field with choices: `SINGLE`, `BEST_OF_2`, `BEST_OF_3`, `BEST_OF_4`
   - Make `match_password` nullable and conditional based on game type
   - Add `determine_winner()` method that compares total_points of the 2 teams in the match and sets `winner`

3. **Create Head-to-Head Group Creation Logic**
   - Add new method `create_head_to_head_groups()` in services.py
   - Logic: For N teams, create N/2 groups with exactly 2 teams each
   - Each group name represents a matchup: "Match 1", "Match 2", etc. (instead of "Group A", "Group B")
   - Create M matches per group based on `matches_per_group` (e.g., 3 for Best of 3)
   - Validation: Ensure even number of teams, throw error if odd
   - Random pairing: Shuffle teams and pair sequentially

4. **Update Round Configuration Endpoint**
   - Modify configure_round view in `groups_views.py`
   - Add conditional logic: if `tournament.is_head_to_head_game()`, call `create_head_to_head_groups()` instead of `create_groups_for_round()`
   - For head-to-head: `qualifying_per_group` becomes "number of groups to advance" (winner from each selected group)
   - Update validation: head-to-head requires even teams, multi-team validates against MAX_TEAMS_PER_GROUP

5. **Modify Qualification Logic for Head-to-Head Games**
   - Update models.py to check tournament type
   - For head-to-head: Return the single winner team from the group (highest total_points across all matches)
   - For multi-team: Keep existing logic (top K teams by total_points)
   - Update round results endpoint to show "Group Winners" vs "Top Teams" based on game type

6. **Auto-Calculate Match Winners on Score Submission**
   - Modify groups_views.py to auto-determine winner after scores are saved
   - After creating/updating `MatchScore` records, call `match.determine_winner()` for head-to-head games
   - Winner determination: Compare `total_points` of 2 teams in the match; highest wins; ties go to `kill_points`, then alphabetical
   - Store winner in `Match.winner` field

7. **Add Game-Specific Stats Tracking**
   - Update models.py model to support multiple records per team
   - Change from `OneToOneField` to `ForeignKey` with `unique_together = ['team', 'game_name']`
   - Add `game_name` field with same choices as Tournament `GAME_CHOICES`
   - Keep all existing stat fields (tournament_wins, scrim_wins, position_points, kill_points, etc.)
   - Add `related_name='statistics_by_game'` to maintain backward compatibility

8. **Create Data Migration for Existing Stats**
   - Write migration to convert existing `TeamStatistics` records
   - For each team with existing stats, create separate records for each game they've played
   - Query tournaments the team participated in, group stats by `game_name`
   - For teams with no tournament history, create a default "All Games" record or skip

9. **Update Stats Calculation Logic**
   - Modify tasks.py leaderboard calculation tasks
   - When updating team stats after tournament completion, fetch/create the game-specific `TeamStatistics` record
   - Update: `TeamStatistics.objects.get_or_create(team=team, game_name=tournament.game_name)`
   - Ensure stats are isolated per game (BGMI stats don't affect Valorant leaderboard)

10. **Add Game Filter to Leaderboard API**
    - Update leaderboard_views.py to accept `game` query parameter
    - Allowed values: `BGMI`, `COD`, `Valorant`, `Freefire`, `Scarfall`, `All`
    - Filter `TeamStatistics` by `game_name` if specified; aggregate across all games for "All"
    - Update ordering and ranking to be game-specific
    - Response includes `game_filter` field indicating which filter is active

11. **Update Team/Player Profile Endpoints**
    - Modify team detail view to return stats segmented by game
    - Response structure: `{"stats_by_game": {"BGMI": {...}, "COD": {...}, "Valorant": {...}}, "overall_stats": {...}}`
    - Add optional `game` query parameter to fetch stats for specific game only
    - Ensure backward compatibility: default to aggregated stats if no game specified

12. **Update Serializers for Winner Display**
    - Modify Match serializer to include `winner` field with nested team data
    - For head-to-head matches, include `team_a` and `team_b` fields (first 2 teams in group)
    - Add `is_head_to_head` computed field for frontend rendering logic
    - Include `match_type` in serialization for UI to display "Best of X"

13. **Add Match Results View for Head-to-Head**
    - Create new view/endpoint to get detailed match results for a group in head-to-head format
    - Returns: Team A vs Team B, match-by-match scores, winner badge data
    - Include aggregate stats across all matches in the series
    - Format optimized for frontend "Match Card" UI shown in screenshots

**Verification**

- **Unit Tests**: Test `create_head_to_head_groups()` with even/odd teams, verify 2 teams per group
- **API Tests**: Create Valorant tournament, configure round → verify N/2 groups created
- **Stats Tests**: Submit scores for different games → verify stats are isolated per game
- **Leaderboard Tests**: Filter by game → verify only relevant teams/stats returned
- **Qualification Tests**: Head-to-head tournament → verify only group winners advance
- **Manual Testing**: Create demo COD tournament (20 teams), start match → verify 10 lobbies (2 teams each), submit scores → verify winners auto-calculated

**Decisions**

- **Infer from game_name vs dedicated field**: Using `game_name` to determine lobby type keeps models simpler and avoids redundant flags. COD and Valorant naturally require 5v5 logic.

- **Stats migration strategy**: Converting to ForeignKey with game_name creates clean separation. Historical aggregated stats can be preserved or distributed based on tournament history.

- **Group naming for head-to-head**: Reusing "Group" model but calling them "Match 1", "Match 2" in the UI maintains code reusability while adapting terminology for frontend clarity.

- **Winner auto-calculation**: Determining winners in the backend on score submission ensures data consistency and reduces frontend complexity. Winner field is source of truth.

- **Password optional for Valorant**: Making password nullable and checking `tournament.requires_password()` enables game-specific room credential logic without separate models.