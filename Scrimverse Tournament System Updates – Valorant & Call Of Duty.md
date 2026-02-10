https://scrimverseee.lovable.app 

Please refer to this website for Call of Duty and Valorant configuration details. Steps to navigate are:
1. Go to the host dashboard.
2. Press on the demo Call of Duty or the Valorant manage.
3. Then start the match to view all the lobbies and how they are structured.


SCRIMVERSE – Tournament System Update
Requirements

Context

Currently, SCRIMVERSE supports BGMI, Scarfall, and Free Fire, which are lobby based and multi team per
lobby games.

We now need to add support for Valorant and Call of Duty, which follow a strict 5v5, team vs team
match structure. This document explains the logic, flow, and UI changes in simple, developer friendly
terms.

1. Core Difference: Existing Games vs Valorant / COD
Existing Games (BGMI, Scarfall, Free Fire)
• 
• 
• 
• 
One lobby can contain many teams (example: 16, 20, or 25 teams).
All teams get the same Room ID and Password.
Admin selects how many teams qualify to the next round.
Leaderboards are lobby based, not match based.
Valorant & Call of Duty (New Requirement)
• 
• 
• 
• 
Match format is 5v5 only.
One lobby = exactly 2 teams.
These two teams fight each other.
Qualification is based on groups (matches), not individual teams.

2. Group & Lobby Logic for Valorant / COD
Definitions
• 
• 
• 
Team: A registered squad (5 players)
Group: One match consisting of 2 teams only
Lobby: One game instance with 1 Group
Example
If 20 teams register:
• 
• 
System auto-creates 10 groups
Each group has 2 teams

Example grouping:
• 
• 
• 
Group 1: Team A vs Team B
Group 2: Team C vs Team D
Group 3: Team E vs Team F
Each group gets:
• 
• 
Unique Match ID (only ID, no password) for Valorant; other games: include ID and password.)
Match specific stats (Team A scored 10 points, Team B scored 5 points)

3. Qualification Logic Change (Important)
Logic (Valorant / COD)
• 
• 
Admin selects how many groups qualify
The winner of each selected group automatically advances
Example:
• 
• 
• 
Total groups: 10
Admin selects: Top 5 groups advance
Result: 5 winning teams move to the next round

4. Match-Based Scoring System
Required Change
Points must be stored per match, per group.
Match Structure
• 
• 
• 
A group can play multiple matches (Best of 3 or Best of 4)
Admin can choose:
Number of matches per round
Match Level Stats
Each match should store:
• 
• 
• 
• 
Wins
Placement Points (if applicable)
Kill Points
Total Points

5. Match View & UI Requirements
Admin View
• 
• 
• 
• 
• 
Select Tournament → Round → Group → Match ( you can view the demo on the lovable website)
View:
Team Alpha vs Team Bravo
Match-wise score
Winner highlighted (icon/badge)
Example:
• 
• 
• 
• 
Match 1:
Team Alpha: 10 points
Team Bravo: 5 points
Winner: Team Alpha

6. Flexible Match Count Logic
• 
• 
• 
Qualifiers can allow unlimited amateur matches
Main rounds should have a fixed match limit of 4 ( but should have access in the admin portal to
increase if they request)
The points table dynamically updates per match 

7. Player & Team Profile Stats (Critical Fix)
Current Issue
• 
Stats from all games are merged together
Required Change
Stats must be game-specific.
Profile View Options
User should be able to:
• 
• 
• 
• 
View BGMI stats only
View Valorant stats only
View Free Fire stats only
View All Games (combined view)

This applies to:
• 
• 
• 
Player Profile
Team Profile
Global Leaderboards

8. Leaderboard Filtering
Global Leaderboard
Add a filter:
• 
• 
• 
• 
BGMI
Valorant
Free Fire
All Games
Leaderboard data should update based on selected game only.

9. Summary of Required Changes
Backend
• 
• 
• 
• 
Introduce Group = 2 teams logic for Valorant & COD
Match-level scoring instead of lobby level
Group-based qualification instead of team based
Game-specific stat separation
Frontend / UI
• 
• 
• 
Winner indicators per match
Game filters in profiles & leaderboards
Clear separation between BGMI-style tournaments and Valorant / COD-style tournaments

10. Notes
• 
• 
• 
• 
This logic should not affect existing BGMI / Free Fire tournaments
Tournament type should define behavior:
Multi-team lobby
2 team match lobby
