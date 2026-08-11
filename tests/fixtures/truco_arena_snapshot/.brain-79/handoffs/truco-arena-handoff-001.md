# Truco Arena — Handoff

## Repo
`/Users/xilax/Documents/GitHub/truco-arena`

## Branch
`feat/truco-rules-engine` — 2 commits, 2166+294 líneas engine/test

## Estado actual
- ✅ `npm test`: 24/24 passing (13 SIM + 11 adversarial)
- ✅ `npx tsc --noEmit`: exits 0
- ✅ `engine/` sin imports prohibidos (react/fs/net/http/dom)
- ✅ Sin console.log en engine/

## Commits recientes

### fix(engine): enforce "tener el quiero" rule in Truco raises (18dc1e5)
- Solo `quieroHolderId` puede subir (Retruco/Vale4)
- Tras subir, `quieroHolderId = opponentId(state, playerId)`
- 11 adversarial tests cubren flujo completo

### feat(engine): implement Truco game engine with all 13 simulation tests (8051a5f)
- Mal Truco: `callerId` original, sanción = `level-1`
- Parda credit removida del motor
- Figs ranks únicos por suit
- `dealerId` param en `dealHands`

## Reglas de Truco verificadas (memory:truco_engine_facts)

| Concepto | Valor |
|----------|-------|
| Orden de cartas (menor=better) | 1E=1, 1B=2, 7E=3, 7O=4, 3x=5, 2x=6, 1O=1C=7... |
| Truco | 2 pts | 
| Retruco | 3 pts |
| Vale4 | 4 pts |
| Mal Truco (caller pierde) | `level-1` pts (mín 1) |
| Parda | mismo rank → parda; 3 pardass → mano gana |
| Envido querido | 2 pts |
| Falta Envido | `30 - winnerScore` pts |
| Flor vs Flor | 4 pts para mano |
| `son_buenas` vs número | pierde (número gana) |
| Parada no-starter | no se enforcea crédito en engine |

## Estructura clave

- `engine/state.ts` — main logic (handleTrucoCanto, handleCardPlayed, etc.)
- `engine/scoring.ts` — card comparison (compareCards, determineHandWinner)
- `engine/types.ts` — TrucoBetState, HandState, etc.
- `engine/deck.ts` — dealHands, shuffleDeck
- `engine/errors.ts` — EngineErrorCode
- `tests/sim/sim-all.test.ts` — 13 SIM tests
- `tests/adversarial.test.ts` — 11 adversarial tests

## siguiente revisión pendientes
1. ¿Hay más bugs adversarial reportados?
2. ¿Verificar que los tests adversarial de SIM-05/SIM-06 (mal Truco en R3) sean consistentes?
3. `brain79` indexing pendiente — bootstrapped o vacío al momento de este commit
