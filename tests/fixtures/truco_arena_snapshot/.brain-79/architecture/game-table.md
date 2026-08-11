# Game Table UI Architecture (`GAME_TABLE`)

## Canonical Reference
The interactive prototype located in [`concept/mocks/`](file:///Users/xilax/Documents/GitHub/truco-arena/concept/mocks) and documented in [`concept/table-spec.md`](file:///Users/xilax/Documents/GitHub/truco-arena/concept/table-spec.md) is the single canonical source of truth for the game table UI.

> **Production Build Rule**: The top navigation bar `.proto-controls` ("DEMO ESCENARIOS") present in `concept/mocks/index.html` is strictly a prototype controller for testing game scenarios in the browser. It **MUST BE OMITTED** when building the production `GAME_TABLE` screen.

## Component Topology & Key Features
1. **Billiard / Blackjack Green Table Felt**:
   - Radial felt gradient (`#1d5935` center to `#082213` edge).
   - Clean 28px rounded borders with gilded gold perimeter trim.

2. **Dynamic 60-Second Turn Clock (`#turn-timer-container`)**:
   - Moves dynamically between active player zones (bottom for user, top for opponent).
   - Color shifts: Green (>25s) -> Amber (11-25s) -> Red pulse (<10s).
   - Auto-folds on timeout (0s).

3. **Left-Aligned MANO Token**:
   - Gold coin token anchored to the left of the played card line (`left: -75px`).
   - Top-left for opponent, bottom-left for player.

4. **Color-Coded Trick Outcome Slots**:
   - Column-based glow borders: Green (`#00e676`) for Win `✓`, Red (`#ff2e63`) for Loss `✗`, Amber Orange (`#ff9800`) for Tie `=`.

5. **Anotador Porteño Scoreboard**:
   - Desktop: Positioned on the right inside felt table.
   - Mobile (`≤ 768px`): Condenses into a compact floating pill badge (`12 - 9 📊`) at top-right of felt. Tapping opens a glassmorphic modal overlay.
   - Integrated `Mano N° X` counter badge.
   - Clean stakes indicators (`✓ 2 PTS`, `✗ 2 PTS`, `2 PTS` orange pending).

6. **Centered Player Hand & Separated Fold Button**:
   - 3 visible player cards mathematically centered (`margin: 0 auto`).
   - `IR AL MAZO` button positioned to the right with offset `left: calc(50% + 175px)`.

7. **AAA Interleaved Card Dealing Engine**:
   - Cards deal 1-by-1 alternating starting from Mano with 140ms stagger and 280ms 3D flight trajectory from `MAZO`.
   - Hand containers pre-render reserved `opacity: 0` placeholders to ensure zero screen/layout shift.
